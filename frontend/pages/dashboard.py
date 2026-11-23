from typing import Any

import streamlit as st

from frontend.api.client import APIClient, APIError
from frontend.components.chat_message import render_message
from frontend.services.auth import AuthService
from frontend.services.conversation import ConversationService
from frontend.services.message import MessageService
from frontend.services.websocket import WebSocketService


def _conversation_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    return data.get("conversations", []) if isinstance(data, dict) else []


def _conversation_name(item: dict[str, Any]) -> str:
    conversation = item.get("conversation", item)
    name = conversation.get("name")
    if name:
        return name
    if conversation.get("conversation_type") == "group":
        return "Unnamed group"
    return "Direct conversation"


def _show_error(exc: APIError) -> None:
    st.error(str(exc.detail))


def _start_direct_chat(service: ConversationService, user: dict[str, Any]) -> None:
    try:
        conversation = service.create_direct_conversation(user["id"])
        st.session_state["active_conversation_id"] = str(conversation["id"])
        st.session_state["page"] = "dashboard"
        st.rerun()
    except APIError as exc:
        _show_error(exc)


def _render_new_chat(service: ConversationService) -> None:
    with st.expander("＋ Start a conversation", expanded=False):
        query = st.text_input("Search users", key="user_search_query", placeholder="Enter at least 2 characters")
        if len(query.strip()) >= 2:
            try:
                users = service.search_users(query.strip())
                if not users:
                    st.caption("No users found.")
                for user in users:
                    col_user, col_action = st.columns([4, 1])
                    col_user.write(f"**{user['username']}**")
                    col_user.caption(user["id"])
                    if col_action.button("Chat", key=f"direct_{user['id']}"):
                        _start_direct_chat(service, user)
            except APIError as exc:
                _show_error(exc)
        st.divider()
        st.markdown("**Create a group**")
        group_name = st.text_input("Group name", key="new_group_name")
        group_query = st.text_input("Find group members", key="group_member_search", placeholder="Search by username")
        selected_members = st.session_state.setdefault("group_member_ids", [])
        if len(group_query.strip()) >= 2:
            try:
                candidates = service.search_users(group_query.strip())
                for candidate in candidates:
                    selected = candidate["id"] in selected_members
                    if st.checkbox(
                        candidate["username"],
                        value=selected,
                        key=f"group_select_{candidate['id']}",
                    ):
                        if candidate["id"] not in selected_members:
                            selected_members.append(candidate["id"])
                    elif candidate["id"] in selected_members:
                        selected_members.remove(candidate["id"])
            except APIError as exc:
                _show_error(exc)
        st.caption(f"Selected members: {len(selected_members)}")
        if st.button("Create group", type="primary", use_container_width=True):
            if not group_name.strip() or not selected_members:
                st.warning("Enter a group name and select at least one member.")
            else:
                try:
                    created = service.create_group_conversation(group_name.strip(), selected_members.copy())
                    st.session_state["active_conversation_id"] = str(created["id"])
                    st.session_state["group_member_ids"] = []
                    st.rerun()
                except APIError as exc:
                    _show_error(exc)


def _render_group_settings(service: ConversationService, conversation: dict[str, Any]) -> None:
    if conversation.get("conversation_type") != "group":
        return
    with st.expander("Group settings"):
        new_name = st.text_input("Group name", value=conversation.get("name") or "", key=f"rename_{conversation['id']}")
        if st.button("Rename group", key=f"rename_btn_{conversation['id']}"):
            try:
                service.rename_group(str(conversation["id"]), new_name.strip())
                st.success("Group renamed.")
                st.rerun()
            except APIError as exc:
                _show_error(exc)
        st.markdown("**Members**")
        for member in conversation.get("members", []):
            st.caption(f"{member.get('user_id')} · {member.get('role', 'member')}")
        member_id = st.text_input("Add member by user ID", key=f"add_member_{conversation['id']}")
        if st.button("Add member", key=f"add_member_btn_{conversation['id']}"):
            try:
                service.add_group_member(str(conversation["id"]), member_id.strip())
                st.success("Member added.")
                st.rerun()
            except APIError as exc:
                _show_error(exc)
        if st.button("Leave group", key=f"leave_{conversation['id']}"):
            try:
                service.leave_group(str(conversation["id"]))
                st.session_state.pop("active_conversation_id", None)
                st.rerun()
            except APIError as exc:
                _show_error(exc)


