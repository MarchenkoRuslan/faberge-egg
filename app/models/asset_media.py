from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class AssetMedia(Base):
    __tablename__ = "asset_media"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    kind = Column(String(50), nullable=False)
    media_type = Column(String(50), nullable=False)
    storage_key = Column(String(1024), nullable=False)
    filename = Column(String(255), nullable=True)
    alt_text = Column(String(500), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    asset = relationship("Asset", back_populates="media")
