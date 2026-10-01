"""
Fee Payment model — atomic records of parent online payments and cashier counter collections.
"""
from sqlalchemy import Column, String, Float, DateTime, Date, ForeignKey, Text, Index
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class FeePaymentDB(Base):
    __tablename__ = "fee_payments"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(GUID, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    fee_structure_id = Column(GUID, ForeignKey("fee_structures.id", ondelete="SET NULL"), nullable=True)
    receipt_no = Column(String(50), nullable=False, unique=True, index=True)  # "RCP-2026-00042"
    base_amount_paid = Column(Float, nullable=False)
    fine_amount_paid = Column(Float, default=0.0, nullable=False)
    discount_waiver = Column(Float, default=0.0, nullable=False)
    total_paid = Column(Float, nullable=False)
    payment_mode = Column(String(30), nullable=False)  # "UPI_ONLINE", "UPI_COUNTER", "CASH", "CARD", "CHEQUE", "NEFT"
    transaction_ref = Column(String(100), nullable=True) # Gateway Order ID or Cheque # or UPI UTR
    gateway_status = Column(String(30), default="COMPLETED", nullable=False) # "INITIATED", "COMPLETED", "FAILED"
    payment_date = Column(Date, nullable=False)
    collected_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True) # null if paid online by parent
    remarks = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(timezone.utc))
    updated_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        Index("ix_fee_payments_school_date", "school_id", "payment_date"),
    )

    # Relationships
    student = relationship("StudentDB")
    fee_structure = relationship("FeeStructureDB")
    collector = relationship("UserDB", foreign_keys=[collected_by])
