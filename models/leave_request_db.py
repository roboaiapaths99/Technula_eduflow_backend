"""
Leave Request model — digital student and staff leaves with document proof and approval tracking.
"""
from sqlalchemy import Column, String, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class LeaveRequestDB(Base):
    __tablename__ = "leave_requests"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(GUID, ForeignKey("students.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False) # Applicant (Parent or Teacher)
    from_date = Column(Date, nullable=False)
    to_date = Column(Date, nullable=False)
    leave_type = Column(String(50), default="SICK", nullable=False) # "SICK", "FAMILY", "EMERGENCY", "VACATION", "OTHER"
    reason = Column(Text, nullable=False)
    attachment_url = Column(String(500), nullable=True) # Medical prescription / Doctor's certificate
    status = Column(String(20), default="PENDING", nullable=False) # "PENDING", "APPROVED", "REJECTED"
    reviewed_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    admin_remarks = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    student = relationship("StudentDB")
    applicant = relationship("UserDB", foreign_keys=[user_id])
    reviewer = relationship("UserDB", foreign_keys=[reviewed_by])
