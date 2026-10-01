"""
School Almanac & Institutional Documents Model.
Features category tagging and validity date window enforcement.
"""
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Integer, BigInteger
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class AlmanacDB(Base):
    __tablename__ = "almanac"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(255), nullable=False)
    category = Column(String(50), nullable=False, index=True)  # holiday_list, event_calendar, rules, syllabus, handbook, general
    target_grade = Column(String(50), default="ALL", nullable=False)  # "ALL" or specific grade
    academic_year = Column(String(20), default="2025-26", nullable=False)

    file_url = Column(String(500), nullable=False)
    file_size = Column(BigInteger, default=0, nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=False)

    version = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    author = relationship("UserDB", foreign_keys=[created_by])
