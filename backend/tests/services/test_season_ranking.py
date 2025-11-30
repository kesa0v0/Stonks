import pytest
from decimal import Decimal
from sqlalchemy import select
from backend.services.season_service import get_active_season, end_current_season
from backend.services.ranking_service import update_user_persona, get_rankings_data
from backend.models import User, Wallet, UserPersona
from backend.core.enums import OrderType
import uuid

@pytest.mark.asyncio
async def test_season_lifecycle_and_ranking(db_session):
    # 1. Create Users
    u1_id = uuid.uuid4()
    u2_id = uuid.uuid4()
    u1 = User(id=u1_id, email="u1@test.com", nickname="Winner", hashed_password="x", is_active=True)
    u2 = User(id=u2_id, email="u2@test.com", nickname="Loser", hashed_password="x", is_active=True)
    db_session.add(u1)
    db_session.add(u2)
    db_session.add(Wallet(user_id=u1_id, balance=Decimal("0")))
    db_session.add(Wallet(user_id=u2_id, balance=Decimal("0")))
    await db_session.commit()
    await db_session.refresh(u1)
    await db_session.refresh(u2)

    # 2. Get Active Season (Should create Season 1)
    s1 = await get_active_season(db_session)
    assert s1.name == "Season 1"
    assert s1.is_active is True

    # 3. Update Stats for Season 1
    # U1 wins big
    await update_user_persona(db_session, u1.id, OrderType.LIMIT, pnl=Decimal("1000"))
    # U2 wins small
    await update_user_persona(db_session, u2.id, OrderType.LIMIT, pnl=Decimal("100"))
    await db_session.commit()

    # 4. Check Ranking for Season 1
    rankings_s1 = await get_rankings_data(db_session, "pnl", 10)
    assert len(rankings_s1) == 2
    assert rankings_s1[0].nickname == "Winner"
    assert rankings_s1[0].value == 1000

    # 5. End Season 1 -> Start Season 2
    # This should reward U1
    s2 = await end_current_season(db_session)
    assert s2.name == "Season 2"
    assert s2.is_active is True
    
    # Verify Season 1 is inactive
    await db_session.refresh(s1)
    assert s1.is_active is False

    # 6. Verify Rewards (U1 should have badge and money)
    await db_session.refresh(u1, attribute_names=["wallet"])
    
    assert u1.wallet.balance == Decimal("10000000") # Rank 1 Reward
    assert len(u1.badges) == 1
    assert u1.badges[0]['rank'] == 1
    assert "Season 1" in u1.badges[0]['title']

    # 7. Update Stats for Season 2
    # U2 wins big this time
    await update_user_persona(db_session, u2.id, OrderType.LIMIT, pnl=Decimal("5000"))
    await db_session.commit()

    # 8. Check Ranking for Season 2
    rankings_s2 = await get_rankings_data(db_session, "pnl", 10)
    assert rankings_s2[0].nickname == "Loser"
    assert rankings_s2[0].value == 5000
    
    # Verify Season 1 stats are not mixed
    # Fetch Season 1 ranking explicitly
    rankings_s1_explicit = await get_rankings_data(db_session, "pnl", 10, season_id=s1.id)
    assert rankings_s1_explicit[0].nickname == "Winner"
    assert rankings_s1_explicit[0].value == 1000
