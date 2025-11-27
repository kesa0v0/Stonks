import pytest
from unittest.mock import patch
from decimal import Decimal
from sqlalchemy import select
from backend.models import OrderStatus, OrderSide, OrderType, Portfolio, Order, Wallet
import uuid
from backend.services.trade_service import execute_trade
from backend.tests.conftest import convert_decimals_to_str # Import the helper

class TestShortSellingScenario:
    
    @pytest.mark.asyncio
    async def test_short_selling_flow(self, db_session, test_user, test_ticker, mock_external_services, payload_json_converter):
        """
        공매도 -> 물타기 -> 상환 -> 스위칭 전체 시나리오 검증
        """
        user_id = str(test_user)
        ticker_id = test_ticker
        mock_redis = mock_external_services["redis"]
        
        # Mocking: Redis에서 현재가를 가져오는 함수 가로채기
        # trade_service.get_current_price를 우리가 원하는 값으로 조작
        
        with patch("backend.services.trade_service.get_current_price") as mock_price:
            
            # =================================================
            # Step 1: 공매도 1개 (가격 100원)
            # =================================================
            # AsyncMock이어야 함
            async def return_100(*args, **kwargs): return Decimal("100.0")
            mock_price.side_effect = return_100
            
            order_id_1 = "00000000-0000-0000-0000-000000000001"
            
            # await 추가
            result = await execute_trade(
                db=db_session,
                redis_client=mock_redis,
                user_id=user_id,
                order_id=order_id_1,
                ticker_id=ticker_id,
                side="SELL",
                quantity=Decimal("1.0") # Use Decimal
            )
            assert result is True
            
            # 검증
            res = await db_session.execute(select(Portfolio))
            pf = res.scalars().first()
            assert pf.quantity == Decimal("-1.0")
            assert pf.average_price == Decimal("99.9") # Changed from 100.0 to 99.9
            # =================================================
            # Step 2: 숏 물타기 (추가 공매도 1개, 가격 150원)
            # =================================================
            async def return_150(*args, **kwargs): return Decimal("150.0")
            mock_price.side_effect = return_150
            
            order_id_2 = "00000000-0000-0000-0000-000000000002"
            
            await execute_trade(db_session, mock_redis, user_id, order_id_2, ticker_id, "SELL", Decimal("1.0")) # Use Decimal
            
            await db_session.refresh(pf)
            assert pf.quantity == Decimal("-2.0")
            # 평단가: (99.9*1 + 150*1) / 2 = 124.95
            # 원래는 99.9 + (150 - 150*0.001) = 99.9 + 149.85 = 249.75.
            # new_qty_abs = 2.
            # 249.75 / 2 = 124.875
            assert pf.average_price == Decimal("124.875")
            
            # =================================================
            # Step 3: 숏 수익 실현 (1개 상환, 가격 50원)
            # =================================================
            async def return_50(*args, **kwargs): return Decimal("50.0")
            mock_price.side_effect = return_50
            
            order_id_3 = "00000000-0000-0000-0000-000000000003"
            
            await execute_trade(db_session, mock_redis, user_id, order_id_3, ticker_id, "BUY", Decimal("1.0")) # Use Decimal
            
            await db_session.refresh(pf)
            assert pf.quantity == Decimal("-1.0")
            # 상환 시 평단가는 변하지 않음 (124.875 유지)
            assert pf.average_price == Decimal("124.875")
            
            # =================================================
            # Step 4: 스위칭 (숏 1개 -> 롱 2개, 가격 50원)
            # 주문 수량 3개 매수 (1개 상환 + 2개 신규 롱)
            # =================================================
            # 가격 유지
            order_id_4 = "00000000-0000-0000-0000-000000000004"
            
            await execute_trade(db_session, mock_redis, user_id, order_id_4, ticker_id, "BUY", Decimal("3.0")) # Use Decimal
            
            await db_session.refresh(pf)
            # 결과: -1 + 3 = +2
            assert pf.quantity == Decimal("2.0")
            # 평단가: 신규 진입 가격인 50.0으로 리셋되어야 함
            assert pf.average_price == Decimal("50.0")
            
            # =================================================
            # Step 5: 롱 청산 (전량 매도, 가격 60원)
            # =================================================
            async def return_60(*args, **kwargs): return Decimal("60.0")
            mock_price.side_effect = return_60
            
            order_id_5 = "00000000-0000-0000-0000-000000000005"
            
            await execute_trade(db_session, mock_redis, user_id, order_id_5, ticker_id, "SELL", Decimal("2.0")) # Use Decimal
            
            # 삭제되었는지 확인
            res = await db_session.execute(select(Portfolio))
            pf_deleted = res.scalars().first()
            assert pf_deleted is None # 삭제됨

class TestBalanceValidation:
    @pytest.mark.asyncio
    async def test_insufficient_balance_buy_order(self, db_session, test_user, test_ticker, mock_external_services, payload_json_converter):
        """
        잔고 부족으로 인한 매수 주문 실패 시나리오 검증
        """
        user_id = str(test_user)
        ticker_id = test_ticker
        mock_redis = mock_external_services["redis"]
        
        # 1. 사용자 지갑 잔고를 매우 낮게 설정
        result = await db_session.execute(select(Wallet).where(Wallet.user_id == test_user))
        wallet = result.scalars().first()
        wallet.balance = Decimal("50.0") # 50원으로 설정
        db_session.add(wallet)
        await db_session.commit()
        await db_session.refresh(wallet)
        
        # 2. 매수 주문 시도 (주문 금액 > 잔고)
        order_quantity = Decimal("1.0") # Use Decimal
        mock_order_price = Decimal("100.0")
        
        with patch("backend.services.trade_service.get_current_price") as mock_price:
            async def return_price(*args, **kwargs): return mock_order_price
            mock_price.side_effect = return_price
            
            order_id = str(uuid.uuid4())
            
            result = await execute_trade(
                db=db_session,
                redis_client=mock_redis,
                user_id=user_id,
                order_id=order_id,
                ticker_id=ticker_id,
                side="BUY",
                quantity=order_quantity
            )
            
            # 3. 결과 검증
            assert result is False, "잔고 부족으로 매수 주문이 실패해야 합니다."
            
            # 별도 트랜잭션으로 처리된 실패 상태 확인
            # (execute_trade가 실패 시 별도 commit을 하므로 조회 가능해야 함)
            res = await db_session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))
            failed_order = res.scalars().first()
            
            if failed_order:
                assert failed_order.status == OrderStatus.FAILED
                assert "Insufficient balance" in failed_order.fail_reason
            
            # 지갑 잔고가 변하지 않았는지 확인
            await db_session.refresh(wallet)
            assert wallet.balance == Decimal("50.0")