@st.fragment(run_every="3s")
def _render_chat(
    access_token: str,
    current_user: dict[str, Any],
    conversation: dict[str, Any],
    websocket_service: WebSocketService | None,
) -> None:
    conversation_id = str(conversation["id"])
    st.markdown('<div class="chat-header">', unsafe_allow_html=True)
    st.subheader(conversation.get("name") or ("Group chat" if conversation.get("conversation_type") == "group" else "Direct conversation"))
    members = conversation.get("members", [])
    st.caption(f"{len(members)} participant(s) · {conversation.get('conversation_type', 'conversation').title()}")
    st.markdown("</div>", unsafe_allow_html=True)
    service = MessageService(access_token)

    try:
        result = service.get_messages(conversation_id, limit=50)
        messages = list(reversed(result.get("messages", [])))
    except APIError as exc:
        _show_error(exc)
        return

    for message in messages:
        render_message(message, str(current_user.get("id", "")))
        if str(message.get("sender_id")) != str(current_user.get("id")) and message.get("id"):
            try:
                service.mark_delivered(str(message["id"]))
            except APIError:
                pass

    unread_candidates = [m for m in messages if str(m.get("sender_id")) != str(current_user.get("id")) and m.get("id")]
    if unread_candidates:
        try:
            service.mark_conversation_read(conversation_id, str(unread_candidates[-1]["id"]))
        except APIError:
            pass

    st.divider()
    with st.form(f"send_message_form_{conversation_id}", clear_on_submit=True):
        content = st.text_area("Message", placeholder="Write a message…", max_chars=5000, label_visibility="collapsed", height=80)
        send = st.form_submit_button("Send message", type="primary", use_container_width=True)
    if send:
        if not content.strip():
            st.warning("Message cannot be empty.")
        else:
            try:
                service.send_message(conversation_id, content.strip())
                st.rerun()
            except APIError as exc:
                _show_error(exc)

    own_messages = [m for m in messages if str(m.get("sender_id")) == str(current_user.get("id")) and m.get("content")]
    if own_messages:
        with st.expander("Edit or delete a recent message"):
            selected = st.selectbox(
                "Your messages",
                own_messages[-20:],
                format_func=lambda item: str(item.get("content", ""))[:70],
                key=f"message_edit_select_{conversation_id}",
            )
            edited = st.text_area("Updated message", value=selected.get("content", ""), max_chars=5000, key=f"message_edit_text_{conversation_id}")
            col_edit, col_delete = st.columns(2)
            if col_edit.button("Save edit", key=f"edit_msg_{conversation_id}", use_container_width=True):
                try:
                    service.update_message(str(selected["id"]), edited.strip())
                    st.success("Message updated.")
                    st.rerun()
                except APIError as exc:
                    _show_error(exc)
            if col_delete.button("Delete message", key=f"delete_msg_{conversation_id}", use_container_width=True):
                try:
                    service.delete_message(str(selected["id"]))
                    st.success("Message deleted.")
                    st.rerun()
                except APIError as exc:
                    _show_error(exc)

    _render_group_settings(ConversationService(access_token), conversation)
    if websocket_service and not websocket_service.connected:
        st.caption("Real-time connection reconnecting. Messages also refresh when you interact with the chat.")


def render_dashboard(auth_service: AuthService) -> None:
    user = st.session_state.get("current_user", {})
    access_token = st.session_state.get("access_token")
    if not access_token:
        st.session_state["page"] = "login"
        st.rerun()
        return

    service = ConversationService(access_token)
    with st.sidebar:
        st.title("💬 Live Chat")
        st.caption(user.get("username", "User"))
        if st.button("Refresh inbox", use_container_width=True):
            st.rerun()
        _render_new_chat(service)
        st.divider()
        st.markdown("**Conversations**")
        try:
            inbox = _conversation_items(service.get_inbox())
            for item in inbox:
                conversation = item.get("conversation", {})
                conversation_id = str(conversation.get("id", ""))
                if not conversation_id:
                    continue
                title = _conversation_name(item)
                preview = item.get("last_message_content") or "No messages yet"
                unread = int(item.get("unread_count", 0) or 0)
                label = f"{title}  ·  {unread}" if unread else title
                if st.button(f"{label}\n{str(preview)[:42]}", key=f"open_{conversation_id}", use_container_width=True):
                    st.session_state["active_conversation_id"] = conversation_id
                    st.rerun()
        except APIError as exc:
            _show_error(exc)
        st.divider()
        if st.button("Log out", use_container_width=True):
            try:
                auth_service.logout()
            except APIError as exc:
                _show_error(exc)
            st.session_state["page"] = "login"
            st.rerun()
        if st.button("Log out all devices", use_container_width=True):
            try:
                auth_service.logout_all()
            except APIError as exc:
                _show_error(exc)
            st.session_state["page"] = "login"
            st.rerun()

    active_id = st.session_state.get("active_conversation_id")
    if not active_id:
        st.title(f"Welcome, {user.get('username', 'there')}!")
        st.info("Choose a conversation from the left, or start a new chat.")
        st.markdown("### Your chat workspace")
        st.write("Direct messages, group conversations, message history and read receipts are available from this workspace.")
        return

    try:
        conversation = service.get_conversation(str(active_id))
    except APIError as exc:
        _show_error(exc)
        st.session_state.pop("active_conversation_id", None)
        return

    if st.button("← Back to welcome"):
        st.session_state.pop("active_conversation_id", None)
        st.rerun()

    websocket_service = st.session_state.get("websocket_service")
    if websocket_service:
        for event in websocket_service.drain_events():
            event_type = event.get("type")
            if event_type in {"message.new", "message.updated", "message.deleted"}:
                st.session_state["last_realtime_event"] = event_type

    _render_chat(access_token, user, conversation, websocket_service)
