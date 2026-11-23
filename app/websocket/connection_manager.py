from typing import Any
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[UUID, set[WebSocket]] = {}

    async def connect(self, user_id: UUID, websocket: WebSocket) -> None:
        if websocket.application_state == WebSocketState.CONNECTING:
            await websocket.accept()
        self.active_connections.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: UUID, websocket: WebSocket) -> None:
        connections = self.active_connections.get(user_id)

        if connections is None:
            return

        connections.discard(websocket)

        if not connections:
            self.active_connections.pop(user_id, None)

    async def send_personal_message(
        self,
        message: dict[str, Any],
        websocket: WebSocket,
    ) -> bool:
        try:
            await websocket.send_json(message)
            return True
        except (WebSocketDisconnect, RuntimeError):
            return False

    async def send_to_user(
        self,
        user_id: UUID,
        message: dict[str, Any],
    ) -> int:
        connections = self.active_connections.get(user_id)

        if not connections:
            return 0

        disconnected_connections = set()
        successful_deliveries = 0

        for websocket in connections.copy():
            try:
                await websocket.send_json(message)
                successful_deliveries += 1
            except (WebSocketDisconnect, RuntimeError):
                disconnected_connections.add(websocket)

        for websocket in disconnected_connections:
            self.disconnect(user_id, websocket)

        return successful_deliveries

    async def broadcast(self, message: dict[str, Any]) -> int:
        successful_deliveries = 0

        for user_id in list(self.active_connections):
            successful_deliveries += await self.send_to_user(
                user_id=user_id,
                message=message,
            )

        return successful_deliveries

    def is_user_online(self, user_id: UUID) -> bool:
        return bool(self.active_connections.get(user_id))

    def get_online_users(self) -> list[UUID]:
        return list(self.active_connections.keys())

    def get_connection_count(self, user_id: UUID) -> int:
        return len(self.active_connections.get(user_id, set()))

    def get_total_connections(self) -> int:
        return sum(len(connections) for connections in self.active_connections.values())


manager = ConnectionManager()
