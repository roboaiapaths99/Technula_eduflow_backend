"""
Holiday Calendar Model — Dedicated school and official holiday management.
"""
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class HolidayDB(Base):
    __tablename__ = "holidays"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(200), nullable=False)
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)
    holiday_type = Column(String(50), default="festival", nullable=False)  # national, festival, school_break, restricted, emergency
    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
