"""
Datesheet Models — Class and section scoped examination schedules.
"""
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class DatesheetDB(Base):
    __tablename__ = "datesheets"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(255), nullable=False)  # e.g. "Term 1 Mid-Term Examination 2026"
    grade = Column(String(10), nullable=False, index=True)  # e.g. "10" or "ALL"
    section = Column(String(10), default="ALL", nullable=False)  # e.g. "A" or "ALL"
    academic_year = Column(String(20), default="2025-26", nullable=False)
    pdf_url = Column(String(500), nullable=True)

    is_published = Column(Boolean, default=False, nullable=False, index=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    entries = relationship("DatesheetEntryDB", back_populates="datesheet", cascade="all, delete-orphan", order_by="DatesheetEntryDB.exam_date")
    author = relationship("UserDB", foreign_keys=[created_by])


class DatesheetEntryDB(Base):
    __tablename__ = "datesheet_entries"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    datesheet_id = Column(GUID, ForeignKey("datesheets.id", ondelete="CASCADE"), nullable=False, index=True)

    subject_name = Column(String(100), nullable=False)
    subject_code = Column(String(30), nullable=True)
    exam_date = Column(Date, nullable=False, index=True)
    start_time = Column(String(30), nullable=False)  # e.g. "09:30 AM"
    end_time = Column(String(30), nullable=False)    # e.g. "12:30 PM"
    venue = Column(String(100), nullable=True)       # e.g. "Examination Hall B"
    syllabus_remarks = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)

    datesheet = relationship("DatesheetDB", back_populates="entries")
