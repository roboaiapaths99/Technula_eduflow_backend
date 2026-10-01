"""
Visitor Log Model — Front-desk walk-ins, guest entries, and campus security logs.
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class VisitorLogDB(Base):
    __tablename__ = "visitor_logs"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)

    visitor_name = Column(String(150), nullable=False)
    visitor_phone = Column(String(20), nullable=False)
    visitor_photo_url = Column(String(500), nullable=True)
    purpose = Column(String(50), nullable=False)  # parent_pickup, vendor_delivery, guest_meeting, admissions, maintenance, inspection, other

    student_id = Column(GUID, ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True)
    gate_pass_id = Column(GUID, ForeignKey("gate_passes.id", ondelete="SET NULL"), nullable=True, index=True)
    person_to_meet = Column(String(150), nullable=True)

    id_proof_type = Column(String(50), nullable=True)  # Aadhaar, Driving License, Voter ID, Passport, Other
    id_proof_number = Column(String(50), nullable=True)

    check_in_time = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    check_out_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default="checked_in", nullable=False, index=True)  # checked_in, checked_out

    gate_name = Column(String(50), default="Main Gate", nullable=False)
    logged_by_user_id = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)

    # Relationships
    student = relationship("StudentDB", foreign_keys=[student_id])
    gate_pass = relationship("GatePassDB", foreign_keys=[gate_pass_id])
    logged_by = relationship("UserDB", foreign_keys=[logged_by_user_id])
