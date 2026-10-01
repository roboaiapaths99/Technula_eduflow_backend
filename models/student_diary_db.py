"""
Student Diary model — for teacher remarks, appreciations, concerns, and parent acknowledgements.
"""
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone, date


class StudentDiaryEntryDB(Base):
    __tablename__ = "student_diary_entries"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(GUID, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    teacher_user_id = Column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    entry_date = Column(Date, default=lambda: datetime.now(timezone.utc).date(), nullable=False)
    category = Column(String(50), default="APPRECIATION", nullable=False)  # APPRECIATION, NEEDS_ATTENTION, ACADEMIC, HEALTH, DISCIPLINE
    title = Column(String(255), nullable=True)
    remark = Column(Text, nullable=False)
    action_required = Column(Boolean, default=False, nullable=False)
    is_parent_visible = Column(Boolean, default=True, nullable=False)
    acknowledged_by_parent = Column(Boolean, default=False, nullable=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    school = relationship("SchoolDB")
    student = relationship("StudentDB", back_populates="diary_entries")
    teacher = relationship("UserDB", foreign_keys=[teacher_user_id])
