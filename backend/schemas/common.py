from decimal import Decimal
from typing import Annotated
from pydantic import PlainSerializer, WithJsonSchema

# Decimal 값을 JSON 직렬화 시 문자열(str)로 변환하는 커스텀 타입
# 예: Decimal('100.50') -> "100.50"
DecimalStr = Annotated[
    Decimal,
    PlainSerializer(lambda x: str(x) if x is not None else None, return_type=str),
    WithJsonSchema({"type": "string", "format": "decimal"})
]
