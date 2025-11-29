from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from backend.core.database import get_db
from backend.core.deps import get_current_user_id
from backend.schemas.human import IpoCreate, BurnCreate
from backend.services.human_service import process_bailout, process_ipo, process_burn

router = APIRouter(prefix="/human", tags=["human_etf"])

@router.post("/bailout")
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

@router.post("/ipo")
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

@router.post("/burn")
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
