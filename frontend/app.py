import streamlit as st
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from api_client import ChatAPIClient, APIError

TIMEZONES = {
    "Asia/Kolkata (IST +5:30)": "Asia/Kolkata",
    "UTC (Coordinated Universal Time)": "UTC",
    "America/New_York (US Eastern)": "America/New_York",
    "America/Chicago (US Central)": "America/Chicago",
    "America/Los_Angeles (US Pacific)": "America/Los_Angeles",
    "Europe/London (GMT/BST)": "Europe/London",
    "Asia/Dubai (GST +4:00)": "Asia/Dubai",
    "Asia/Singapore (SGT +8:00)": "Asia/Singapore",
}

# Page setup
st.set_page_config(
    page_title="Live Chat",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------- Session State Initialization -----------------
st.session_state.setdefault("access_token", None)
st.session_state.setdefault("refresh_token", None)
st.session_state.setdefault("current_user", None)
st.session_state.setdefault("active_conv_id", None)
st.session_state.setdefault("active_conv_name", None)
st.session_state.setdefault("active_other_user_id", None)
st.session_state.setdefault("active_other_username", None)
st.session_state.setdefault("user_cache", {})  # user_id -> username
st.session_state.setdefault("last_read_cached", {})
st.session_state.setdefault("display_timezone", "Asia/Kolkata (IST +5:30)")


def get_current_zoneinfo() -> ZoneInfo:
    tz_label = st.session_state.get("display_timezone", "Asia/Kolkata (IST +5:30)")
    tz_key = TIMEZONES.get(tz_label, "Asia/Kolkata")
    try:
        return ZoneInfo(tz_key)
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def on_token_refresh(new_access: str, new_refresh: str):
    st.session_state["access_token"] = new_access
    st.session_state["refresh_token"] = new_refresh


def get_client() -> ChatAPIClient:
    return ChatAPIClient(
        access_token=st.session_state.get("access_token"),
        refresh_token=st.session_state.get("refresh_token"),
        on_tokens_refreshed=on_token_refresh,
    )


def format_timestamp(dt_str: str | None) -> str:
    if not dt_str:
        return ""
    try:
        clean_str = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        target_tz = get_current_zoneinfo()
        local_dt = dt.astimezone(target_tz)
        return local_dt.strftime("%I:%M %p · %b %d")
    except Exception:
        return str(dt_str)


def format_last_seen(dt_str: str | None) -> str:
    if not dt_str:
        return "Offline"
    try:
        clean_str = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        target_tz = get_current_zoneinfo()
        local_dt = dt.astimezone(target_tz)
        return f"Last seen {local_dt.strftime('%I:%M %p · %b %d')}"
    except Exception:
        return "Offline"


def resolve_username(client: ChatAPIClient, user_id: str, default: str = "User") -> str:
    cache = st.session_state["user_cache"]
    if user_id in cache:
        return cache[user_id]
    try:
        user_info = client.get_user_by_id(user_id)
        name = user_info.get("username", default)
        cache[user_id] = name
        return name
    except Exception:
        if user_id == st.session_state.get("active_other_user_id"):
            other_name = st.session_state.get("active_other_username")
            if other_name:
                cache[user_id] = other_name
                return other_name
        return default


# ----------------- Authentication Views -----------------
def render_auth():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("💬 Live Chat System")
        st.caption("A fast, production-ready real-time communication platform.")

        tab_login, tab_register = st.tabs(["🔑 Login", "✨ Register"])

        client = get_client()

        with tab_login:
            st.subheader("Welcome Back")
            with st.form("login_form", clear_on_submit=False):
                email = st.text_input("Email", placeholder="user@example.com").strip()
                password = st.text_input("Password", type="password")
                submit_login = st.form_submit_button("Sign In", use_container_width=True, type="primary")

            if submit_login:
                if not email or not password:
                    st.error("Please provide both email and password.")
                else:
                    try:
                        tokens = client.login(email, password)
                        st.session_state["access_token"] = tokens["access_token"]
                        st.session_state["refresh_token"] = tokens["refresh_token"]

                        user_client = get_client()
                        me = user_client.get_me()
                        st.session_state["current_user"] = me
                        st.session_state["user_cache"][str(me["id"])] = me["username"]
                        st.success("Successfully logged in!")
                        st.rerun()
                    except APIError as e:
                        st.error(f"Login failed: {e.detail}")

        with tab_register:
            st.subheader("Create a New Account")
            with st.form("register_form", clear_on_submit=False):
                username = st.text_input("Username", placeholder="e.g. john_doe").strip()
                reg_email = st.text_input("Email address", placeholder="john@example.com").strip()
                reg_password = st.text_input("Password (min 8 chars)", type="password")
                reg_confirm = st.text_input("Confirm Password", type="password")
                submit_register = st.form_submit_button("Sign Up", use_container_width=True)

            if submit_register:
                if not username or not reg_email or not reg_password:
                    st.error("All fields are required.")
                elif len(username) < 3:
                    st.error("Username must be at least 3 characters.")
                elif len(reg_password) < 8:
                    st.error("Password must be at least 8 characters.")
                elif reg_password != reg_confirm:
                    st.error("Passwords do not match.")
                else:
                    try:
                        client.register(username, reg_email, reg_password)
                        st.success("Account created successfully! Please log in above.")
                    except APIError as e:
                        st.error(f"Registration failed: {e.detail}")


# ----------------- Logged In Main Application -----------------
def render_main_app():
    client = get_client()
    user = st.session_state.get("current_user", {})
    my_id = str(user.get("id"))
    st.session_state["user_cache"][my_id] = user.get("username", "You")

    # ===================== SIDEBAR =====================
    with st.sidebar:
        # Profile Section
        st.subheader(f"🧑‍💻 {user.get('username', 'My Account')}")
        st.caption(f"{user.get('email', '')}")

        col_ref, col_logout = st.columns([1, 1])
        if col_ref.button("🔄 Refresh", use_container_width=True):
            st.rerun()
        if col_logout.button("🚪 Logout", use_container_width=True):
            if st.session_state.get("refresh_token"):
                client.logout(st.session_state["refresh_token"])
            st.session_state.clear()
            st.rerun()

        st.divider()

        with st.expander("🌐 Timezone Settings", expanded=False):
            current_choice = st.session_state.get("display_timezone", "Asia/Kolkata (IST +5:30)")
            tz_names = list(TIMEZONES.keys())
            idx = tz_names.index(current_choice) if current_choice in tz_names else 0
            selected_tz = st.selectbox("Display Timezone", tz_names, index=idx, key="tz_select")
            if selected_tz != current_choice:
                st.session_state["display_timezone"] = selected_tz
                st.rerun()

        # Start New Chat Modal / Expander
        with st.expander("➕ New Conversation"):
            tab_direct, tab_group = st.tabs(["Direct Chat", "Group Chat"])

            with tab_direct:
                search_q = st.text_input("Find User", placeholder="Type username...", key="direct_search")
                if len(search_q.strip()) >= 2:
                    try:
                        results = client.search_users(search_q.strip())
                        if not results:
                            st.caption("No users found.")
                        for u in results:
                            col_u, col_btn = st.columns([3, 1])
                            col_u.write(f"**{u['username']}**")
                            # Cache username
                            st.session_state["user_cache"][str(u["id"])] = u["username"]
                            if col_btn.button("Chat", key=f"start_{u['id']}"):
                                try:
                                    conv = client.create_direct_conversation(str(u["id"]))
                                    st.session_state["active_conv_id"] = str(conv["id"])
                                    st.session_state["active_conv_name"] = u["username"]
                                    st.session_state["active_other_user_id"] = str(u["id"])
                                    st.session_state["active_other_username"] = u["username"]
                                    st.session_state["user_cache"][str(u["id"])] = u["username"]
                                    st.rerun()
                                except APIError as err:
                                    st.error(err.detail)
                    except APIError as err:
                        st.error(err.detail)

            with tab_group:
                group_name = st.text_input("Group Name", placeholder="Engineering Team", key="grp_name")
                member_search = st.text_input("Search Members", placeholder="Find user...", key="grp_search")
                selected_ids = st.session_state.setdefault("new_group_selected_ids", [])

                if len(member_search.strip()) >= 2:
                    try:
                        m_results = client.search_users(member_search.strip())
                        for cand in m_results:
                            cand_id = str(cand["id"])
                            st.session_state["user_cache"][cand_id] = cand["username"]
                            is_checked = cand_id in selected_ids
                            if st.checkbox(cand["username"], value=is_checked, key=f"cand_{cand_id}"):
                                if cand_id not in selected_ids:
                                    selected_ids.append(cand_id)
                            else:
                                if cand_id in selected_ids:
                                    selected_ids.remove(cand_id)
                    except APIError as err:
                        st.error(err.detail)

                st.caption(f"Selected members: {len(selected_ids)}")
                if st.button("Create Group", type="primary", use_container_width=True):
                    if not group_name.strip():
                        st.warning("Please provide a group name.")
                    elif not selected_ids:
                        st.warning("Please select at least one member.")
                    else:
                        try:
                            created_grp = client.create_group_conversation(group_name.strip(), selected_ids)
                            st.session_state["active_conv_id"] = str(created_grp["id"])
                            st.session_state["active_conv_name"] = group_name.strip()
                            st.session_state["active_other_user_id"] = None
                            st.session_state["new_group_selected_ids"] = []
                            st.success("Group created!")
                            st.rerun()
                        except APIError as err:
                            st.error(err.detail)

        st.divider()

        # Inbox Conversations List
        st.markdown("### 💬 Conversations")
        try:
            inbox_items = client.get_inbox()
            if not inbox_items:
                st.caption("No conversations yet. Start one above!")

            for item in inbox_items:
                conv = item.get("conversation", {})
                conv_id = str(conv.get("id"))
                conv_type = conv.get("conversation_type", "direct")
                unread = int(item.get("unread_count", 0))

                # Identify other user in direct conversation
                other_uid = str(item.get("other_user_id") or "")
                other_uname = item.get("other_username")

                if not other_uid and conv_type == "direct":
                    # Fallback: find member who is not me
                    for m in conv.get("members", []):
                        mid = str(m.get("user_id"))
                        if mid != my_id:
                            other_uid = mid
                            other_uname = m.get("username")
                            break

                # Resolve other username if missing
                if conv_type == "direct" and not other_uname and other_uid:
                    other_uname = resolve_username(client, other_uid, "Direct Chat")
                elif other_uname and other_uid:
                    st.session_state["user_cache"][other_uid] = other_uname

                # Display Name
                if conv_type == "group":
                    display_name = f"👥 {conv.get('name') or 'Group Chat'}"
                else:
                    display_name = f"👤 {other_uname or 'Direct Chat'}"

                # Unread Badge
                badge = f" 🔴 {unread}" if unread > 0 else ""
                snippet = item.get("last_message_content") or "No messages yet"
                if len(snippet) > 28:
                    snippet = snippet[:26] + "..."

                btn_label = f"{display_name}{badge}\n↳ {snippet}"
                is_selected = (conv_id == st.session_state.get("active_conv_id"))

                if st.button(
                    btn_label,
                    key=f"inbox_{conv_id}",
                    use_container_width=True,
                    type="primary" if is_selected else "secondary",
                ):
                    st.session_state["active_conv_id"] = conv_id
                    st.session_state["active_conv_name"] = display_name
                    st.session_state["active_other_user_id"] = other_uid if conv_type == "direct" else None
                    st.session_state["active_other_username"] = other_uname if conv_type == "direct" else None
                    st.rerun()

        except APIError as e:
            st.error(f"Failed to load conversations: {e.detail}")

    # ===================== MAIN CHAT WORKSPACE =====================
    active_id = st.session_state.get("active_conv_id")
    if not active_id:
        st.title(f"👋 Welcome, {user.get('username', 'there')}!")
        st.info("👈 Select a conversation from the sidebar or click **➕ New Conversation** to begin.")
        st.markdown(
            """
            ### Real-Time Features Enabled
            - **Live User Presence**: Shows online status (`🟢 Online`) or last seen time.
            - **Named Participants**: Direct chats show the person's real username.
            - **Read & Delivery Receipts**: Track message status (`✓ Sent`, `✓✓ Delivered`, `👁️ Read`).
            - **Typing Indicators**: Displays when the other user is typing.
            """
        )
        return

    # Load Active Conversation Details
    try:
        conv_details = client.get_conversation_details(active_id)
    except APIError as e:
        st.error(f"Failed to load conversation: {e.detail}")
        st.session_state["active_conv_id"] = None
        return

    conv_type = conv_details.get("conversation_type", "direct")
    members = conv_details.get("members", [])

    # Cache member usernames
    other_user_id = st.session_state.get("active_other_user_id")
    for m in members:
        mid = str(m.get("user_id"))
        m_uname = m.get("username")
        if m_uname:
            st.session_state["user_cache"][mid] = m_uname
        if conv_type == "direct" and mid != my_id:
            other_user_id = mid
            if m_uname:
                st.session_state["active_other_username"] = m_uname

    # Resolve header title
    if conv_type == "group":
        header_title = f"👥 {conv_details.get('name') or 'Group Chat'}"
        sub_caption = f"{len(members)} participant(s)"
    else:
        other_name = resolve_username(client, other_user_id, "Direct Chat") if other_user_id else "Direct Chat"
        header_title = f"👤 {other_name}"

        # Fetch Presence
        presence = client.get_presence(other_user_id) if other_user_id else {}
        if presence.get("is_online"):
            sub_caption = "🟢 Online"
        else:
            sub_caption = f"⚪ {format_last_seen(presence.get('last_seen'))}"

    # Header Row
    head_col1, head_col2 = st.columns([4, 1])
    with head_col1:
        st.subheader(header_title)
        st.caption(sub_caption)
    with head_col2:
        if st.button("Close Chat", use_container_width=True):
            st.session_state["active_conv_id"] = None
            st.session_state["active_conv_name"] = None
            st.session_state["active_other_user_id"] = None
            st.session_state["active_other_username"] = None
            st.rerun()

    # Group Settings (if group)
    if conv_type == "group":
        with st.expander("⚙️ Group Settings"):
            set_tab1, set_tab2 = st.columns([1, 1])
            with set_tab1:
                new_title = st.text_input("Rename Group", value=conv_details.get("name") or "")
                if st.button("Save Name"):
                    try:
                        client.rename_group(active_id, new_title.strip())
                        st.success("Group renamed!")
                        st.rerun()
                    except APIError as err:
                        st.error(err.detail)
            with set_tab2:
                add_user_q = st.text_input("Add Member (User ID)", placeholder="Enter User UUID")
                if st.button("Add Member"):
                    try:
                        client.add_group_member(active_id, add_user_q.strip())
                        st.success("Member added!")
                        st.rerun()
                    except APIError as err:
                        st.error(err.detail)

            st.divider()
            if st.button("🚪 Leave Group", type="primary"):
                try:
                    client.leave_group(active_id)
                    st.session_state["active_conv_id"] = None
                    st.session_state["active_conv_name"] = None
                    st.rerun()
                except APIError as err:
                    st.error(err.detail)

    st.divider()

    # Real-time Message Stream Fragment (Smooth 3-second auto-poll)
    @st.fragment(run_every="3s")
    def render_messages_stream(c_id: str, me_id: str, other_uid: str | None, conv_kind: str):
        c_client = get_client()

        # 1. Maintain my active presence in Redis
        c_client.heartbeat()

        # 2. Check other user presence (live auto-updated every 3s)
        other_is_online = False
        last_seen_val = None
        if conv_kind == "direct" and other_uid:
            p_data = c_client.get_presence(other_uid)
            other_is_online = bool(p_data.get("is_online"))
            last_seen_val = p_data.get("last_seen")

        # 3. Fetch typing indicators
        typing_users = c_client.get_typing(c_id)
        if typing_users:
            names = ", ".join(typing_users)
            st.info(f"✍️ **{names}** is typing...")

        # 4. Fetch messages
        try:
            msg_res = c_client.get_messages(c_id, limit=50)
            messages = list(reversed(msg_res.get("messages", [])))
        except APIError:
            st.caption("Connecting to message feed...")
            return

        # 5. Smart presence fallback: If other user sent a message in the last 60s, they are active
        incoming_msgs = [m for m in messages if str(m.get("sender_id")) != me_id]
        if not other_is_online and incoming_msgs:
            latest_inc_time = incoming_msgs[-1].get("created_at")
            if latest_inc_time:
                try:
                    dt = datetime.fromisoformat(latest_inc_time.replace("Z", "+00:00"))
                    if (datetime.now(dt.tzinfo) - dt).total_seconds() < 60:
                        other_is_online = True
                except Exception:
                    pass

        # Live Status Banner inside the stream (auto-updates every 3s)
        if conv_kind == "direct":
            if other_is_online:
                st.caption("🟢 **Status:** Active now")
            else:
                st.caption(f"⚪ **Status:** {format_last_seen(last_seen_val)}")

        if not messages:
            st.info("No messages yet. Say hello!")

        # 6. Render each message
        for msg in messages:
            sender_id = str(msg.get("sender_id"))
            is_me = (sender_id == me_id)
            deleted = msg.get("deleted_at") is not None
            text = "*This message was deleted*" if deleted else (msg.get("content") or "")
            time_label = format_timestamp(msg.get("created_at"))
            msg_created = msg.get("created_at", "")

            # Check if there is an incoming message replied AFTER this message
            has_subsequent_incoming = False
            if is_me and incoming_msgs and msg_created:
                for inc in incoming_msgs:
                    if inc.get("created_at", "") >= msg_created:
                        has_subsequent_incoming = True
                        break

            # Resolve sender name (bulletproof fallback chain)
            if is_me:
                sender_display = "You"
                avatar = "🧑‍💻"
            else:
                other_fallback = (
                    st.session_state.get("active_other_username")
                    or (st.session_state.get("active_conv_name") or "").replace("👤 ", "").replace("👥 ", "")
                )
                sender_display = (
                    msg.get("sender_username")
                    or st.session_state["user_cache"].get(sender_id)
                    or other_fallback
                    or resolve_username(c_client, sender_id, "User")
                )
                avatar = "👤"

            # Receipts for my own messages
            receipt_badge = ""
            if is_me and not deleted:
                if msg.get("is_read") or has_subsequent_incoming:
                    receipt_badge = " · 👁️ Read"
                elif msg.get("is_delivered") or other_is_online:
                    receipt_badge = " · ✓✓ Delivered"
                else:
                    receipt_badge = " · ✓ Sent"

            with st.chat_message("user" if is_me else "assistant", avatar=avatar):
                st.markdown(f"**{sender_display}**")
                st.write(text)
                st.caption(f"{time_label}{receipt_badge}")

        # 7. Mark conversation as read
        if incoming_msgs:
            latest_incoming_id = str(incoming_msgs[-1]["id"])
            last_cached = st.session_state.get(f"last_read_{c_id}")
            if last_cached != latest_incoming_id:
                c_client.mark_conversation_read(c_id, latest_incoming_id)
                st.session_state[f"last_read_{c_id}"] = latest_incoming_id

    # Call the message stream
    render_messages_stream(active_id, my_id, other_user_id, conv_type)

    # Bottom Pinned Chat Input
    user_input = st.chat_input("Write a message...")
    if user_input:
        if user_input.strip():
            try:
                # Notify typing stop & send message
                client.set_typing(active_id, is_typing=False)
                client.send_message(active_id, user_input.strip())
                st.rerun()
            except APIError as e:
                st.error(f"Failed to send message: {e.detail}")


# ----------------- App Entrypoint -----------------
def main():
    if not st.session_state.get("access_token") or not st.session_state.get("current_user"):
        render_auth()
    else:
        render_main_app()


if __name__ == "__main__":
    main()
