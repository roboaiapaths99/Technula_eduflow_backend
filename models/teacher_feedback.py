"""
Teacher Feedback model — enhanced with school_id and teacher_id tracking.
"""
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class TeacherFeedback(Base):
    __tablename__ = "teacher_feedback"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(GUID, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    exam_id = Column(GUID, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True)
    teacher_id = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    feedback = Column(Text, nullable=False)
    strengths = Column(Text, nullable=True)
    needs_work = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "exam_id", name="uq_feedback_student_exam"),
    )

    # Relationships
    student = relationship("StudentDB", back_populates="feedback")
