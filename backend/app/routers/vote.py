from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.deps import get_db, get_current_user_id
from backend.core.rate_limit_config import get_rate_limiter
from backend.schemas.vote import (
    VoteProposalCreate,
    VoteProposalOut,
    VoteCastRequest,
    VoteOut,
    ProposalDetail,
    ProposalList,
)
from backend.models.vote import VoteProposalStatus
from backend.services.vote_service import (
    create_proposal,
    list_proposals,
    cast_vote,
    unvote,
    settle_proposal,
    get_proposal_detail,
)

router = APIRouter(prefix="/votes", tags=["votes"])


@router.post("/proposals", response_model=VoteProposalOut, dependencies=[Depends(get_rate_limiter("/votes/proposals"))])
async def create_vote_proposal(
    body: VoteProposalCreate,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return await create_proposal(db, user_id, body)


@router.get("/proposals", response_model=ProposalList, dependencies=[Depends(get_rate_limiter("/votes/proposals:list"))])
async def list_vote_proposals(
    ticker_id: Optional[str] = None,
    status: Optional[VoteProposalStatus] = None,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    items = await list_proposals(db, ticker_id=ticker_id, status_filter=status)
    return {"items": items}


@router.get("/proposals/{proposal_id}", response_model=ProposalDetail, dependencies=[Depends(get_rate_limiter("/votes/proposals/detail"))])
async def get_vote_proposal_detail(
    proposal_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return await get_proposal_detail(db, proposal_id, user_id)


@router.post("/proposals/{proposal_id}/vote", response_model=VoteOut, dependencies=[Depends(get_rate_limiter("/votes/proposals/vote"))])
async def vote_on_proposal(
    proposal_id: UUID,
    body: VoteCastRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    vote_obj = await cast_vote(db, proposal_id, user_id, body)
    return vote_obj


@router.post("/proposals/{proposal_id}/unvote", dependencies=[Depends(get_rate_limiter("/votes/proposals/unvote"))])
async def unvote_proposal(
    proposal_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    return await unvote(db, proposal_id, user_id)


@router.post("/proposals/{proposal_id}/settle", response_model=VoteProposalOut, dependencies=[Depends(get_rate_limiter("/votes/proposals/settle"))])
async def settle_vote_proposal(
    proposal_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    proposal = await settle_proposal(db, proposal_id)
    return proposal
