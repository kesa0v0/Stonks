from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from fastapi import HTTPException, status

from backend.models import (
    VoteProposal,
    Vote,
    VoteProposalStatus,
    VoteProposalType,
    Ticker,
    Portfolio,
)
from backend.schemas.vote import VoteProposalCreate, VoteCastRequest, ProposalDetail, ProposalTally


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_locked_quantity(db: AsyncSession, user_id, ticker_id: str) -> Decimal:
    """Return total quantity locked in active votes for this user and ticker."""
    now = _utcnow()
    stmt = (
        select(func.coalesce(func.sum(Vote.quantity), 0))
        .join(VoteProposal, Vote.proposal_id == VoteProposal.id)
        .where(
            Vote.user_id == user_id,
            VoteProposal.ticker_id == ticker_id,
            VoteProposal.status == VoteProposalStatus.PENDING,
            VoteProposal.start_at <= now,
            VoteProposal.end_at >= now,
        )
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none() or Decimal(0)


async def create_proposal(db: AsyncSession, user_id, payload: VoteProposalCreate) -> VoteProposal:
    ticker_res = await db.execute(select(Ticker).where(Ticker.id == payload.ticker_id))
    ticker = ticker_res.scalars().first()
    if not ticker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticker not found")

    start_at = payload.start_at or _utcnow()
    if payload.end_at <= start_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end_at must be after start_at")

    proposal = VoteProposal(
        ticker_id=payload.ticker_id,
        proposer_id=user_id,
        title=payload.title,
        description=payload.description,
        vote_type=payload.vote_type,
        target_value=payload.target_value,
        start_at=start_at,
        end_at=payload.end_at,
        status=VoteProposalStatus.PENDING,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal


async def list_proposals(db: AsyncSession, ticker_id: Optional[str] = None, status_filter: Optional[VoteProposalStatus] = None) -> List[VoteProposal]:
    stmt = select(VoteProposal)
    if ticker_id:
        stmt = stmt.where(VoteProposal.ticker_id == ticker_id)
    if status_filter:
        stmt = stmt.where(VoteProposal.status == status_filter)
    stmt = stmt.order_by(VoteProposal.end_at.desc())
    res = await db.execute(stmt)
    return res.scalars().all()


async def get_proposal(db: AsyncSession, proposal_id) -> VoteProposal:
    res = await db.execute(select(VoteProposal).where(VoteProposal.id == proposal_id))
    proposal = res.scalars().first()
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    return proposal


async def _get_vote(db: AsyncSession, proposal_id, user_id) -> Optional[Vote]:
    res = await db.execute(select(Vote).where(and_(Vote.proposal_id == proposal_id, Vote.user_id == user_id)))
    return res.scalars().first()


async def cast_vote(db: AsyncSession, proposal_id, user_id, body: VoteCastRequest) -> Vote:
    proposal = await get_proposal(db, proposal_id)
    now = _utcnow()
    if proposal.status != VoteProposalStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Proposal is not open for voting")
    if not (proposal.start_at <= now <= proposal.end_at):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Voting window is closed")

    # Portfolio and available stake
    pf_res = await db.execute(select(Portfolio).where(and_(Portfolio.user_id == user_id, Portfolio.ticker_id == proposal.ticker_id)))
    pf = pf_res.scalars().first()
    portfolio_qty = pf.quantity if pf else Decimal(0)

    existing_vote = await _get_vote(db, proposal_id, user_id)
    current_locked = await get_locked_quantity(db, user_id, proposal.ticker_id)
    locked_excluding_this = current_locked - (existing_vote.quantity if existing_vote else Decimal(0))
    available = portfolio_qty - locked_excluding_this
    if body.quantity > available:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not enough unlocked shares to stake for vote")

    if existing_vote:
        existing_vote.choice = body.choice
        existing_vote.quantity = body.quantity
        vote_obj = existing_vote
    else:
        vote_obj = Vote(
            proposal_id=proposal_id,
            user_id=user_id,
            choice=body.choice,
            quantity=body.quantity,
        )
        db.add(vote_obj)

    await db.commit()
    await db.refresh(vote_obj)
    return vote_obj


async def unvote(db: AsyncSession, proposal_id, user_id):
    proposal = await get_proposal(db, proposal_id)
    now = _utcnow()
    if proposal.status != VoteProposalStatus.PENDING or now > proposal.end_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot unvote after proposal closed")

    existing_vote = await _get_vote(db, proposal_id, user_id)
    if not existing_vote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vote not found")

    await db.delete(existing_vote)
    await db.commit()
    return {"message": "Vote removed"}


async def tally_proposal(db: AsyncSession, proposal_id) -> ProposalTally:
    stmt_yes = select(func.coalesce(func.sum(Vote.quantity), 0)).where(and_(Vote.proposal_id == proposal_id, Vote.choice.is_(True)))
    stmt_no = select(func.coalesce(func.sum(Vote.quantity), 0)).where(and_(Vote.proposal_id == proposal_id, Vote.choice.is_(False)))
    yes = (await db.execute(stmt_yes)).scalar_one_or_none() or Decimal(0)
    no = (await db.execute(stmt_no)).scalar_one_or_none() or Decimal(0)
    return ProposalTally(yes=str(yes), no=str(no))


async def settle_proposal(db: AsyncSession, proposal_id):
    proposal = await get_proposal(db, proposal_id)
    now = _utcnow()
    if proposal.status != VoteProposalStatus.PENDING:
        return proposal
    if now < proposal.end_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Proposal not ended yet")

    tally = await tally_proposal(db, proposal_id)
    yes = Decimal(str(tally.yes))
    no = Decimal(str(tally.no))
    proposal.status = VoteProposalStatus.PASSED if yes > no else VoteProposalStatus.REJECTED
    proposal.updated_at = now
    await db.commit()
    await db.refresh(proposal)
    return proposal


async def get_proposal_detail(db: AsyncSession, proposal_id, user_id) -> ProposalDetail:
    proposal = await get_proposal(db, proposal_id)
    tally = await tally_proposal(db, proposal_id)
    my_vote = await _get_vote(db, proposal_id, user_id)
    return ProposalDetail(
        id=str(proposal.id),
        ticker_id=proposal.ticker_id,
        title=proposal.title,
        description=proposal.description,
        vote_type=proposal.vote_type,
        target_value=proposal.target_value,
        start_at=proposal.start_at,
        end_at=proposal.end_at,
        status=proposal.status,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        tally=tally,
        my_vote=my_vote,
    )
