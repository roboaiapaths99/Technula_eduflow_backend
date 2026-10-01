"""
Audit Log — tracks every sensitive action across all schools for SaaS compliance.
Used by SuperAdmin to monitor cross-school activity and by school admins for their own school.
"""
from sqlalchemy import Column, String, DateTime, Text, JSON
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class AuditLogDB(Base):
    __tablename__ = "audit_logs"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, nullable=True, index=True)  # Nullable for SuperAdmin actions
    user_id = Column(GUID, nullable=True, index=True)
    user_email = Column(String(255), nullable=True)
    action = Column(String(100), nullable=False, index=True)  # e.g. "student.create", "marks.update", "login.success"
    resource_type = Column(String(50), nullable=True)  # "student", "teacher", "marks", "school"
    resource_id = Column(String(50), nullable=True)
    details = Column(JSON, nullable=True)  # Changed fields, old/new values
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
