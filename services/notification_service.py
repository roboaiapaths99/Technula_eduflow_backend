"""
Notification Service — Multi-channel delivery orchestrator.
Channels:
1. In-App (saved to NotificationDB)
2. WhatsApp (via Meta WhatsApp Cloud API)
3. Email (via Resend API)
4. Push (via Firebase Cloud Messaging)
Logs all deliveries to MongoDB for audit & troubleshooting.
"""
from __future__ import annotations
import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import urllib.request
import urllib.error

from core.config import settings
from db.mongo import log_mongo_document

logger = logging.getLogger("service.notification")


# ── IN-APP NOTIFICATION ───────────────────────────────────────────────
def create_in_app_notification(
    db,
    school_id,
    user_id,
    title: str,
    message: str,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
):
    """Save in-app notification in PostgreSQL / SQLite."""
    from models.notification_db import NotificationDB
    from models.user_db import UserDB

    # Verify recipient exists in User table to avoid FK violations on dummy parent links
    try:
        exists = db.query(UserDB.id).filter(UserDB.id == user_id).first()
        if not exists:
            return None

        notif = NotificationDB(
            school_id=school_id,
            recipient_user_id=user_id,
            channel="IN_APP",
            event_type=event_type,
            title=title,
            message=message,
            payload_json=json.dumps(payload) if payload else None,
            status="SENT",
            delivered_at=datetime.now(timezone.utc),
        )
        db.add(notif)
        db.commit()
    except Exception as e:
        db.rollback()
        return None

    # Log to MongoDB
    log_mongo_document("notifications", {
        "channel": "IN_APP",
        "school_id": str(school_id),
        "user_id": str(user_id),
        "title": title,
        "event_type": event_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "SENT",
    })
    return notif


