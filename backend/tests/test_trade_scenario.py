import pytest
from unittest.mock import patch
from decimal import Decimal
from backend.models import OrderStatus, OrderSide, OrderType, Portfolio
from backend.services.trade_service import execute_trade

# 시나리오 테스트
# 주의: create_order API는 RabbitMQ로 보내기만 하고 체결은 안 함.
# 따라서 여기서는 'API를 통해 주문을 넣는 것'보다
# 'execute_trade 함수를 직접 호출'하여 체결 로직을 검증하는 것이 더 확실함.
# (API 테스트는 잔고 체크 로직 검증용으로 별도로 할 수 있음)

class TestShortSellingScenario:
    
    def test_short_selling_flow(self, db_session, test_user, test_ticker, mock_external_services):
        """
        공매도 -> 물타기 -> 상환 -> 스위칭 전체 시나리오 검증
        """
        user_id = str(test_user)
        ticker_id = test_ticker
        
        # Mocking: Redis에서 현재가를 가져오는 함수 가로채기
        # trade_service.get_current_price를 우리가 원하는 값으로 조작
        
        with patch("backend.services.trade_service.get_current_price") as mock_price:
            
            # =================================================
            # Step 0: 초기 상태 확인 (잔고 1억)
            # =================================================
            # execute_trade는 order_id가 DB에 있어야 하므로, 
            # 테스트 편의를 위해 execute_trade 내부에서 Order를 조회하는 부분을 
            # 'DB에 주문을 미리 생성'해두는 방식으로 처리해야 함.
            # 하지만 execute_trade는 Order가 없으면 생성하기도 함(시장가).
            # 여기서는 시장가(MARKET) 로직을 타도록 유도.
            
            # =================================================
            # Step 1: 공매도 1개 (가격 100원)
            # =================================================
            mock_price.return_value = Decimal("100.0")
            order_id_1 = "00000000-0000-0000-0000-000000000001"
            
            result = execute_trade(
                db=db_session,
                user_id=user_id,
                order_id=order_id_1,
                ticker_id=ticker_id,
                side="SELL",
                quantity=1.0
            )
            assert result is True
            
            # 검증
            pf = db_session.query(Portfolio).first()
            assert pf.quantity == Decimal("-1.0")
            assert pf.average_price == Decimal("100.0")
            # 잔고: 1억 + 100원
            # (Wallet 모델을 다시 조회해야 함)
            # wallet = db_session.query(Wallet).first()
            # assert wallet.balance == 100000100 

            # =================================================
            # Step 2: 숏 물타기 (추가 공매도 1개, 가격 150원)
            # =================================================
            mock_price.return_value = Decimal("150.0") # 가격 상승
            order_id_2 = "00000000-0000-0000-0000-000000000002"
            
            execute_trade(db_session, user_id, order_id_2, ticker_id, "SELL", 1.0)
            
            db_session.refresh(pf)
            assert pf.quantity == Decimal("-2.0")
            # 평단가: (100*1 + 150*1) / 2 = 125.0
            assert pf.average_price == Decimal("125.0")
            
            # =================================================
            # Step 3: 숏 수익 실현 (1개 상환, 가격 50원)
            # =================================================
            mock_price.return_value = Decimal("50.0") # 가격 폭락 (이득)
            order_id_3 = "00000000-0000-0000-0000-000000000003"
            
            execute_trade(db_session, user_id, order_id_3, ticker_id, "BUY", 1.0)
            
            db_session.refresh(pf)
            assert pf.quantity == Decimal("-1.0")
            # 상환 시 평단가는 변하지 않음 (125.0 유지)
            assert pf.average_price == Decimal("125.0")
            
            # =================================================
            # Step 4: 스위칭 (숏 1개 -> 롱 2개, 가격 50원)
            # 주문 수량 3개 매수 (1개 상환 + 2개 신규 롱)
            # =================================================
            # 가격 유지
            order_id_4 = "00000000-0000-0000-0000-000000000004"
            
            execute_trade(db_session, user_id, order_id_4, ticker_id, "BUY", 3.0)
            
            db_session.refresh(pf)
            # 결과: -1 + 3 = +2
            assert pf.quantity == Decimal("2.0")
            # 평단가: 신규 진입 가격인 50.0으로 리셋되어야 함
            assert pf.average_price == Decimal("50.0")
            
            # =================================================
            # Step 5: 롱 청산 (전량 매도, 가격 60원)
            # =================================================
            mock_price.return_value = Decimal("60.0")
            order_id_5 = "00000000-0000-0000-0000-000000000005"
            
            execute_trade(db_session, user_id, order_id_5, ticker_id, "SELL", 2.0)
            
            # 삭제되었는지 확인
            pf_deleted = db_session.query(Portfolio).first()
            assert pf_deleted is None # 삭제됨
