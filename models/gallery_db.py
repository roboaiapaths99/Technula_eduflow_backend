"""
Photo Gallery & Album Models — Rich visual galleries with class/event scoping.
"""
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class GalleryAlbumDB(Base):
    __tablename__ = "gallery_albums"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    event_date = Column(Date, nullable=False, index=True)
    target_grade = Column(String(50), default="ALL", nullable=False)  # "ALL" or specific grade
    cover_photo_url = Column(String(500), nullable=True)

    created_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    photos = relationship("GalleryPhotoDB", back_populates="album", cascade="all, delete-orphan", order_by="GalleryPhotoDB.sort_order")
    author = relationship("UserDB", foreign_keys=[created_by])


class GalleryPhotoDB(Base):
    __tablename__ = "gallery_photos"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    album_id = Column(GUID, ForeignKey("gallery_albums.id", ondelete="CASCADE"), nullable=False, index=True)

    image_url = Column(String(500), nullable=False)
    caption = Column(String(255), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    album = relationship("GalleryAlbumDB", back_populates="photos")
