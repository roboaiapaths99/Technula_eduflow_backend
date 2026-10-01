"""
Chat Message model — 1:1 parent-teacher messaging with media support.
"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class ChatMessageDB(Base):
    __tablename__ = "chat_messages"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(String(255), nullable=False, index=True)  # deterministic combo of 2 user IDs
    sender_user_id = Column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_user_id = Column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    message_type = Column(String(20), default="TEXT", nullable=False)  # TEXT, IMAGE, VOICE, VIDEO, FILE
    content = Column(Text, nullable=True)  # Text body for TEXT type
    media_url = Column(String(500), nullable=True)  # URL for media types
    media_filename = Column(String(255), nullable=True)  # Original filename
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
