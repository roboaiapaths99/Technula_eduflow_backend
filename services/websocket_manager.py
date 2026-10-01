"""
Real-time WebSocket & Event Broadcasting Manager for Technula EduFlow.
Supports user channels, school broadcasts, and 1:1 conversation subscriptions.
"""
from __future__ import annotations
import asyncio
import json
import logging
from typing import Dict, Set, Optional, Any
from fastapi import WebSocket

logger = logging.getLogger("realtime_manager")


class ConnectionManager:
    def __init__(self):
        # Maps user_id -> Set of active WebSockets
        self.user_connections: Dict[str, Set[WebSocket]] = {}
        # Maps school_id -> Set of active WebSockets
        self.school_connections: Dict[str, Set[WebSocket]] = {}
        # Maps conversation_id -> Set of active WebSockets
        self.conversation_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: str, school_id: Optional[str] = None):
        await websocket.accept()
        async with self._lock:
            # Register user
            if user_id not in self.user_connections:
                self.user_connections[user_id] = set()
            self.user_connections[user_id].add(websocket)

            # Register school
            if school_id:
                if school_id not in self.school_connections:
                    self.school_connections[school_id] = set()
                self.school_connections[school_id].add(websocket)

        logger.info(f"[WS] Connected user {user_id} in school {school_id}")

    async def disconnect(self, websocket: WebSocket, user_id: str, school_id: Optional[str] = None):
        async with self._lock:
            if user_id in self.user_connections:
                self.user_connections[user_id].discard(websocket)
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]

            if school_id and school_id in self.school_connections:
                self.school_connections[school_id].discard(websocket)
                if not self.school_connections[school_id]:
                    del self.school_connections[school_id]

            # Clean from conversations
            for conv_id in list(self.conversation_connections.keys()):
                self.conversation_connections[conv_id].discard(websocket)
                if not self.conversation_connections[conv_id]:
                    del self.conversation_connections[conv_id]

        logger.info(f"[WS] Disconnected user {user_id}")

    async def subscribe_conversation(self, websocket: WebSocket, conversation_id: str):
        async with self._lock:
            if conversation_id not in self.conversation_connections:
                self.conversation_connections[conversation_id] = set()
            self.conversation_connections[conversation_id].add(websocket)

    async def unsubscribe_conversation(self, websocket: WebSocket, conversation_id: str):
        async with self._lock:
            if conversation_id in self.conversation_connections:
                self.conversation_connections[conversation_id].discard(websocket)
                if not self.conversation_connections[conversation_id]:
                    del self.conversation_connections[conversation_id]

    async def send_to_user(self, user_id: str, message: Dict[str, Any]):
        """Send an event payload directly to a specific user's active sockets."""
        sockets = list(self.user_connections.get(str(user_id), []))
        if not sockets:
            return
        payload = json.dumps(message)
        dead = []
        for ws in sockets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for d in dead:
                    self.user_connections.get(str(user_id), set()).discard(d)

    async def broadcast_to_school(self, school_id: str, message: Dict[str, Any]):
        """Broadcast an event payload to all users connected within a school tenant."""
        sockets = list(self.school_connections.get(str(school_id), []))
        if not sockets:
            return
        payload = json.dumps(message)
        dead = []
        for ws in sockets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for d in dead:
                    self.school_connections.get(str(school_id), set()).discard(d)

    async def broadcast_to_conversation(self, conversation_id: str, message: Dict[str, Any]):
        """Broadcast chat messages to active chat participants."""
        sockets = list(self.conversation_connections.get(conversation_id, []))
        if not sockets:
            return
        payload = json.dumps(message)
        dead = []
        for ws in sockets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for d in dead:
                    self.conversation_connections.get(conversation_id, set()).discard(d)

    def dispatch_sync(self, coro):
        """Safe non-blocking helper to schedule async broadcast from sync FastAPI routes."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(coro)
            else:
                loop.run_until_complete(coro)
        except RuntimeError:
            # New thread or no loop running
            asyncio.run(coro)
        except Exception as e:
            logger.warning(f"Error dispatching websocket event: {e}")


# Global Singleton Manager
manager = ConnectionManager()
