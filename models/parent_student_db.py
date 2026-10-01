"""
Parent-Student link — enhanced with verification tracking.
"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class ParentStudentDB(Base):
    __tablename__ = "parent_student_links"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    parent_user_id = Column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(GUID, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    relation = Column(String(50), default="Guardian", nullable=False)  # Father, Mother, Guardian
    is_primary = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=True, nullable=False)  # OTP/Admin verified
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("parent_user_id", "student_id", name="uq_parent_student"),
    )

    # Relationships
    parent = relationship("UserDB", back_populates="parent_links", foreign_keys=[parent_user_id])
    student = relationship("StudentDB", back_populates="parent_links", foreign_keys=[student_id])
