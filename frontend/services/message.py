from typing import Any

from frontend.api.client import APIClient


class MessageService:
    def __init__(self, access_token: str) -> None:
        self.client = APIClient(access_token=access_token)

    def get_messages(self, conversation_id: str, limit: int = 50, before_created_at: str | None = None, before_id: str | None = None) -> dict[str, Any]:
        return self.client.get_messages(conversation_id, limit, before_created_at, before_id)

    def send_message(self, conversation_id: str, content: str) -> dict[str, Any]:
        return self.client.send_message(conversation_id, content)

    def update_message(self, message_id: str, content: str) -> dict[str, Any]:
        return self.client.update_message(message_id, content)

    def delete_message(self, message_id: str) -> dict[str, Any]:
        return self.client.delete_message(message_id)

    def mark_delivered(self, message_id: str) -> dict[str, Any]:
        return self.client.mark_message_delivered(message_id)

    def mark_read(self, message_id: str) -> dict[str, Any]:
        return self.client.mark_message_read(message_id)

    def mark_conversation_read(self, conversation_id: str, message_id: str) -> dict[str, Any]:
        return self.client.mark_conversation_read(conversation_id, message_id)

    def get_receipts(self, message_id: str) -> dict[str, Any]:
        return self.client.get_message_receipts(message_id)
