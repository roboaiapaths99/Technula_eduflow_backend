"""
Notification model — multi-channel notification tracking with delivery lifecycle.
CREATED → QUEUED → SENT → DELIVERED → READ/ACKNOWLEDGED | FAILED
"""
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class NotificationDB(Base):
    __tablename__ = "notifications"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_user_id = Column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String(30), nullable=False)  # IN_APP, EMAIL, WHATSAPP, PUSH
    event_type = Column(String(50), nullable=False)  # MARKS_PUBLISHED, ATTENDANCE_ALERT, RISK_ALERT, ANNOUNCEMENT, TICKET_UPDATE
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    payload_json = Column(Text, nullable=True)  # JSON string with deep-link metadata
    status = Column(String(30), default="SENT", nullable=False)  # CREATED, QUEUED, SENT, DELIVERED, READ, FAILED
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
