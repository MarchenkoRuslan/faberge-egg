from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class FractionTransfer(Base):
    __tablename__ = "fraction_transfers"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(
        Integer, ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    from_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True,
    )
    to_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    fraction_count = Column(Integer, nullable=False)
    transfer_type = Column(String(50), nullable=False)
    order_id = Column(
        Integer, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=True,
    )
    blockchain_tx_hash = Column(String(255), nullable=True)
    blockchain_status = Column(String(50), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    asset = relationship("Asset", back_populates="fraction_transfers")
    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])
    order = relationship("Order")
