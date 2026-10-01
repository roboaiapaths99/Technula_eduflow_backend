"""
Gate Pass & Status Log Models — Complete Gate Pass Lifecycle.
Statuses: requested -> approved -> out -> returned (or rejected / cancelled / expired).
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class GatePassDB(Base):
    __tablename__ = "gate_passes"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(GUID, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_user_id = Column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    pass_code = Column(String(30), nullable=False, unique=True, index=True)
    pass_type = Column(String(30), default="early_leave", nullable=False)  # early_leave, visitor_pickup, outing, emergency, other
    accompanied_by_name = Column(String(150), nullable=False)
    accompanied_by_relation = Column(String(50), nullable=False)
    visitor_photo_url = Column(String(500), nullable=True)
    reason = Column(Text, nullable=False)

    expected_out_time = Column(DateTime(timezone=True), nullable=False)
    expected_return_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default="requested", nullable=False, index=True)  # requested, approved, rejected, out, returned, cancelled, expired
    qr_token = Column(String(100), nullable=False, unique=True, index=True)

    approved_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    actual_out_time = Column(DateTime(timezone=True), nullable=True)
    actual_return_time = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    student = relationship("StudentDB", foreign_keys=[student_id])
    parent = relationship("UserDB", foreign_keys=[parent_user_id])
    approver = relationship("UserDB", foreign_keys=[approved_by])
    status_logs = relationship("GatePassStatusLogDB", back_populates="gate_pass", cascade="all, delete-orphan", order_by="desc(GatePassStatusLogDB.created_at)")


class GatePassStatusLogDB(Base):
    __tablename__ = "gate_pass_status_logs"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    gate_pass_id = Column(GUID, ForeignKey("gate_passes.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status = Column(String(20), nullable=False)
    to_status = Column(String(20), nullable=False)
    changed_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    gate_name = Column(String(50), default="Main Gate", nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    gate_pass = relationship("GatePassDB", back_populates="status_logs")
    actor = relationship("UserDB", foreign_keys=[changed_by])
