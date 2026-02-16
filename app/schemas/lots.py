from decimal import Decimal
from pydantic import BaseModel, field_serializer


class _LotBaseResponse(BaseModel):
    @field_serializer("price_special_eur", "price_nominal_eur", check_fields=False)
    def serialize_price(self, value: Decimal) -> str:
        normalized = value.normalize()
        return format(normalized, "f")


class LotListResponse(_LotBaseResponse):
    id: int
    name: str
    slug: str
    total_fractions: int
    special_price_fractions_cap: int
    remaining_special_fractions: int
    price_special_eur: Decimal
    price_nominal_eur: Decimal
    min_fractions_to_buy: int
    is_active: bool

    model_config = {"from_attributes": True}


class LotDetailResponse(_LotBaseResponse):
    id: int
    name: str
    slug: str
    total_fractions: int
    special_price_fractions_cap: int
    remaining_special_fractions: int
    price_special_eur: Decimal
    price_nominal_eur: Decimal
    min_fractions_to_buy: int
    is_active: bool

    model_config = {"from_attributes": True}
