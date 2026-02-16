from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.models.database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    lot_id = Column(Integer, ForeignKey("lots.id"), nullable=False)
    fraction_count = Column(Integer, nullable=False)
    amount_eur_cents = Column(Integer, nullable=False)
    payment_method = Column(String(50), nullable=False)  # stripe | paykilla
    status = Column(String(50), nullable=False, default="pending")  # pending | paid | failed | cancelled
    external_payment_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
