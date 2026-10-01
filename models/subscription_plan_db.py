"""
Subscription Plan — tracks each school's active plan tier, quotas, features,
and PayU payment history. Supports 10-day free trial.

Plan tiers:
  - starter (free, 10-day trial, limited features)
  - growth  (₹1,999/mo, mid-tier features)
  - enterprise (₹4,999/mo, all features, unlimited)
"""
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Float, JSON, ForeignKey
from sqlalchemy.orm import relationship
from db.base import Base, GUID


# ── Feature keys for plan gating ────────────────────
PLAN_FEATURES = {
    "starter": [
        "attendance",
        "marks",
        "report_cards",
        "announcements",
        "basic_analytics",
    ],
    "growth": [
        "attendance",
        "marks",
        "report_cards",
        "announcements",
        "basic_analytics",
        "fee_management",
        "certificates",
        "ptc",
        "chat_diary",
        "homework",
        "timetable",
        "calendar",
        "leave_management",
        "bulk_csv_upload",
        "advanced_analytics",
    ],
    "enterprise": [
        "attendance",
        "marks",
        "report_cards",
        "announcements",
        "basic_analytics",
        "fee_management",
        "certificates",
        "ptc",
        "chat_diary",
        "homework",
        "timetable",
        "calendar",
        "leave_management",
        "bulk_csv_upload",
        "advanced_analytics",
        "ai_risk",
        "exam_ocr",
        "risk_prediction",
        "full_analytics",
        "counter_cash",
        "whatsapp_broadcast",
    ],
}

PLAN_QUOTAS = {
    "starter":    {"max_students": 100,   "max_staff": 5},
    "growth":     {"max_students": 500,   "max_staff": 25},
    "enterprise": {"max_students": 99999, "max_staff": 99999},
}

PLAN_PRICING = {
    "starter":    {"monthly": 0,    "yearly": 0},
    "growth":     {"monthly": 1999, "yearly": 19990},
    "enterprise": {"monthly": 4999, "yearly": 49990},
}

FREE_TRIAL_DAYS = 10


class SubscriptionPlanDB(Base):
    __tablename__ = "subscription_plans"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    plan_tier = Column(String(30), nullable=False, default="starter")   # starter | growth | enterprise
    billing_cycle = Column(String(20), nullable=False, default="monthly")  # monthly | yearly
    amount = Column(Float, default=0)

    max_students = Column(Integer, default=100, nullable=False)
    max_staff = Column(Integer, default=5, nullable=False)
    features = Column(JSON, default=list)  # list of enabled feature keys

    is_active = Column(Boolean, default=True, nullable=False)
    is_trial = Column(Boolean, default=True, nullable=False)
    trial_started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)

    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # PayU payment tracking
    last_payment_id = Column(String(100), nullable=True)
    last_payment_status = Column(String(30), nullable=True)  # success | pending | failed

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    school = relationship("SchoolDB", back_populates="subscription")
