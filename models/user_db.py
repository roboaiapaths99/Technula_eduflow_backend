"""
User model — enhanced with school_id, phone, email_verified.
Supports roles: Admin, Teacher, ClassTeacher, SubjectTeacher, Parent
"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
import json
from datetime import datetime, timezone


# Default permission set for staff/teacher accounts
DEFAULT_STAFF_PERMISSIONS = {
    "attendance": True,
    "marks": True,
    "homework": True,
    "diary": True,
    "timetable": False,
    "calendar": False,
    "gallery": False,
    "gate_pass": False,
    "leave": False,
    "datesheet": False,
    "announcements": False,
    "certificates": False,
    "fees": False,
    "students": False,
    "reports": False,
    "analytics": False,
    "settings": False,
}


class UserDB(Base):
    __tablename__ = "users"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    phone = Column(String(20), nullable=True)
    full_name = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, index=True)  # Admin, Teacher, ClassTeacher, SubjectTeacher, Parent
    is_active = Column(Boolean, default=True, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    must_reset_password = Column(Boolean, default=False, nullable=False)  # Force password change on first login
    permissions_json = Column(Text, nullable=True)  # JSON string of module-level RBAC permissions
    fcm_token = Column(String(500), nullable=True)  # Firebase push token
    allow_whatsapp = Column(Boolean, default=True, nullable=False)
    allow_email = Column(Boolean, default=True, nullable=False)
    allow_sms = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(timezone.utc))
    updated_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    @property
    def permissions(self) -> dict:
        """Parse permissions_json into a dict, falling back to defaults."""
        if self.permissions_json:
            try:
                return json.loads(self.permissions_json)
            except (json.JSONDecodeError, TypeError):
                pass
        # Admin gets all permissions
        if (self.role or "").lower() == "admin":
            return {k: True for k in DEFAULT_STAFF_PERMISSIONS}
        return dict(DEFAULT_STAFF_PERMISSIONS)

    @permissions.setter
    def permissions(self, value: dict):
        self.permissions_json = json.dumps(value) if value else None

    # Relationships
    school = relationship("SchoolDB", back_populates="users")
    parent_links = relationship("ParentStudentDB", back_populates="parent", foreign_keys="ParentStudentDB.parent_user_id")
    teacher_assignments = relationship("TeacherAssignmentDB", back_populates="teacher", foreign_keys="TeacherAssignmentDB.teacher_user_id")
