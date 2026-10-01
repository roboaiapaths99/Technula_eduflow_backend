"""
Homework and Assignment Diary models.
"""
from sqlalchemy import Column, String, Date, DateTime, Boolean, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class HomeworkDB(Base):
    __tablename__ = "homework"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    grade = Column(String(10), nullable=False)
    section = Column(String(10), nullable=False)
    subject_id = Column(GUID, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    posted_by = Column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    due_date = Column(Date, nullable=False)
    priority = Column(String(20), default="MEDIUM", nullable=False) # "LOW", "MEDIUM", "HIGH"
    attachment_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(timezone.utc))
    updated_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    subject = relationship("Subject")
    teacher = relationship("UserDB", foreign_keys=[posted_by])
    submissions = relationship("HomeworkSubmissionDB", back_populates="homework", cascade="all, delete-orphan")


class HomeworkSubmissionDB(Base):
    __tablename__ = "homework_submissions"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    homework_id = Column(GUID, ForeignKey("homework.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(GUID, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), default="NOT_SUBMITTED", nullable=False) # "SUBMITTED", "LATE", "NOT_SUBMITTED", "GRADED"
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    remarks = Column(Text, nullable=True)
    grade_value = Column(String(10), nullable=True) # "A", "B+", etc.
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("homework_id", "student_id", name="uq_hw_student_submission"),
    )

    # Relationships
    homework = relationship("HomeworkDB", back_populates="submissions")
    student = relationship("StudentDB")
