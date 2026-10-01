"""
School model — the multi-tenant root entity.
Every other business table references school_id.
"""
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class SchoolDB(Base):
    __tablename__ = "schools"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    code = Column(String(50), unique=True, index=True, nullable=True)  # 6-char shareable school code (e.g. DPS-DEL)
    name = Column(String(255), nullable=False)
    board = Column(String(50), nullable=True)  # CBSE, ICSE, State
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True, unique=True)
    logo_url = Column(String(500), nullable=True)
    stamp_url = Column(String(500), nullable=True)
    signature_url = Column(String(500), nullable=True)
    affiliation_no = Column(String(100), nullable=True)
    principal_name = Column(String(150), nullable=True)
    website = Column(String(255), nullable=True)
    academic_year = Column(String(20), default="2025-26", nullable=True)

    # ── SaaS Multi-Tenant Fields ──
    is_active = Column(Boolean, default=True, nullable=False)
    is_suspended = Column(Boolean, default=False, nullable=False)
    max_students = Column(Integer, default=500, nullable=False)
    max_teachers = Column(Integer, default=50, nullable=False)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # SaaS Subscription
    subscription_plan = Column(String(30), default="starter", nullable=False)

    # ── Branding & Customization ──
    brand_color = Column(String(30), default="#635bff", nullable=True)
    powered_by_text = Column(String(100), default="Powered by Technula-Gaj", nullable=True)
    parent_profile_approval_required = Column(Boolean, default=False, nullable=False)
    birthday_template = Column(Text, nullable=True)

    # Relationships
    users = relationship("UserDB", back_populates="school", cascade="all, delete-orphan")
    students = relationship("StudentDB", back_populates="school", cascade="all, delete-orphan")
    subjects = relationship("Subject", back_populates="school", cascade="all, delete-orphan")
    exams = relationship("Exam", back_populates="school", cascade="all, delete-orphan")
    subscription = relationship("SubscriptionPlanDB", back_populates="school", uselist=False, cascade="all, delete-orphan")