# ── WHATSAPP CLOUD API ────────────────────────────────────────────────
def send_whatsapp_message(
    to_phone: str,
    template_name: str = "report_card_ready",
    parameters: Optional[list] = None,
    custom_text: Optional[str] = None,
) -> bool:
    """
    Send WhatsApp notification via Meta WhatsApp Cloud API.
    Falls back gracefully if token is not configured or in sandbox.
    """
    if not settings.WHATSAPP_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
        logger.info(f"[WhatsApp Mock] Would send to {to_phone}: {custom_text or template_name}")
        log_mongo_document("whatsapp_logs", {
            "to": to_phone,
            "mode": "MOCK",
            "template": template_name,
            "text": custom_text,
            "status": "SIMULATED_SUCCESS",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return True

    url = f"{settings.WHATSAPP_API_URL}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    # Format phone (remove + or spaces)
    clean_phone = "".join(filter(str.isdigit, to_phone))

    if custom_text:
        body = {
            "messaging_product": "whatsapp",
            "to": clean_phone,
            "type": "text",
            "text": {"body": custom_text},
        }
    else:
        body = {
            "messaging_product": "whatsapp",
            "to": clean_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": "en_US"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": str(p)} for p in (parameters or [])],
                    }
                ] if parameters else [],
            },
        }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            resp_data = json.loads(response.read().decode("utf-8"))
            log_mongo_document("whatsapp_logs", {
                "to": to_phone,
                "mode": "LIVE",
                "status": "SENT",
                "response": resp_data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return True
    except Exception as e:
        logger.error(f"[WhatsApp] Delivery failed to {to_phone}: {e}")
        log_mongo_document("whatsapp_logs", {
            "to": to_phone,
            "mode": "LIVE",
            "status": "FAILED",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return False


# ── RESEND EMAIL API ──────────────────────────────────────────────────
def send_email(
    to_email: str,
    subject: str,
    html_content: str,
) -> bool:
    """
    Send transactional email using Resend API.
    Falls back gracefully if API key is not configured.
    """
    if not settings.RESEND_API_KEY:
        logger.info(f"[Email Mock] Would send to {to_email}: {subject}")
        log_mongo_document("email_logs", {
            "to": to_email,
            "mode": "MOCK",
            "subject": subject,
            "status": "SIMULATED_SUCCESS",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return True

    url = settings.RESEND_API_URL.rstrip("/") + "/emails" if hasattr(settings, "RESEND_API_URL") and settings.RESEND_API_URL else "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ResendPython/2.0.0",
    }
    import requests
    import re

    from_address = settings.EMAIL_FROM or f"{settings.RESEND_FROM_NAME or 'Technula Team'} <{settings.RESEND_FROM_EMAIL or 'classes@mail.technula.com'}>"
    plain_text = re.sub(r'<[^>]+>', ' ', html_content)
    plain_text = " ".join(plain_text.split())

    body = {
        "from": from_address,
        "to": [to_email],
        "subject": subject,
        "html": html_content,
        "text": plain_text,
    }

    try:
        timeout_val = getattr(settings, "RESEND_TIMEOUT_SECONDS", 20) or 20
        res = requests.post(url, headers=headers, json=body, timeout=timeout_val)
        if res.status_code in [200, 201]:
            resp_data = res.json()
            logger.info(f"[Resend Email] Successfully sent email to {to_email}: {resp_data.get('id')}")
            log_mongo_document("email_logs", {
                "to": to_email,
                "mode": "LIVE",
                "status": "SENT",
                "response": resp_data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return True
        else:
            logger.error(f"[Resend Email] API returned status {res.status_code}: {res.text}")
            log_mongo_document("email_logs", {
                "to": to_email,
                "mode": "LIVE",
                "status": "FAILED",
                "error": res.text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return False
    except Exception as e:
        logger.error(f"[Resend Email] Failed to send email to {to_email}: {e}")
        log_mongo_document("email_logs", {
            "to": to_email,
            "mode": "LIVE",
            "status": "FAILED",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return False


# ── PUSH NOTIFICATIONS (EXPO PUSH & FIREBASE FCM) ─────────────────────
def send_push_notification(
    fcm_token: str,
    title: str,
    body: str,
    data_payload: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Send push notification to mobile devices.
    Supports:
    1. Expo Push Service API (for ExponentPushToken[...] tokens from Expo Go / dev client)
    2. Firebase Cloud Messaging (FCM HTTP v1 via firebase_admin for native tokens)
    Both configure high-priority Android heads-up alerts with sound and channel 'schoolos_alerts'.
    """
    if not fcm_token:
        logger.info(f"[Push Notice] No device token available for push: {title}")
        return False

    # Clean data payload so all values are strings (required by FCM and Expo)
    safe_data: Dict[str, str] = {}
    if data_payload:
        for k, v in data_payload.items():
            if v is not None:
                safe_data[str(k)] = str(v)

    # 1. Check for Expo Push Token
    if fcm_token.startswith("ExponentPushToken") or fcm_token.startswith("ExpoPushToken"):
        try:
            import requests
            expo_payload = {
                "to": fcm_token,
                "sound": "default",
                "title": title,
                "body": body,
                "channelId": "schoolos_alerts",
                "priority": "high",
                "badge": 1,
                "data": safe_data,
            }
            resp = requests.post(
                "https://exp.host/--/api/v2/push/send",
                json=expo_payload,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                    "Content-Type": "application/json",
                },
                timeout=8,
            )
            res_data = resp.json()
            logger.info(f"[Expo Push] Delivered to {fcm_token[:20]}...: {res_data}")
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"[Expo Push] Failed to deliver: {e}")
            return False

    # 2. Native Firebase FCM Push Notification
    if not settings.FIREBASE_CREDENTIALS_JSON:
        logger.info(f"[FCM Mock] Would send push to {fcm_token[:15]}...: {title}")
        return True

    try:
        import importlib
        firebase_admin = importlib.import_module("firebase_admin")
        messaging = importlib.import_module("firebase_admin.messaging")
        credentials = importlib.import_module("firebase_admin.credentials")

        if not getattr(firebase_admin, "_apps", None):
            cred_path = settings.FIREBASE_CREDENTIALS_JSON
            if cred_path and not os.path.isabs(cred_path):
                backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                candidate = os.path.join(backend_dir, cred_path)
                if os.path.exists(candidate):
                    cred_path = candidate
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)

        # Android Heads-Up Notification configuration (pops from top with sound & ringtone like Zomato)
        android_config = messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                channel_id="schoolos_alerts",
                sound="default",
                priority="high",
                default_sound=True,
                default_vibrate_timings=True,
                notification_priority="PRIORITY_MAX",
            ),
        )

        apns_config = messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    sound="default",
                    badge=1,
                )
            )
        )

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            android=android_config,
            apns=apns_config,
            data=safe_data,
            token=fcm_token,
        )
        response = messaging.send(message)
        logger.info(f"[FCM Push] Sent successfully: {response}")
        return True
    except Exception as e:
        logger.warning(f"[FCM Push] Failed to deliver: {e}")
        return False


# ── UNIFIED MULTI-CHANNEL DISPATCH WITH PERMISSION CHECKS ─────────────
def dispatch_multi_channel_notification(
    db,
    school_id,
    user_id,
    title: str,
    message: str,
    event_type: str = "GENERAL",
    phone: Optional[str] = None,
    email: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    override_whatsapp: bool = False,
    override_email: bool = False,
) -> Dict[str, Any]:
    """
    Dispatches notification across channels while strictly honoring parent/user channel opt-in permissions.
    - In-App: ALWAYS delivered and saved to user inbox.
    - WhatsApp: Delivered ONLY IF user.allow_whatsapp is True (or override_whatsapp is True).
    - Email: Delivered ONLY IF user.allow_email is True (or override_email is True).
    - FCM: Delivered if fcm_token exists.
    """
    from models.user_db import UserDB

    user = db.query(UserDB).filter(UserDB.id == user_id).first() if user_id else None

    # Target destinations
    dest_phone = phone or (user.phone if user else None)
    dest_email = email or (user.email if user else None)
    allow_wa = override_whatsapp or (getattr(user, "allow_whatsapp", True) if user else True)
    allow_em = override_email or (getattr(user, "allow_email", True) if user else True)
    fcm_token = getattr(user, "fcm_token", None) if user else None

    dispatch_report = {
        "in_app": True,
        "whatsapp": False,
        "email": False,
        "push": False,
        "whatsapp_skipped_reason": None,
        "email_skipped_reason": None,
    }

    # 1. In-App Notification (Always enabled)
    if user_id:
        create_in_app_notification(
            db=db,
            school_id=school_id,
            user_id=user_id,
            title=title,
            message=message,
            event_type=event_type,
            payload=payload,
        )

    # 2. WhatsApp Notification
    if dest_phone:
        if allow_wa:
            wa_ok = send_whatsapp_message(
                to_phone=dest_phone,
                custom_text=f"*{title}*\n{message}",
            )
            dispatch_report["whatsapp"] = wa_ok
        else:
            dispatch_report["whatsapp_skipped_reason"] = "User opted out of WhatsApp notifications"
    else:
        dispatch_report["whatsapp_skipped_reason"] = "No phone number available"

    # 3. Email Notification
    if dest_email:
        if allow_em:
            email_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
                <h2 style="color: #635bff; margin-top: 0;">{title}</h2>
                <p style="font-size: 15px; color: #334155; line-height: 1.6;">{message}</p>
                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
                <p style="font-size: 12px; color: #94a3b8;">School Management System</p>
            </div>
            """
            em_ok = send_email(to_email=dest_email, subject=title, html_content=email_html)
            dispatch_report["email"] = em_ok
        else:
            dispatch_report["email_skipped_reason"] = "User opted out of Email notifications"
    else:
        dispatch_report["email_skipped_reason"] = "No email address available"

    # 4. FCM Mobile Push
    if fcm_token:
        push_ok = send_push_notification(
            fcm_token=fcm_token,
            title=title,
            body=message,
            data_payload={"event_type": event_type, **(payload or {})},
        )
        dispatch_report["push"] = push_ok

    return dispatch_report


# ── AUTO-NOTIFY PARENTS OF A STUDENT ──────────────────────────────────
def notify_parents_of_student(
    db,
    student_id,
    school_id,
    title: str,
    message: str,
    event_type: str = "GENERAL",
    payload: Optional[Dict[str, Any]] = None,
):
    """
    Convenience function: Finds all parent UserDB records linked to a student
    and dispatches multi-channel notifications to each of them.
    Called automatically by every backend API (attendance, marks, homework, etc.)
    """
    from models.parent_student_db import ParentStudentDB
    from models.user_db import UserDB

    try:
        # Get all parent user IDs linked to this student
        parent_links = (
            db.query(ParentStudentDB)
            .filter(ParentStudentDB.student_id == student_id)
            .all()
        )

        results = []
        for link in parent_links:
            parent = db.query(UserDB).filter(UserDB.id == link.parent_user_id).first()
            if parent:
                result = dispatch_multi_channel_notification(
                    db=db,
                    school_id=school_id,
                    user_id=parent.id,
                    title=title,
                    message=message,
                    event_type=event_type,
                    phone=parent.phone,
                    email=parent.email,
                    payload=payload,
                )
                results.append(result)

        return results
    except Exception as e:
        logger.error(f"[AutoNotify] Failed to notify parents of student {student_id}: {e}")
        return []


def notify_class_parents(
    db,
    school_id,
    class_name: str,
    section: Optional[str] = None,
    title: str = "",
    message: str = "",
    event_type: str = "GENERAL",
    payload: Optional[Dict[str, Any]] = None,
):
    """
    Convenience function: Finds all students in a class/section and notifies their linked parents.
    Used for class-wide homework, announcements, datesheets, etc.
    """
    from models.student_db import StudentDB

    try:
        query = db.query(StudentDB).filter(
            StudentDB.school_id == school_id,
            StudentDB.current_class == class_name
        )
        if section:
            query = query.filter(StudentDB.section == section)
        students = query.all()

        total_notified = 0
        for st in students:
            res = notify_parents_of_student(
                db=db,
                student_id=st.id,
                school_id=school_id,
                title=title,
                message=message,
                event_type=event_type,
                payload=payload,
            )
            total_notified += len(res)
        return {"students_count": len(students), "dispatched_notifications": total_notified}
    except Exception as e:
        logger.error(f"[AutoNotifyClass] Failed to notify class {class_name}-{section}: {e}")
        return {"students_count": 0, "dispatched_notifications": 0}
