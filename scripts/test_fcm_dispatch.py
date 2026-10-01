import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings
from services.notification_service import send_push_notification

def main():
    print("========================================")
    print("FIREBASE FCM CONFIGURATION TEST")
    print("========================================")
    print("Firebase Credentials File:", settings.FIREBASE_CREDENTIALS_JSON)
    
    # Verify file exists
    cred_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), settings.FIREBASE_CREDENTIALS_JSON)
    print("Credentials Path:", cred_path)
    print("File Exists:", os.path.exists(cred_path))
    
    import firebase_admin
    from firebase_admin import credentials
    if not getattr(firebase_admin, "_apps", None):
        cred = credentials.Certificate(cred_path)
        app = firebase_admin.initialize_app(cred)
    else:
        app = firebase_admin.get_app()
    
    print("Firebase App Initialized successfully!")
    print("Connected Project ID:", app.project_id)
    print("Service Account:", cred.service_account_email)
    print("========================================")
    print("READY: Backend is fully configured to push real-time FCM notifications!")

if __name__ == "__main__":
    main()
