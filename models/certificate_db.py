import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from db.base import Base, GUID

class SchoolAssetDB(Base):
    """Stores school official assets: official stamp, principal digital signature, and crest"""
    __tablename__ = "school_assets"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    stamp_image_url = Column(String(500), nullable=True)
    signature_image_url = Column(String(500), nullable=True)
    letterhead_header_url = Column(String(500), nullable=True)
    principal_name = Column(String(120), default="Dr. Alok Verma")
    principal_designation = Column(String(120), default="Principal & Head of Institution")
    affiliation_code = Column(String(64), default="CBSE/AFF/2730198")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class CertificateRequestDB(Base):
    """Tracks certificate applications by parents/students, admin approval queue, and issued certificates"""
    __tablename__ = "certificate_requests"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(GUID, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_user_id = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # TRANSFER_CERTIFICATE | BONAFIDE | CHARACTER | FEE_CLEARANCE
    certificate_type = Column(String(64), nullable=False)
    purpose_reason = Column(Text, nullable=False)
    delivery_mode = Column(String(32), default="ONLINE_APP") # ONLINE_APP | OFFLINE_COUNTER
    
    # PENDING | APPROVED | REJECTED | READY_FOR_PICKUP
    status = Column(String(32), default="PENDING")
    rejection_reason = Column(Text, nullable=True)
    
    # Generated upon approval
    certificate_number = Column(String(64), nullable=True, unique=True, index=True) # e.g. TC-2026-0001
    qr_verification_token = Column(String(128), nullable=True, unique=True, index=True)
    approved_by = Column(String(120), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
