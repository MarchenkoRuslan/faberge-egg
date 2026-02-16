from enum import Enum

from pydantic import BaseModel


class PaymentMethod(str, Enum):
    STRIPE = "stripe"
    PAYKILLA = "paykilla"


class OrderCreateRequest(BaseModel):
    lot_id: int
    fraction_count: int
    payment_method: PaymentMethod
    return_url: str | None = None
    cancel_url: str | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "lot_id": 1,
                    "fraction_count": 100,
                    "payment_method": "stripe",
                    "return_url": "https://frontend.example.com/success",
                    "cancel_url": "https://frontend.example.com/cancel",
                }
            ]
        }
    }


class OrderCreateResponse(BaseModel):
    order_id: int
    checkout_url: str | None = None
    session_id: str | None = None
    payment_method: PaymentMethod


class OrderResponse(BaseModel):
    id: int
    lot_id: int
    fraction_count: int
    amount_eur_cents: int
    payment_method: PaymentMethod
    status: str
    created_at: str

    model_config = {"from_attributes": True}


class OrderStatusResponse(BaseModel):
    id: int
    status: str
    fraction_count: int
    amount_eur_cents: int


class PaymentMethodsResponse(BaseModel):
    available_methods: list[PaymentMethod]
    enabled_methods: list[PaymentMethod]
