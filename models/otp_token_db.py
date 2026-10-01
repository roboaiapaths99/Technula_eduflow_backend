"""
OTP and Password Reset Token model — persistent store replacing in-memory dictionaries.
Supports SuperAdmin OTP, Parent Login OTP, and Password Reset Tokens.
"""
from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Text
from db.base import Base, GUID
import uuid
import json
from datetime import datetime, timezone


class OtpTokenDB(Base):
    __tablename__ = "otp_tokens"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=True, index=True)
    token_type = Column(String(50), nullable=False, index=True)  # SUPERADMIN_OTP, PARENT_OTP, PASSWORD_RESET
    identifier = Column(String(255), nullable=False, index=True)  # phone or email (normalized)
    token = Column(String(255), nullable=False, index=True)
    short_code = Column(String(50), nullable=True, index=True)
    meta_json = Column(Text, nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    @property
    def payload(self) -> dict:
        if self.meta_json:
            try:
                return json.loads(self.meta_json)
            except Exception:
                return {}
        return {}

    @payload.setter
    def payload(self, data: dict):
        self.meta_json = json.dumps(data) if data else None
