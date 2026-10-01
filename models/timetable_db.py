"""
Timetable Slot model — weekly master schedule per grade and section.
"""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class TimetableSlotDB(Base):
    __tablename__ = "timetable_slots"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    academic_year = Column(String(20), default="2025-26", nullable=False)
    grade = Column(String(10), nullable=False)
    section = Column(String(10), nullable=False)
    day_of_week = Column(Integer, nullable=False)         # 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday, 5=Saturday
    period_number = Column(Integer, nullable=False)       # 1 to 8
    start_time = Column(String(10), nullable=False)       # "08:30"
    end_time = Column(String(10), nullable=False)         # "09:15"
    subject_id = Column(GUID, ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    teacher_id = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    room_number = Column(String(30), nullable=True)       # "Room 102", "Physics Lab"
    slot_type = Column(String(20), default="CLASS", nullable=False) # "CLASS", "BREAK", "LUNCH", "ASSEMBLY"
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(timezone.utc))
    updated_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        UniqueConstraint("school_id", "grade", "section", "day_of_week", "period_number", name="uq_class_period_slot"),
    )

    # Relationships
    subject = relationship("Subject")
    teacher = relationship("UserDB", foreign_keys=[teacher_id])
