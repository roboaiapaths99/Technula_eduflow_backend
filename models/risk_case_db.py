"""
Risk Case model — Student Success Intelligence Layer.
Rules-based risk detection: consecutive absences, mark decline, missed assignments.
"""
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class RiskCaseDB(Base):
    __tablename__ = "risk_cases"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(GUID, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    risk_level = Column(String(20), nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    trigger_rule = Column(String(100), nullable=False)  # e.g., "CONSECUTIVE_ABSENCES_3", "SCORE_DROP_15PCT"
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(30), default="OPEN", nullable=False)  # OPEN, IN_REVIEW, ACTION_TAKEN, RESOLVED
    assigned_to = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    student = relationship("StudentDB", back_populates="risk_cases")
