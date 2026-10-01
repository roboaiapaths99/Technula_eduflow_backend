"""
Notification API — In-app notification center & FCM device token registration.
SECURED: All endpoints require authentication.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.session import get_db
from models.notification_db import NotificationDB
from models.user_db import UserDB
from auth.dependencies import get_current_user

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class RegisterDeviceTokenRequest(BaseModel):
    fcm_token: Optional[str] = None
    token: Optional[str] = None

    def get_token(self) -> str:
        t = self.fcm_token or self.token
        if not t:
            raise ValueError("Device token is required")
        return t.strip()


@router.get("/")
def get_user_notifications(
    unread_only: bool = False,
    limit: int = 30,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get in-app notifications for the authenticated user."""
    query = (
        db.query(NotificationDB)
        .filter(NotificationDB.recipient_user_id == user.id, NotificationDB.channel == "IN_APP")
    )
    if unread_only:
        query = query.filter(NotificationDB.read_at == None)

    items = query.order_by(NotificationDB.created_at.desc()).limit(limit).all()

    return [
        {
            "id": str(n.id),
            "title": n.title,
            "message": n.message,
            "event_type": n.event_type,
            "payload_json": n.payload_json,
            "status": n.status,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "read_at": n.read_at.isoformat() if n.read_at else None,
        }
        for n in items
    ]


@router.post("/{notification_id}/mark-read")
def mark_notification_read(
    notification_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a notification as read."""
    notif = db.query(NotificationDB).filter(
        NotificationDB.id == notification_id,
        NotificationDB.recipient_user_id == user.id,
    ).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.read_at = datetime.now(timezone.utc)
    notif.status = "READ"
    db.commit()
    return {"status": "success"}


@router.post("/register-device")
@router.post("/device-token")
def register_device_token(
    req: RegisterDeviceTokenRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save FCM/Expo device push token for mobile notifications."""
    token_val = req.get_token()
    user.fcm_token = token_val
    db.commit()
    return {"status": "success", "message": "Device push token registered", "token": token_val[:15] + "..."}


@router.post("/test-push")
def test_push_notification(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Send an immediate test push notification and in-app alert to the current user.
    Tests FCM, Expo Push, and In-App Heads-up popup flow.
    """
    from services.notification_service import dispatch_multi_channel_notification

    report = dispatch_multi_channel_notification(
        db=db,
        school_id=user.school_id,
        user_id=user.id,
        title="🔔 School Test Alert",
        message="Your device is successfully connected to the School Notification System! Notifications will appear from above with ringtone.",
        event_type="TEST_ALERT",
        phone=user.phone,
        email=user.email,
        payload={
            "screen": "notices",
            "type": "TEST_ALERT",
            "test": "true",
        },
    )
    return {
        "status": "success",
        "message": "Test alert dispatched",
        "has_token": bool(user.fcm_token),
        "token_preview": user.fcm_token[:20] + "..." if user.fcm_token else None,
        "dispatch_report": report,
    }
