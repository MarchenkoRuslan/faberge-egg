from datetime import datetime

from pydantic import BaseModel


class ProvenanceEntry(BaseModel):
    id: int
    transfer_type: str
    fraction_count: int
    from_display: str | None
    to_display: str
    blockchain_tx_hash: str | None
    blockchain_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ProvenanceResponse(BaseModel):
    asset_slug: str
    total: int
    items: list[ProvenanceEntry]
