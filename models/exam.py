"""
Exam model — enhanced with school_id, exam_type, is_published.
"""
from sqlalchemy import Column, String, Float, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class Exam(Base):
    __tablename__ = "exams"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    exam_type = Column(String(50), nullable=True)  # Unit Test, Mid Term, Final, Periodic
    term = Column(String(50), nullable=False)
    grade = Column(String(10), nullable=False)
    date = Column(Date, nullable=False)
    total_marks = Column(Float, nullable=False)
    is_published = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    school = relationship("SchoolDB", back_populates="exams")
    marks = relationship("Mark", back_populates="exam", cascade="all, delete-orphan")
