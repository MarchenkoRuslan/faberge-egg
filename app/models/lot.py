from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime
from sqlalchemy.sql import func

from app.models.database import Base


class Lot(Base):
    __tablename__ = "lots"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, index=True, nullable=False)
    total_fractions = Column(Integer, nullable=False)
    special_price_fractions_cap = Column(Integer, nullable=False)
    price_special_eur = Column(Numeric(10, 4), nullable=False)
    price_nominal_eur = Column(Numeric(10, 4), nullable=False)
    sold_special_fractions = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
