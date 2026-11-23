from typing import Any, Callable

from frontend.api.client import APIClient


class ConversationService:
    def __init__(
        self,
        access_token: str,
        refresh_token: str | None = None,
        on_token_refreshed: Callable[[str, str], None] | None = None,
    ) -> None:
        self.client = APIClient(
            access_token=access_token,
            refresh_token=refresh_token,
            on_token_refreshed=on_token_refreshed,
        )

    def get_inbox(self) -> dict[str, Any]:
        return self.client.get_conversation_inbox()

    def get_all_conversations(self) -> list[dict[str, Any]]:
        return self.client.get_conversations()

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        return self.client.get_conversation(conversation_id)

    def create_direct_conversation(self, other_user_id: str) -> dict[str, Any]:
        return self.client.create_direct_conversation(other_user_id)

    def create_group_conversation(self, name: str, member_ids: list[str]) -> dict[str, Any]:
        return self.client.create_group_conversation(name, member_ids)

    def search_users(self, query: str, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        return self.client.search_users(query, limit, offset)

    def rename_group(self, conversation_id: str, name: str) -> dict[str, Any]:
        return self.client.rename_group(conversation_id, name)

    def add_group_member(self, conversation_id: str, user_id: str) -> dict[str, Any]:
        return self.client.add_group_member(conversation_id, user_id)

    def remove_group_member(self, conversation_id: str, user_id: str) -> dict[str, Any]:
        return self.client.remove_group_member(conversation_id, user_id)

    def leave_group(self, conversation_id: str) -> dict[str, Any]:
        return self.client.leave_group(conversation_id)
