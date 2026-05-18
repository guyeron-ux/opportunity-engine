import asyncio
import json
import logging
from typing import Any
from fastapi import WebSocket

log = logging.getLogger("websocket")


class WebSocketManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)
        log.info("WebSocket connected. Total: %d", len(self._connections))

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)
        log.info("WebSocket disconnected. Total: %d", len(self._connections))

    async def broadcast(self, message: Any):
        if not self._connections:
            return
        payload = json.dumps(message, default=str)
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception as e:
                log.warning("WS send failed: %s", e)
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ws_manager = WebSocketManager()
