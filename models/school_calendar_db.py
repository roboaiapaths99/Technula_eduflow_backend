"""
School Calendar Event model — holidays, examinations, parent-teacher meetings, and vacations.
"""
from sqlalchemy import Column, String, Boolean, Date, DateTime, ForeignKey, Text
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class SchoolCalendarEventDB(Base):
    __tablename__ = "school_calendar_events"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False)               # Equal to start_date for 1-day events
    event_type = Column(String(50), default="HOLIDAY", nullable=False) # "HOLIDAY", "EXAM", "PTM", "SPORTS", "VACATION", "OTHER"
    is_holiday = Column(Boolean, default=True, nullable=False)         # School closed
    affects_attendance = Column(Boolean, default=True, nullable=False) # Exclude from working days denominator
    target_grades = Column(String(100), default="ALL", nullable=False) # "ALL" or "10,11"
    description = Column(Text, nullable=True)
    created_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
