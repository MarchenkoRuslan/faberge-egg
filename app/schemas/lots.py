from decimal import Decimal
from pydantic import BaseModel


class LotListResponse(BaseModel):
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


class LotDetailResponse(BaseModel):
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
