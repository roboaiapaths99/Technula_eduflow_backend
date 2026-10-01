"""
Ticket model — parent complaints, requests, and queries with SLA tracking.
"""
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class TicketDB(Base):
    __tablename__ = "tickets"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_user_id = Column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(GUID, ForeignKey("students.id", ondelete="SET NULL"), nullable=True)
    category = Column(String(50), nullable=False)  # Academic, Transport, Fees, Discipline, General
    subject = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(30), default="OPEN", nullable=False)  # OPEN, IN_PROGRESS, RESOLVED, CLOSED
    priority = Column(String(20), default="MEDIUM", nullable=False)  # LOW, MEDIUM, HIGH, URGENT
    assigned_to = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
