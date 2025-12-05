from fastapi import APIRouter, Depends
from backend.core.rate_limit_config import get_rate_limiter
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List

from backend.core.database import get_db
from backend.core.deps import get_current_user_id, get_redis # Import get_redis
from backend.schemas.human import IpoCreate, BurnCreate, ShareholderResponse, DividendPaymentEntry, IssuerDividendStats, UpdateDividendRate, HumanCorporateValueResponse
from backend.services.human_service import process_bailout, process_ipo, process_burn, get_shareholders, get_issuer_dividend_stats, get_issuer_dividend_history, update_dividend_rate, get_human_corporate_value
import redis.asyncio as async_redis # Import async_redis


router = APIRouter(prefix="/human", tags=["human_etf"])

@router.get("/corporate_value", response_model=HumanCorporateValueResponse, dependencies=[Depends(get_rate_limiter("/human/corporate_value"))])
async def get_my_corporate_value(
    db: AsyncSession = Depends(get_db),
    redis_client: async_redis.Redis = Depends(get_redis), # Use get_redis
    user_id: UUID = Depends(get_current_user_id)
):
    """
    [기업 가치 조회]
    발행자 본인의 Human ETF의 시장 가치 및 관련 지표를 조회합니다.
    """
    return await get_human_corporate_value(db, redis_client, user_id)

@router.patch("/dividend_rate", dependencies=[Depends(get_rate_limiter("/human/dividend_rate"))])
async def update_my_dividend_rate(
    rate_in: UpdateDividendRate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    [배당률 변경]
    자신의 Human ETF 배당률을 변경합니다.
    - 파산 상태인 경우 최소 50% 이상이어야 합니다.
    """
    return await update_dividend_rate(db, user_id, rate_in)

@router.get("/shareholders", response_model=ShareholderResponse, dependencies=[Depends(get_rate_limiter("/human/shareholders"))])
async def get_my_shareholders(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    [주주 명부 조회]
    자신의 Human ETF를 보유한 주주들의 목록과 지분율을 조회합니다.
    """
    return await get_shareholders(db, user_id)

@router.get("/dividend/stats", response_model=IssuerDividendStats, dependencies=[Depends(get_rate_limiter("/human/dividend/stats"))])
async def get_my_dividend_stats(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    [배당 통계 조회]
    발행자(나)의 현재 배당률 및 누적 배당 지급액을 조회합니다.
    """
    return await get_issuer_dividend_stats(db, user_id)

@router.get("/dividend/history", response_model=List[DividendPaymentEntry], dependencies=[Depends(get_rate_limiter("/human/dividend/history"))])
async def get_my_dividend_history(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    [배당 내역 조회]
    발행자(나)의 최근 배당 지급 내역을 조회합니다.
    """
    return await get_issuer_dividend_history(db, user_id)

@router.post("/bailout", dependencies=[Depends(get_rate_limiter("/human/bailout"))])
async def request_bailout(
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    [긴급 구제 금융 신청]
    - 조건: 파산 상태이며, 발행한 Human ETF 주식이 팔리지 않음.
    - 효과: 시스템 봇이 평가 금액으로 전량 매수.
    """
    return await process_bailout(db, user_id)

@router.post("/ipo", dependencies=[Depends(get_rate_limiter("/human/ipo"))])
async def create_ipo(
    ipo_in: IpoCreate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    [IPO] 자신의 지분을 주식으로 발행합니다.
    - HUMAN_{USER_ID} 티커 생성
    - 입력받은 수량만큼 발행하여 본인 지갑에 입고
    - 파산자는 배당률 50% 이상 필수
    """
    return await process_ipo(db, user_id, ipo_in)

@router.post("/burn", dependencies=[Depends(get_rate_limiter("/human/burn"))])
async def burn_shares(
    burn_in: BurnCreate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id)
):
    """
    [소각] 보유한 자사주(Human ETF)를 소각합니다.
    - 모든 유통 주식을 소각하면 상장 폐지 및 파산 해제(해방)됩니다.
    """
    return await process_burn(db, user_id, burn_in)
