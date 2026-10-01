import sys
import os
import random

# Ensure backend dir is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings
from services.sms_service import dispatch_login_otp
from services.notification_service import send_email

def main():
    print("========================================")
    print("LIVE CREDENTIALS & DISPATCH TEST")
    print("========================================")
    print(f"SMS API Key Configured: {bool(settings.effective_sms_api_key)}")
    print(f"SMS Sender ID: {settings.effective_sms_sender_id}")
    print(f"SMS Template ID: {settings.effective_sms_template_id}")
    print(f"Resend API Key Configured: {bool(settings.RESEND_API_KEY)}")
    print(f"Resend From Email: {settings.EMAIL_FROM}")
    print("----------------------------------------")

    test_otp = str(random.randint(100000, 999999))
    target_phone = "7906681573"
    target_email = "bhaskarjoshi900@gmail.com"

    # 1. Dispatch Real SMS via MetaReach Gateway
    print(f"\n[1] Dispatching LIVE SMS OTP ({test_otp}) to +91 {target_phone}...")
    sms_ok = dispatch_login_otp(to_phone=target_phone, otp=test_otp)
    print(f"SMS Dispatch Status: {'SUCCESS' if sms_ok else 'FAILED'}")

    # 2. Dispatch Real Email via Resend
    print(f"\n[2] Dispatching LIVE Email to {target_email} via Resend...")
    subject = f"Technula EduFlow Live Test Verification - OTP: {test_otp}"
    html_body = f"""
    <div style="font-family: Arial, sans-serif; padding: 24px; max-width: 500px; margin: 0 auto; border: 1px solid #e2e8f0; borderRadius: 12px;">
        <h2 style="color: #4f46e5; margin-top: 0;">Technula EduFlow Verification Test</h2>
        <p>Hello Bhaskar,</p>
        <p>This is a live transactional test email sent via <strong>Resend</strong> from <code>{settings.EMAIL_FROM}</code>.</p>
        <div style="background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 16px; text-align: center; margin: 20px 0;">
            <div style="font-size: 12px; color: #64748b; margin-bottom: 6px; font-weight: bold;">YOUR VERIFICATION CODE</div>
            <div style="font-size: 32px; font-weight: 900; letter-spacing: 4px; color: #059669;">{test_otp}</div>
        </div>
        <p>Real DLT SMS OTP was also dispatched to <strong>+91 {target_phone}</strong> via MetaReach gateway (Sender: {settings.effective_sms_sender_id}).</p>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
        <p style="font-size: 11px; color: #94a3b8; margin-bottom: 0;">Technula SaaS Live Dispatch Verification</p>
    </div>
    """
    email_ok = send_email(to_email=target_email, subject=subject, html_content=html_body)
    print(f"Email Dispatch Status: {'SUCCESS' if email_ok else 'FAILED'}")

    print("========================================")
    if sms_ok and email_ok:
        print("ALL TESTS PASSED: Both real SMS and Email delivered successfully!")
    else:
        print("TEST FAILED: One or both dispatches did not succeed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
