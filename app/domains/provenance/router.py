from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Asset
from app.models.blockchain_wallet import BlockchainWallet
from app.models.fraction_transfer import FractionTransfer
from app.models.user import User
from app.domains.provenance.schemas import ProvenanceEntry, ProvenanceResponse
from app.domains.provenance.service import resolve_display_name

router = APIRouter()

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@router.get(
    "/{slug}/provenance",
    response_model=ProvenanceResponse,
    summary="Get provenance (transfer history) for an asset",
)
def get_asset_provenance(
    slug: str,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    asset = db.query(Asset).filter(Asset.slug == slug).first()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )

    total = db.query(FractionTransfer).filter(
        FractionTransfer.asset_id == asset.id,
    ).count()

    transfers = (
        db.query(FractionTransfer)
        .filter(FractionTransfer.asset_id == asset.id)
        .order_by(FractionTransfer.created_at.desc(), FractionTransfer.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    if not transfers:
        return ProvenanceResponse(asset_slug=slug, total=total, items=[])

    user_ids = set()
    for t in transfers:
        if t.from_user_id is not None:
            user_ids.add(t.from_user_id)
        user_ids.add(t.to_user_id)

    users = db.query(User.id, User.display_name).filter(User.id.in_(user_ids)).all()
    display_names: dict[int, str | None] = {u.id: u.display_name for u in users}

    wallets = (
        db.query(BlockchainWallet.user_id, BlockchainWallet.address)
        .filter(BlockchainWallet.user_id.in_(user_ids))
        .all()
    )
    wallet_addresses: dict[int, str] = {w.user_id: w.address for w in wallets}

    items = [
        ProvenanceEntry(
            id=t.id,
            transfer_type=t.transfer_type,
            fraction_count=t.fraction_count,
            from_display=resolve_display_name(
                t.from_user_id, display_names, wallet_addresses,
            ),
            to_display=resolve_display_name(
                t.to_user_id, display_names, wallet_addresses,
            ) or f"user#{t.to_user_id}",
            blockchain_tx_hash=t.blockchain_tx_hash,
            blockchain_status=t.blockchain_status,
            created_at=t.created_at,
        )
        for t in transfers
    ]

    return ProvenanceResponse(asset_slug=slug, total=total, items=items)
