import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import settings
from services.pdf_service import generate_html_fee_receipt
from api.fee_api import router as fee_router
from auth.auth_api import router as auth_router

print("=== SYSTEM VERIFICATION ===", flush=True)
print("SuperAdmin Phones Configured:", settings.authorized_superadmin_phones, flush=True)
assert "7906681573" in settings.authorized_superadmin_phones, "7906681573 missing"
assert "9990911093" in settings.authorized_superadmin_phones, "9990911093 missing"
print("SUCCESS: Authorized SuperAdmin phones successfully loaded from .env!", flush=True)

sample_receipt_data = {
    "school": {
        "name": "Delhi Public International School",
        "board": "CBSE",
        "affiliation_no": "CBSE-AFF-2025/9981",
        "address": "Sector 21, Knowledge City",
        "city": "New Delhi",
        "state": "Delhi",
        "phone": "+91 11 2345 6789",
        "email": "accounts@dpis.edu"
    },
    "student": {
        "name": "Aarav Sharma",
        "admission_no": "ADM-2025-001",
        "grade": "10",
        "section": "A",
        "father_name": "Rajesh Sharma",
        "mother_name": "Sunita Sharma"
    },
    "payment": {
        "receipt_no": "RCP-2025-9981",
        "payment_date": "2026-09-23",
        "fee_head": "Term 2 Tuition & Activity Fee",
        "installment_name": "Quarterly Installment 2",
        "base_amount": 18500,
        "fine_amount": 0,
        "discount_waiver": 500,
        "total_paid": 18000,
        "payment_mode": "UPI / NetBanking",
        "transaction_ref": "UPI-HDFC-991823901923"
    }
}

html = generate_html_fee_receipt(sample_receipt_data)
assert "Delhi Public International School" in html
assert "RCP-2025-9981" in html
assert "18,000.00" in html
print(f"SUCCESS: Fee receipt HTML generated cleanly ({len(html)} bytes)!", flush=True)
print("ALL BACKEND INTEGRITY CHECKS PASSED!", flush=True)
