from pydantic import BaseModel

class FxRateResponse(BaseModel):
    base: str
    quote: str
    rate: float
