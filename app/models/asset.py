from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    showroom_id = Column(Integer, ForeignKey("showrooms.id"), nullable=False)
    slug = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    headline = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    meta = Column(JSON, nullable=True)
    status = Column(String(50), nullable=False, default="active")
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    showroom = relationship("Showroom", back_populates="assets")
    media = relationship(
        "AssetMedia",
        back_populates="asset",
        order_by="AssetMedia.sort_order",
    )
    lots = relationship("Lot", back_populates="asset")
