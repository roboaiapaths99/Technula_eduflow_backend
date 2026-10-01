"""
School Payment Gateway Configuration model — multi-tenant payment credentials.
"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class SchoolPaymentConfigDB(Base):
    __tablename__ = "school_payment_configs"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    gateway_provider = Column(String(50), default="MANUAL", nullable=False)  # RAZORPAY, STRIPE, CASHFREE, MANUAL
    merchant_key = Column(String(255), nullable=True)        # Gateway API Key (e.g. rzp_live_...)
    merchant_secret = Column(String(255), nullable=True)     # Gateway Secret
    upi_vpa = Column(String(100), nullable=True)             # e.g. "schoolname@hdfcbank"
    upi_account_name = Column(String(150), nullable=True)    # e.g. "Greenwood High School"
    bank_name = Column(String(150), nullable=True)           # e.g. "HDFC Bank"
    bank_account_no = Column(String(50), nullable=True)      # e.g. "50200012345678"
    bank_ifsc = Column(String(20), nullable=True)            # e.g. "HDFC0001234"
    bank_account_holder = Column(String(150), nullable=True) # e.g. "Greenwood High Educational Trust"
    qr_code_url = Column(Text, nullable=True)                # Payment QR code image URL or base64
    receipt_prefix = Column(String(20), default="RCP", nullable=False) # e.g. "GWH-2026"
    receipt_template_url = Column(Text, nullable=True)       # Custom school letterhead / format image URL
    receipt_template_html = Column(Text, nullable=True)      # Custom HTML receipt template format
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

