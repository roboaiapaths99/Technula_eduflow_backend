"""
Attendance model — daily student attendance with status and reason.
"""
from sqlalchemy import Column, String, Date, DateTime, Text, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class AttendanceDB(Base):
    __tablename__ = "attendance"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(GUID, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False)  # Present, Absent, Late, HalfDay
    reason = Column(Text, nullable=True)
    marked_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(timezone.utc))
    updated_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        UniqueConstraint("school_id", "student_id", "date", name="uq_attendance_student_date"),
        Index("ix_attendance_school_date_status", "school_id", "date", "status"),
    )

    # Relationships
    student = relationship("StudentDB", back_populates="attendance_records")
