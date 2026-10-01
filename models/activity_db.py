"""
Activity & Events Feed Model — Visual chronological timeline of campus events.
"""
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class ActivityDB(Base):
    __tablename__ = "activities"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    event_date = Column(Date, nullable=False, index=True)
    target_grade = Column(String(50), default="ALL", nullable=False)  # "ALL" or specific grade
    category = Column(String(50), default="cultural", nullable=False)  # sports, cultural, workshop, competition, celebration, ptm, academic
    cover_image_url = Column(String(500), nullable=True)
    linked_album_id = Column(GUID, ForeignKey("gallery_albums.id", ondelete="SET NULL"), nullable=True)

    is_published = Column(Boolean, default=True, nullable=False, index=True)
    created_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    author = relationship("UserDB", foreign_keys=[created_by])
    linked_album = relationship("GalleryAlbumDB", foreign_keys=[linked_album_id])
