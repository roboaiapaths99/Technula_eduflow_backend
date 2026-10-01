"""
Announcement model — school-wide announcements with multi-channel delivery.
"""
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class AnnouncementDB(Base):
    __tablename__ = "announcements"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    target_role = Column(String(50), default="ALL", nullable=False)  # ALL, PARENTS, TEACHERS, GRADE_10
    target_grade = Column(String(10), nullable=True)  # Optional grade filter
    send_whatsapp = Column(Boolean, default=False, nullable=False)
    send_email = Column(Boolean, default=False, nullable=False)
    send_push = Column(Boolean, default=False, nullable=False)
    is_pinned = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
