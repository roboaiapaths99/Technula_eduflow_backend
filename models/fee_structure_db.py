"""
Fee Structure model — grade-wise fee components, installment terms, and due dates.
"""
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Date, ForeignKey
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class FeeStructureDB(Base):
    __tablename__ = "fee_structures"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    academic_year = Column(String(20), nullable=False)       # "2025-26"
    grade = Column(String(10), nullable=False)               # "10"
    fee_head = Column(String(100), nullable=False)           # "Tuition Fee", "Transport", "Lab & Library", "Development"
    total_amount = Column(Float, nullable=False)             # 25000.00
    installment_name = Column(String(50), nullable=False)    # "Term 1", "Quarter 2", "Annual"
    due_date = Column(Date, nullable=False)                  # 2026-04-15
    grace_period_days = Column(Integer, default=7, nullable=False)
    late_fine_per_day = Column(Float, default=50.0, nullable=False)
    is_optional = Column(Boolean, default=False, nullable=False) # e.g. Transport vs Tuition
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
