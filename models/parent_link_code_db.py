"""
Parent Link Code — unique verification codes for secure parent-student linking.
Admin generates a code per student. Parent enters the code during registration
to prove they are the real parent. If no code or wrong code → flagged as suspicious.
"""
import secrets
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


def _generate_link_code():
    """Generate a unique 8-char alphanumeric code like 'STU-A3X7K9'."""
    return f"STU-{secrets.token_hex(3).upper()}"


class ParentLinkCodeDB(Base):
    __tablename__ = "parent_link_codes"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(GUID, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(20), nullable=False, unique=True, index=True, default=_generate_link_code)
    relation = Column(String(50), default="Guardian")  # Father, Mother, Guardian
    is_used = Column(Boolean, default=False, nullable=False)
    used_by_user_id = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    student = relationship("StudentDB")
    school = relationship("SchoolDB")
