from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from decimal import Decimal
import logging

from backend.models import User, Wallet, Portfolio, Ticker, DividendHistory
from backend.services.common.wallet import add_balance, sub_balance
from backend.core.constants import WALLET_REASON_DIVIDEND
from backend.core.event_hook import publish_event
import redis.asyncio as async_redis
from backend.core.config import settings

logger = logging.getLogger(__name__)

async def process_dividend(db: AsyncSession, payer_user: User, pnl: Decimal):
    """
    수익 발생 시 배당금을 계산하여 주주들에게 분배합니다.
    """
    # 1. 배당 조건 확인
    if pnl <= 0 or payer_user.dividend_rate <= 0:
        return

    # 2. 배당금 계산
    # dividend_rate는 Numeric(5,4) (예: 0.5000)
    total_dividend = pnl * payer_user.dividend_rate
    
    # 3. 주주 조회 (자사주 제외 - 자사주는 배당 안 함 or 소각 효과)
    # payer의 HUMAN ETF 티커 ID: HUMAN-{user_id}
    ticker_id = f"HUMAN-{payer_user.id}"
    
    # 전체 발행량 조회 (자사주 포함? 제외? -> 보통 자사주는 배당 제외가 원칙)
    # 여기서는 '본인 제외'한 나머지 주주들에게만 배당한다고 가정.
    # 만약 본인이 100% 가지고 있으면 배당금은 0원 (본인이 본인에게 주는 건 의미 없음)
    stmt = select(Portfolio).where(
        Portfolio.ticker_id == ticker_id,
        Portfolio.user_id != payer_user.id, # 자사주 제외
        Portfolio.quantity > 0
    )
    result = await db.execute(stmt)
    shareholders = result.scalars().all()
    
    if not shareholders:
        logger.info(f"No shareholders for {ticker_id}. Dividend skipped.")
        return

    # 유통 주식 수 계산
    total_shares = sum(s.quantity for s in shareholders)
    
    if total_shares <= 0:
        return

    # 4. 배당금 징수 (Payer 지갑에서 차감)
    # 이미 trade_service에서 net_income이 입금된 상태라고 가정하고 여기서 차감함.
    # 주의: trade_service와 같은 트랜잭션 안에서 실행되어야 함.
    payer_wallet_stmt = select(Wallet).where(Wallet.user_id == payer_user.id).with_for_update()
    payer_wallet_res = await db.execute(payer_wallet_stmt)
    payer_wallet = payer_wallet_res.scalars().first()
    
    if not payer_wallet:
        logger.error(f"Payer wallet not found: {payer_user.id}")
        return

    # 잔액 체크 (혹시 모를 마이너스 방지)
    if payer_wallet.balance < total_dividend:
        # 잔액 부족 시 있는 만큼만 배당? 아니면 강제 마이너스?
        # 일단 있는 만큼만 털어서 배당 (최대치 조정)
        total_dividend = payer_wallet.balance
        logger.warning(f"Payer {payer_user.id} has insufficient funds for full dividend. Adjusted to {total_dividend}")
    
    if total_dividend <= 0:
        return

    sub_balance(payer_wallet, total_dividend, WALLET_REASON_DIVIDEND)
    logger.info(f"Dividend collected from {payer_user.nickname}: {total_dividend} KRW")

    # 5. 배당금 분배 (Bulk 처리를 위해 정보 수집)
    collected_payouts = {} # user_id -> payout_amount
    history_records = [] # List of DividendHistory objects

    for shareholder in shareholders:
        share_ratio = shareholder.quantity / total_shares
        payout = total_dividend * share_ratio
        
        # 소수점 처리 (내림)
        payout = Decimal(int(payout)) 
        
        if payout <= 0:
            continue
            
        # 기존에 해당 주주에게 지급될 배당금이 있다면 합산
        collected_payouts[shareholder.user_id] = collected_payouts.get(shareholder.user_id, Decimal(0)) + payout
        
        history = DividendHistory(
            payer_id=payer_user.id,
            receiver_id=shareholder.user_id,
            ticker_id=ticker_id,
            amount=payout
        )
        history_records.append(history)
            
    # 6. Bulk update receiver wallets
    if collected_payouts:
        # Fetch all receiver wallets in one go and lock them
        receiver_user_ids = [str(uid) for uid in collected_payouts.keys()] # Ensure user_ids are strings/UUIDs as in DB
        receiver_wallets_stmt = select(Wallet).where(Wallet.user_id.in_(receiver_user_ids)).with_for_update()
        receiver_wallets_res = await db.execute(receiver_wallets_stmt)
        receiver_wallets = receiver_wallets_res.scalars().all()

        # Create a dictionary for quick lookup of wallets by user_id
        wallets_by_user_id = {str(w.user_id): w for w in receiver_wallets}

        for user_id, payout_amount in collected_payouts.items():
            wallet = wallets_by_user_id.get(str(user_id))
            if wallet:
                # add_balance directly modifies the wallet object in place
                add_balance(wallet, payout_amount, WALLET_REASON_DIVIDEND)
            else:
                logger.error(f"Receiver wallet not found for user: {user_id}. Cannot distribute dividend.")

    # 7. Bulk insert DividendHistory records
    if history_records:
        db.add_all(history_records)

    logger.info(f"Dividend distribution completed for {ticker_id}")

    # 이벤트 발행 (Human 채널용)
    try:
        redis_client = async_redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)
        event = {
            "type": "dividend_paid",
            "payer_id": str(payer_user.id),
            "payer_nickname": payer_user.nickname,
            "ticker_id": ticker_id,
            "total_dividend": float(total_dividend),
        }
        await publish_event(redis_client, event, channel="human_events")
        await redis_client.close()
    except Exception:
        pass
