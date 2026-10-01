"""
Mark model — enhanced with school_id, grade_letter, uploaded_by.
"""
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class Mark(Base):
    __tablename__ = "marks"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(GUID, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    exam_id = Column(GUID, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id = Column(GUID, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    marks_obtained = Column(Float, nullable=False)
    max_marks = Column(Float, nullable=False)
    grade_letter = Column(String(5), nullable=True)  # A+, A, B, C, D, F
    uploaded_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "exam_id", "subject_id", name="uq_student_exam_subject"),
    )

    # Relationships
    student = relationship("StudentDB", back_populates="marks")
    exam = relationship("Exam", back_populates="marks")
    subject = relationship("Subject", back_populates="marks")
