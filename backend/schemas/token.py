from typing import Optional
from pydantic import BaseModel

class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: str
    expires_in: int  # Time in seconds until the access token expires

class TokenPayload(BaseModel):
    sub: Optional[str] = None
    type: Optional[str] = None
    exp: Optional[int] = None
    jti: Optional[str] = None  # For refresh token reuse detection

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None

class DiscordExchangeRequest(BaseModel):
    code: str
    redirect_uri: Optional[str] = None
