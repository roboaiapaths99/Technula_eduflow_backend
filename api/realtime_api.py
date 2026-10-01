"""
Real-time WebSocket & Server-Sent Events (SSE) API.
Enables instant chat message delivery, live attendance pulses, and dashboard KPI streaming.
"""
from __future__ import annotations
import asyncio
import json
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException
from fastapi.responses import StreamingResponse
from jose import jwt, JWTError

from core.config import settings
from db.session import get_db
from models.user_db import UserDB
from services.websocket_manager import manager
from auth.dependencies import get_current_user

logger = logging.getLogger("realtime_api")

router = APIRouter(prefix="/realtime", tags=["Realtime & WebSockets"])


def _authenticate_ws_token(token: str) -> Optional[dict]:
    """Decode JWT token for WebSocket connection authentication."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """
    WebSocket endpoint for authenticated users.
    Connect with ws://host:8000/realtime/ws?token=<JWT_TOKEN>
    """
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    payload = _authenticate_ws_token(token)
    if not payload:
        await websocket.close(code=4003, reason="Invalid or expired token")
        return

    user_id = str(payload.get("sub") or payload.get("id"))
    school_id = str(payload.get("school_id") or "")

    await manager.connect(websocket, user_id=user_id, school_id=school_id)
    try:
        # Send initial connection handshake
        await websocket.send_text(json.dumps({
            "type": "connection_established",
            "user_id": user_id,
            "school_id": school_id,
            "timestamp": asyncio.get_event_loop().time()
        }))

        while True:
            raw_data = await websocket.receive_text()
            try:
                msg = json.loads(raw_data)
                msg_type = msg.get("type")

                if msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

                elif msg_type == "subscribe_chat":
                    conv_id = msg.get("conversation_id")
                    if conv_id:
                        await manager.subscribe_conversation(websocket, conv_id)
                        await websocket.send_text(json.dumps({
                            "type": "subscribed",
                            "conversation_id": conv_id
                        }))

                elif msg_type == "unsubscribe_chat":
                    conv_id = msg.get("conversation_id")
                    if conv_id:
                        await manager.unsubscribe_conversation(websocket, conv_id)
                        await websocket.send_text(json.dumps({
                            "type": "unsubscribed",
                            "conversation_id": conv_id
                        }))

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        await manager.disconnect(websocket, user_id=user_id, school_id=school_id)
    except Exception as e:
        logger.warning(f"WebSocket error for user {user_id}: {e}")
        await manager.disconnect(websocket, user_id=user_id, school_id=school_id)


@router.get("/sse/kpis")
async def sse_dashboard_kpis(
    school_id: Optional[str] = None,
    user=Depends(get_current_user),
):
    """
    Server-Sent Events (SSE) endpoint for live dashboard KPI refresh.
    Pushes periodic KPI heartbeat pulses to connected browsers.
    """
    target_school = str(school_id or user.school_id or "")

    async def event_generator():
        try:
            for iteration in range(60):  # Stream up to 5-10 minutes per connection
                pulse_data = {
                    "event": "kpi_pulse",
                    "school_id": target_school,
                    "iteration": iteration,
                    "status": "healthy"
                }
                yield f"data: {json.dumps(pulse_data)}\n\n"
                await asyncio.sleep(10)  # Pulse every 10 seconds
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/pulse")
async def trigger_realtime_pulse(
    event_type: str,
    target_school_id: Optional[str] = None,
    target_user_id: Optional[str] = None,
    data: Optional[dict] = None,
    user=Depends(get_current_user),
):
    """Admin endpoint to broadcast an instant real-time event to school or user."""
    payload = {
        "type": event_type,
        "sender": str(user.id),
        "data": data or {}
    }
    if target_user_id:
        await manager.send_to_user(target_user_id, payload)
    elif target_school_id:
        await manager.broadcast_to_school(target_school_id, payload)
    elif user.school_id:
        await manager.broadcast_to_school(str(user.school_id), payload)

    return {"status": "dispatched", "type": event_type}
