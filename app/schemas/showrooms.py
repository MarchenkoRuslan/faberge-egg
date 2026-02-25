from decimal import Decimal
from typing import Any

from pydantic import BaseModel, field_serializer


class AssetMediaResponse(BaseModel):
    kind: str
    media_type: str
    url: str | None
    filename: str | None = None
    alt_text: str | None = None

    model_config = {"from_attributes": True}


class AssetLotResponse(BaseModel):
    id: int
    slug: str
    total_fractions: int
    special_price_fractions_cap: int
    remaining_special_fractions: int
    price_special_eur: Decimal
    price_nominal_eur: Decimal
    min_fractions_to_buy: int
    is_active: bool

    @field_serializer("price_special_eur", "price_nominal_eur")
    def serialize_price(self, value: Decimal) -> str:
        normalized = value.normalize()
        return format(normalized, "f")

    model_config = {"from_attributes": True}


class AssetListResponse(BaseModel):
    slug: str
    name: str
    headline: str | None = None
    hero_image: AssetMediaResponse | None = None

    model_config = {"from_attributes": True}


class AssetDetailResponse(BaseModel):
    slug: str
    name: str
    headline: str | None = None
    description: str | None = None
    meta: dict[str, Any] | None = None
    media: list[AssetMediaResponse] = []
    lot: AssetLotResponse | None = None

    model_config = {"from_attributes": True}


class ShowroomListResponse(BaseModel):
    slug: str
    name: str
    headline: str | None = None

    model_config = {"from_attributes": True}


class ShowroomDetailResponse(BaseModel):
    slug: str
    name: str
    headline: str | None = None
    description: str | None = None
    meta: dict[str, Any] | None = None
    assets: list[AssetDetailResponse] = []

    model_config = {"from_attributes": True}
