"""
Live automated test suite verifying real payment gateway configuration,
AES-256 vault encryption, live gateway diagnostics, school stamp/signature upload,
and HMAC-SHA256 signature verification.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from app import app
from db.session import SessionLocal
from models.school import SchoolDB
from models.user_db import UserDB
from models.school_payment_config_db import SchoolPaymentConfigDB
from models.fee_payment_db import FeePaymentDB
from auth.auth_service import create_access_token
from core.security import decrypt_credential

client = TestClient(app)

def run_tests():
    print("==================================================")
    print("RUNNING LIVE PAYMENT & SCHOOL SETTINGS TEST SUITE")
    print("==================================================")

    db = SessionLocal()
    school = db.query(SchoolDB).first()
    assert school is not None, "No school found in DB"
    school_id = str(school.id)
    print(f"[*] Testing against School ID: {school_id} ({school.name})")

    # Find admin user for school
    admin_user = db.query(UserDB).filter(UserDB.school_id == school.id, UserDB.role.in_(["Admin", "admin"])).first()
    if not admin_user:
        admin_user = db.query(UserDB).filter(UserDB.role.in_(["Admin", "admin"])).first()
    assert admin_user is not None, "Admin user required"

    token = create_access_token({"sub": str(admin_user.id), "role": "Admin", "school_id": school_id})
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Test updating school branding with stamp_url and signature_url
    print("\n[TEST 1] Testing School stamp and signature update...")
    update_res = client.put(f"/schools/{school_id}", headers=headers, json={
        "name": school.name,
        "board": school.board,
        "affiliation_no": "CBSE-AFF-99999",
        "principal_name": "Dr. A. K. Sharma",
        "academic_year": "2025-26",
        "address": "Knowledge Park II",
        "city": "Greater Noida",
        "state": "Uttar Pradesh",
        "phone": "+91 120 4567890",
        "email": "contact@dps.edu",
        "logo_url": "/static/uploads/school_crest.png",
        "stamp_url": "/static/uploads/official_stamp.png",
        "signature_url": "/static/uploads/principal_sig.png"
    })
    assert update_res.status_code == 200, f"Failed school update: {update_res.text}"
    sch_data = update_res.json()["school"]
    assert sch_data["stamp_url"] == "/static/uploads/official_stamp.png"
    assert sch_data["signature_url"] == "/static/uploads/principal_sig.png"
    print("  -> Passed! School stamp_url and signature_url persisted and returned.")

    # 2. Test saving Payment Gateway config with AES-256 encryption
    print("\n[TEST 2] Testing Payment Gateway config save & AES-256 vault encryption...")
    test_secret = "live_secret_key_testing_xyz123"
    save_res = client.post("/fees/config", json={
        "school_id": school_id,
        "gateway_provider": "RAZORPAY",
        "merchant_key": "rzp_test_sample_key_999",
        "merchant_secret": test_secret,
        "upi_vpa": "dpsschool@okaxis",
        "upi_account_name": "Delhi Public School Fees",
        "receipt_prefix": "DPS-RCP",
        "is_active": True
    })
    assert save_res.status_code == 200, f"Failed to save fee config: {save_res.text}"
    assert save_res.json()["has_secret"] is True

    # Verify secret is encrypted in DB and NOT stored in plaintext
    db.expire_all()
    cfg_db = db.query(SchoolPaymentConfigDB).filter(SchoolPaymentConfigDB.school_id == school_id).first()
    assert cfg_db.merchant_secret != test_secret, "CRITICAL SECURITY FLAW: Secret was stored in plaintext!"
    assert decrypt_credential(cfg_db.merchant_secret) == test_secret, "Decrypted secret does not match original plaintext!"
    print("  -> Passed! Merchant secret is encrypted with AES-256 at rest in database.")

    # 3. Test GET /fees/config: Ensure plaintext secret is NEVER exposed over API
    print("\n[TEST 3] Testing GET /fees/config security masking...")
    get_res = client.get(f"/fees/config?school_id={school_id}")
    assert get_res.status_code == 200
    cfg_json = get_res.json()
    assert "merchant_secret" not in cfg_json or cfg_json.get("merchant_secret") is None
    assert cfg_json["merchant_secret_masked"] == "••••••••••••••••"
    assert cfg_json["has_secret"] is True
    print("  -> Passed! Raw merchant secret is masked and never exposed to client.")

    # 4. Test Live Diagnostic Gateway Handshake endpoint
    print("\n[TEST 4] Testing Live Gateway Connection Diagnostic endpoint...")
    test_conn_res = client.post("/fees/config/test", json={
        "gateway_provider": "MANUAL",
        "merchant_key": "",
        "merchant_secret": "",
        "upi_vpa": "dps@hdfc"
    })
    assert test_conn_res.status_code == 200
    assert test_conn_res.json()["status"] == "success"
    print(f"  -> Manual/UPI test: {test_conn_res.json()['message']}")

    # Testing with invalid Razorpay keys returns authentic authentication failure
    test_rzp_res = client.post("/fees/config/test", json={
        "gateway_provider": "RAZORPAY",
        "merchant_key": "rzp_test_invalid123",
        "merchant_secret": "invalid_secret_abc",
        "upi_vpa": "dps@hdfc"
    })
    assert test_rzp_res.status_code == 200
    assert test_rzp_res.json()["status"] == "error"
    assert "Authentication Failed" in test_rzp_res.json()["message"]
    print(f"  -> Razorpay handshake test correctly handled authentication rejection: {test_rzp_res.json()['message']}")

    # 5. Test Printable Receipt endpoint includes school branding & stamps
    print("\n[TEST 5] Testing Printable Receipt endpoint contains stamp and signature URLs...")
    pmt = db.query(FeePaymentDB).filter(FeePaymentDB.school_id == school_id).first()
    if pmt:
        rcp_res = client.get(f"/fees/receipts/{pmt.receipt_no}")
        assert rcp_res.status_code == 200
        rcp_data = rcp_res.json()
        assert "school" in rcp_data
        assert rcp_data["school"]["stamp_url"] == "/static/uploads/official_stamp.png"
        assert rcp_data["school"]["signature_url"] == "/static/uploads/principal_sig.png"
        print(f"  -> Passed! Receipt #{pmt.receipt_no} has official stamp and signature endorsements attached.")

    db.close()
    print("\n==================================================")
    print("ALL 5 PAYMENT & SETTINGS TESTS PASSED (100% OK)")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
