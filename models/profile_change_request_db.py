"""
Profile Change Request Model — Approval workflow for guardian profile edits.
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class ProfileChangeRequestDB(Base):
    __tablename__ = "profile_change_requests"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_user_id = Column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(GUID, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)

    field_name = Column(String(50), nullable=False)  # phone, email, address, emergency_contact_name, emergency_contact_phone
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=False)
    status = Column(String(20), default="pending", nullable=False, index=True)  # pending, approved, rejected

    reviewed_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    parent = relationship("UserDB", foreign_keys=[parent_user_id])
    student = relationship("StudentDB", foreign_keys=[student_id])
    reviewer = relationship("UserDB", foreign_keys=[reviewed_by])
