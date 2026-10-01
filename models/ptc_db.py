import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Date, DateTime, Text, Boolean, ForeignKey
from db.base import Base, GUID

class PTCEventDB(Base):
    """Parent-Teacher Conference Event announced by administration"""
    __tablename__ = "ptc_events"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    event_date = Column(Date, nullable=False)
    start_time = Column(String(16), default="09:00")
    end_time = Column(String(16), default="13:00")
    slot_duration_mins = Column(Integer, default=15)
    grade = Column(String(16), nullable=True) # None = all grades
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PTCSlotDB(Base):
    """Specific 15-minute slot for a teacher during a PTC event"""
    __tablename__ = "ptc_slots"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    event_id = Column(GUID, ForeignKey("ptc_events.id", ondelete="CASCADE"), nullable=False, index=True)
    teacher_id = Column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    start_time = Column(String(16), nullable=False) # e.g. "09:15"
    end_time = Column(String(16), nullable=False)   # e.g. "09:30"
    is_booked = Column(Boolean, default=False)
    room_or_link = Column(String(120), default="Room 102")


class PTCBookingDB(Base):
    """Parent booking of a PTC slot"""
    __tablename__ = "ptc_bookings"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    slot_id = Column(GUID, ForeignKey("ptc_slots.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    event_id = Column(GUID, ForeignKey("ptc_events.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(GUID, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    parent_user_id = Column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agenda_topic = Column(String(255), nullable=True)
    status = Column(String(32), default="CONFIRMED") # CONFIRMED | CANCELLED | COMPLETED
    teacher_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
