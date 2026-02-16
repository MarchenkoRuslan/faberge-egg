from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Lot, get_db
from app.schemas.lots import LotDetailResponse, LotListResponse

router = APIRouter()


def lot_to_list_response(lot: Lot) -> LotListResponse:
    remaining = max(0, lot.special_price_fractions_cap - lot.sold_special_fractions)
    return LotListResponse(
        id=lot.id,
        name=lot.name,
        slug=lot.slug,
        total_fractions=lot.total_fractions,
        special_price_fractions_cap=lot.special_price_fractions_cap,
        remaining_special_fractions=remaining,
        price_special_eur=lot.price_special_eur,
        price_nominal_eur=lot.price_nominal_eur,
        min_fractions_to_buy=settings.MIN_FRACTIONS,
        is_active=lot.is_active,
    )


def lot_to_detail_response(lot: Lot) -> LotDetailResponse:
    remaining = max(0, lot.special_price_fractions_cap - lot.sold_special_fractions)
    return LotDetailResponse(
        id=lot.id,
        name=lot.name,
        slug=lot.slug,
        total_fractions=lot.total_fractions,
        special_price_fractions_cap=lot.special_price_fractions_cap,
        remaining_special_fractions=remaining,
        price_special_eur=lot.price_special_eur,
        price_nominal_eur=lot.price_nominal_eur,
        min_fractions_to_buy=settings.MIN_FRACTIONS,
        is_active=lot.is_active,
    )


@router.get(
    "",
    response_model=list[LotListResponse],
    summary="List all lots",
)
def list_lots(
    db: Annotated[Session, Depends(get_db)],
):
    """Returns all active lots with remaining special fractions and prices."""
    lots = db.query(Lot).filter(Lot.is_active == True).all()
    return [lot_to_list_response(lot) for lot in lots]


@router.get(
    "/{lot_id}",
    response_model=LotDetailResponse,
    summary="Get lot by ID",
)
def get_lot(
    lot_id: int,
    db: Annotated[Session, Depends(get_db)],
):
    """Returns one lot with full details for the object card (remaining fractions, prices, limits)."""
    lot = db.query(Lot).filter(Lot.id == lot_id, Lot.is_active == True).first()
    if not lot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lot not found")
    return lot_to_detail_response(lot)
