"""
Teacher-Class assignment — enhanced with role_type and subject_id.
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class TeacherAssignmentDB(Base):
    __tablename__ = "teacher_assignments"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    teacher_user_id = Column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    grade = Column(String(10), nullable=False)
    section = Column(String(10), nullable=False)
    role_type = Column(String(30), default="ClassTeacher", nullable=False)  # ClassTeacher, SubjectTeacher
    subject_id = Column(GUID, ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("school_id", "teacher_user_id", "grade", "section", "role_type", "subject_id",
                         name="uq_teacher_assignment"),
    )

    # Relationships
    teacher = relationship("UserDB", back_populates="teacher_assignments", foreign_keys=[teacher_user_id])
