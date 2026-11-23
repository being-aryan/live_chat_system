from datetime import datetime
from typing import Any

import streamlit as st


def format_timestamp(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%I:%M %p")
    except (TypeError, ValueError):
        return value


def render_message(message: dict[str, Any], current_user_id: str) -> None:
    own_message = str(message.get("sender_id")) == str(current_user_id)
    content = message.get("content")
    deleted = message.get("deleted_at") is not None or content is None
    alignment = "right" if own_message else "left"
    bubble_class = "message-own" if own_message else "message-other"
    label = "You" if own_message else "Participant"
    timestamp = format_timestamp(message.get("created_at"))
    text = "This message was deleted" if deleted else str(content)
    st.markdown(
        f'<div class="message-row {alignment}"><div class="message-bubble {bubble_class}">'
        f'<div class="message-label">{label}</div><div>{_escape(text)}</div>'
        f'<div class="message-time">{timestamp}</div></div></div>',
        unsafe_allow_html=True,
    )


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
        .replace("\n", "<br>")
    )
