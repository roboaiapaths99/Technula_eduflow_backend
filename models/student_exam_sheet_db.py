import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime, Text, ForeignKey
from db.base import Base, GUID

class StudentExamSheetDB(Base):
    __tablename__ = "student_exam_sheets"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(GUID, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    exam_id = Column(GUID, ForeignKey("exams.id", ondelete="CASCADE"), nullable=True)
    exam_name = Column(String(120), nullable=True)
    subject_id = Column(GUID, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=True)
    subject_name = Column(String(120), nullable=False)
    
    # AES-256 Encrypted file storage
    encrypted_file_path = Column(String(500), nullable=False)
    original_filename = Column(String(255), nullable=True)
    file_size_bytes = Column(Float, default=0.0)
    
    # OCR extracted data & verification check
    ocr_extracted_text = Column(Text, nullable=True)
    ocr_detected_admission_no = Column(String(64), nullable=True)
    ocr_detected_student_name = Column(String(120), nullable=True)
    ocr_detected_roll_no = Column(String(32), nullable=True)
    verification_status = Column(String(32), default="VERIFIED_MATCH") # VERIFIED_MATCH | MISMATCH_FLAGGED | MANUALLY_CONFIRMED
    
    # Marks and grading feedback
    marks_awarded = Column(Float, nullable=True)
    max_marks = Column(Float, default=100.0)
    teacher_notes = Column(Text, nullable=True)
    uploaded_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
