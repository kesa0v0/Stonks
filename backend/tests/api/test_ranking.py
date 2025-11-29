import pytest
from httpx import AsyncClient
from decimal import Decimal
from sqlalchemy import select
from backend.models import User, UserPersona
from backend.core.enums import OrderType
from backend.services.ranking_service import update_user_persona
from backend.core.security import create_access_token
import uuid

@pytest.mark.asyncio
async def test_ranking_service_update(db_session):
    """
    Test that update_user_persona correctly updates user statistics.
    """
    # 1. Create User
    user_id = uuid.uuid4()
    user = User(id=user_id, email="ranker@test.com", hashed_password="pw", nickname="Ranker", is_active=True)
    db_session.add(user)
    await db_session.commit()
    
    # 2. First Trade (Market Buy)
    await update_user_persona(
        db=db_session,
        user_id=user_id,
        order_type=OrderType.MARKET,
        pnl=None, # No PnL on buy
        fee=Decimal("100.0")
    )
    await db_session.commit() # Explicit commit required
    
    # Verify
    result = await db_session.execute(select(UserPersona).where(UserPersona.user_id == user_id))
    persona = result.scalars().first()
    assert persona is not None
    assert persona.total_trade_count == 1
    assert persona.market_order_count == 1
    assert persona.total_fees_paid == 100.0
    
    # 3. Second Trade (Limit Sell, Win)
    await update_user_persona(
        db=db_session,
        user_id=user_id,
        order_type=OrderType.LIMIT,
        pnl=Decimal("5000.0"), # Profit
        fee=Decimal("50.0")
    )
    await db_session.commit() # Explicit commit required
    
    # Verify Update
    await db_session.refresh(persona)
    assert persona.total_trade_count == 2
    assert persona.limit_order_count == 1
    assert persona.win_count == 1
    assert persona.total_profit == 5000.0
    assert persona.best_trade_pnl == 5000.0
    assert persona.total_fees_paid == 150.0

    # 4. Third Trade (Loss)
    await update_user_persona(
        db=db_session,
        user_id=user_id,
        order_type=OrderType.MARKET,
        pnl=Decimal("-2000.0"), # Loss
        fee=Decimal("10.0")
    )
    await db_session.commit() # Explicit commit required
    
    await db_session.refresh(persona)
    assert persona.loss_count == 1
    assert persona.total_loss == 2000.0 # Stored as positive
    assert persona.worst_trade_pnl == -2000.0


@pytest.mark.asyncio
async def test_ranking_api(client: AsyncClient, db_session):
    """
    Test GET /rankings endpoint with multiple users.
    """
    # 1. Setup Users and Personas
    # User A: High Profit (10000)
    user_a = User(id=uuid.uuid4(), email="a@t.com", hashed_password="pw", nickname="Ace", is_active=True)
    persona_a = UserPersona(
        user_id=user_a.id, 
        total_realized_pnl=10000, 
        total_profit=10000,
        total_loss=0, 
        total_trade_count=20, 
        win_count=15, 
        loss_count=5,
        # Initialize other fields
        total_fees_paid=0,
        short_position_count=0, long_position_count=0,
        market_order_count=0, limit_order_count=0,
        night_trade_count=0, panic_sell_count=0,
        best_trade_pnl=0, worst_trade_pnl=0,
        top_buyer_count=0, bottom_seller_count=0
    ) # Win Rate: 75%
    
    # User B: High Loss (5000)
    user_b = User(id=uuid.uuid4(), email="b@t.com", hashed_password="pw", nickname="Bomb", is_active=True)
    persona_b = UserPersona(
        user_id=user_b.id, 
        total_realized_pnl=-5000, 
        total_profit=3000,
        total_loss=8000, 
        total_trade_count=100, 
        win_count=20, 
        loss_count=80,
        # Initialize other fields
        total_fees_paid=0,
        short_position_count=0, long_position_count=0,
        market_order_count=0, limit_order_count=0,
        night_trade_count=0, panic_sell_count=0,
        best_trade_pnl=0, worst_trade_pnl=0,
        top_buyer_count=0, bottom_seller_count=0
    ) # Win Rate: 20%, Volume: 100
    
    # User C: High Win Rate (100%) but low volume
    user_c = User(id=uuid.uuid4(), email="c@t.com", hashed_password="pw", nickname="Champ", is_active=True)
    persona_c = UserPersona(
        user_id=user_c.id, 
        total_realized_pnl=500, 
        total_profit=500,
        total_loss=0, 
        total_trade_count=10, 
        win_count=10, 
        loss_count=0,
        # Initialize other fields
        total_fees_paid=0,
        short_position_count=0, long_position_count=0,
        market_order_count=0, limit_order_count=0,
        night_trade_count=0, panic_sell_count=0,
        best_trade_pnl=0, worst_trade_pnl=0,
        top_buyer_count=0, bottom_seller_count=0
    ) # Win Rate: 100%
    
    db_session.add_all([user_a, user_b, user_c, persona_a, persona_b, persona_c])
    await db_session.commit()
    
    # 2. Test PnL Ranking (Ace -> Champ -> Bomb)
    response = await client.get("/rankings/pnl")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["nickname"] == "Ace"
    assert data[0]["value"] == 10000.0
    assert data[1]["nickname"] == "Champ"
    assert data[2]["nickname"] == "Bomb"
    
    # 3. Test Loss Ranking (Bomb -> others)
    response = await client.get("/rankings/loss")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["nickname"] == "Bomb"
    
    # 4. Test Volume Ranking (Bomb -> Ace -> Champ)
    response = await client.get("/rankings/volume")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["nickname"] == "Bomb"
    assert data[0]["value"] == 100.0
    
    # 5. Test Win Rate Ranking (Champ 100% -> Ace 75% -> Bomb 20%)
    response = await client.get("/rankings/win_rate")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["nickname"] == "Champ"
    assert data[0]["value"] == 100.0
    assert data[1]["nickname"] == "Ace"
    assert data[1]["value"] == 75.0
