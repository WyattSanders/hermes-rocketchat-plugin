"""Rocket.Chat platform adapter for Hermes Agent.

A plugin-based gateway adapter that connects to a self-hosted Rocket.Chat
server via REST API polling. No external dependencies beyond `requests`.

Configuration via environment variables (recommended)::

    ROCKETCHAT_URL=http://localhost:3000
    ROCKETCHAT_USER=hermes-bot
    ROCKETCHAT_PASSWORD=secret
    ROCKETCHAT_POLL_INTERVAL=3
    ROCKETCHAT_ALLOWED_USERS=alice,bob
    ROCKETCHAT_ALLOW_ALL_USERS=false
    ROCKETCHAT_HOME_CHANNEL=hermes-cron

Or via config.yaml::

    gateway:
      platforms:
        rocketchat:
          enabled: true
          extra:
            url: "http://localhost:3000"
            username: "hermes-bot"
            password: "secret"
            poll_interval: 3

Rocket.Chat server setup: create a bot user in Rocket.Chat
(Admin > Users > New User, role: bot).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import requests

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 3.0
MAX_MESSAGE_LENGTH = 16_000
HISTORY_COUNT = 20


def _post_message(
    session: requests.Session,
    base_url: str,
    headers: Dict[str, str],
    chat_id: str,
    text: str,
    thread_id: Optional[str] = None,
    timeout: int = 15,
) -> Dict[str, Any]:
    """Send ``text`` to a room and return the decoded JSON response.

    ``chat_id`` may be a room ID (``chat.sendMessage``) or a ``#channel`` /
    ``@username`` name (``chat.postMessage``), so a human-readable
    ``ROCKETCHAT_HOME_CHANNEL`` works for cron delivery.
    """
    base = base_url.rstrip("/")
    if chat_id.startswith(("#", "@")):
        body: Dict[str, Any] = {"channel": chat_id, "text": text}
        if thread_id:
            body["tmid"] = thread_id
        resp = session.post(f"{base}/api/v1/chat.postMessage", json=body,
                            headers=headers, timeout=timeout)
    else:
        payload: Dict[str, Any] = {"text": text, "roomId": chat_id}
        if thread_id:
            payload["tmid"] = thread_id
        resp = session.post(f"{base}/api/v1/chat.sendMessage", json={"message": payload},
                            headers=headers, timeout=timeout)
    return resp.json()


# ---------------------------------------------------------------------------
# Requirement checks and validation
# ---------------------------------------------------------------------------

def check_requirements() -> bool:
    """Rocket.Chat adapter requires the `requests` library."""
    try:
        import requests  # noqa: F401
        return True
    except ImportError:
        return False


def validate_config(cfg: PlatformConfig) -> bool:
    """Return True if Rocket.Chat has enough config to attempt a connection."""
    extra = getattr(cfg, "extra", None) or {}
    url = os.getenv("ROCKETCHAT_URL") or extra.get("url", "")
    username = os.getenv("ROCKETCHAT_USER") or extra.get("username", "")
    password = os.getenv("ROCKETCHAT_PASSWORD") or extra.get("password", "")
    return bool(url and username and password)


def is_connected(cfg: PlatformConfig) -> bool:
    """Ping Rocket.Chat to verify authentication is working."""
    extra = getattr(cfg, "extra", None) or {}
    url = os.getenv("ROCKETCHAT_URL") or extra.get("url", "")
    username = os.getenv("ROCKETCHAT_USER") or extra.get("username", "")
    password = os.getenv("ROCKETCHAT_PASSWORD") or extra.get("password", "")

    if not url or not username or not password:
        return False
    try:
        session = requests.Session()
        resp = session.post(
            f"{url.rstrip('/')}/api/v1/login",
            json={"user": username, "password": password},
            timeout=10,
        )
        return resp.json().get("status") == "success"
    except Exception:
        return False


def _env_enablement() -> Optional[Dict[str, Any]]:
    """Seed PlatformConfig.extra from environment variables."""
    url = os.getenv("ROCKETCHAT_URL")
    if not url:
        return None

    poll_interval_str = os.getenv("ROCKETCHAT_POLL_INTERVAL", "3")
    allowed_str = os.getenv("ROCKETCHAT_ALLOWED_USERS", "")
    allow_all_str = os.getenv("ROCKETCHAT_ALLOW_ALL_USERS", "false")
    home_channel = os.getenv("ROCKETCHAT_HOME_CHANNEL", "")

    try:
        poll_interval = float(poll_interval_str)
    except ValueError:
        poll_interval = DEFAULT_POLL_INTERVAL

    allowed_users = [u.strip() for u in allowed_str.split(",") if u.strip()]

    return {
        "url": url,
        "username": os.getenv("ROCKETCHAT_USER", ""),
        "password": os.getenv("ROCKETCHAT_PASSWORD", ""),
        "poll_interval": poll_interval,
        "allowed_users": allowed_users,
        "allow_all_users": allow_all_str.lower() in ("true", "1", "yes"),
        "home_channel": home_channel,
    }


# ---------------------------------------------------------------------------
# Standalone sender (for cron jobs outside the gateway process)
# ---------------------------------------------------------------------------

async def _standalone_send(
    pconfig: PlatformConfig,
    chat_id: str,
    message: str,
    *,
    thread_id: Optional[str] = None,
    media_files: Optional[List[str]] = None,
    force_document: bool = False,
) -> dict:
    """Send a message via Rocket.Chat REST API outside the gateway."""
    extra = getattr(pconfig, "extra", None) or {}
    url = os.getenv("ROCKETCHAT_URL") or extra.get("url", "")
    username = os.getenv("ROCKETCHAT_USER") or extra.get("username", "")
    password = os.getenv("ROCKETCHAT_PASSWORD") or extra.get("password", "")

    if not all([url, username, password]):
        return {"error": "Rocket.Chat not configured"}

    try:
        session = requests.Session()
        login_resp = session.post(
            f"{url.rstrip('/')}/api/v1/login",
            json={"user": username, "password": password},
            timeout=15,
        )
        login_data = login_resp.json()
        if login_data.get("status") != "success":
            return {"error": f"Auth failed: {login_data}"}

        auth_token = login_data["data"]["authToken"]
        user_id = login_data["data"]["userId"]
        headers = {
            "X-Auth-Token": auth_token,
            "X-User-Id": user_id,
            "Content-Type": "application/json",
        }

        send_data = _post_message(session, url, headers, chat_id, message, thread_id)

        if send_data.get("success"):
            msg_id = send_data.get("message", {}).get("_id")
            return {"success": True, "message_id": msg_id}
        return {"error": f"Send failed: {send_data}"}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Interactive setup
# ---------------------------------------------------------------------------

def interactive_setup() -> None:
    """Minimal stdin wizard for ``hermes setup rocketchat``."""
    print()
    print("Rocket.Chat Platform Setup")
    print("-" * 34)
    print("Create a bot user in Rocket.Chat first (Admin > Users > New User, role: bot).")
    print()

    try:
        from hermes_cli.config import get_env_var, set_env_var
    except ImportError:
        print("hermes_cli.config not available; set ROCKETCHAT_* vars in ~/.hermes/.env")
        return

    def _prompt(var: str, prompt_text: str, *, secret: bool = False) -> None:
        try:
            if secret:
                import getpass
                value = getpass.getpass(f"{prompt_text}: ")
            else:
                value = input(f"{prompt_text}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if value:
            set_env_var(var, value)

    _prompt("ROCKETCHAT_URL", "Rocket.Chat URL (e.g. http://localhost:3000)")
    _prompt("ROCKETCHAT_USER", "Bot username")
    _prompt("ROCKETCHAT_PASSWORD", "Bot password", secret=True)
    _prompt("ROCKETCHAT_POLL_INTERVAL", "Poll interval in seconds (default: 3)")
    _prompt("ROCKETCHAT_HOME_CHANNEL", "Home channel for cron delivery (optional)")
    print("Done. Make sure your Rocket.Chat server is running.")


# ---------------------------------------------------------------------------
# Rocket.Chat Adapter
# ---------------------------------------------------------------------------

class RocketChatAdapter(BasePlatformAdapter):
    """Async adapter that polls Rocket.Chat for inbound messages.

    Inherits from BasePlatformAdapter to use build_source(), handle_message(),
    and the full async send interface.
    """

    def __init__(self, config: PlatformConfig, platform: Platform) -> None:
        super().__init__(config, platform)
        extra = config.extra or {}

        self.url = os.getenv("ROCKETCHAT_URL") or extra.get("url", "")
        self.username = os.getenv("ROCKETCHAT_USER") or extra.get("username", "")
        self.password = os.getenv("ROCKETCHAT_PASSWORD") or extra.get("password", "")

        poll_str = os.getenv("ROCKETCHAT_POLL_INTERVAL") or extra.get("poll_interval", "3")
        try:
            self.poll_interval = float(poll_str)
        except ValueError:
            self.poll_interval = DEFAULT_POLL_INTERVAL

        allowed_str = os.getenv("ROCKETCHAT_ALLOWED_USERS") or ",".join(extra.get("allowed_users", []))
        self.allowed_users: Set[str] = {u.strip() for u in allowed_str.split(",") if u.strip()}
        self.allow_all = os.getenv("ROCKETCHAT_ALLOW_ALL_USERS", "").lower() in (
            "true", "1", "yes"
        ) or extra.get("allow_all_users", False)
        self.home_channel = os.getenv("ROCKETCHAT_HOME_CHANNEL") or extra.get("home_channel", "")

        self._session = requests.Session()
        self._auth_token: Optional[str] = None
        self._user_id: Optional[str] = None
        self._bot_username: Optional[str] = None
        # room_id -> IDs of messages in that room's current history window
        self._seen_by_room: Dict[str, Set[str]] = {}
        self._stopping = False
        self._poll_task: Optional[asyncio.Task] = None

        if not self.allow_all and not self.allowed_users:
            logger.warning(
                "Rocket.Chat: neither ROCKETCHAT_ALLOWED_USERS nor "
                "ROCKETCHAT_ALLOW_ALL_USERS is set — all inbound messages will be ignored."
            )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _authenticate(self) -> None:
        """Authenticate with Rocket.Chat and store session headers."""
        resp = self._session.post(
            f"{self.url.rstrip('/')}/api/v1/login",
            json={"user": self.username, "password": self.password},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("status") == "success":
            raise RuntimeError(f"Rocket.Chat auth failed: {data}")

        self._auth_token = data["data"]["authToken"]
        self._user_id = data["data"]["userId"]

    def _headers(self) -> Dict[str, str]:
        return {
            "X-Auth-Token": self._auth_token or "",
            "X-User-Id": self._user_id or "",
            "Content-Type": "application/json",
        }

    def _api_get(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """GET an API endpoint, logging in again once if the token expired."""
        url = f"{self.url.rstrip('/')}/api/v1/{endpoint}"
        resp = self._session.get(url, params=params, headers=self._headers(), timeout=15)
        if resp.status_code == 401:
            logger.info("Rocket.Chat token rejected; re-authenticating")
            self._authenticate()
            resp = self._session.get(url, params=params, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # BasePlatformAdapter required methods
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Authenticate and start the polling loop."""
        try:
            await asyncio.to_thread(self._authenticate)
            me = await asyncio.to_thread(self._api_get, "me", {})
            self._bot_username = me.get("username")
            logger.info(
                "Rocket.Chat connected — bot user: %s (%s)",
                self._bot_username,
                me.get("_id"),
            )
            self._stopping = False
            self._poll_task = asyncio.create_task(self._poll_loop())
            return True
        except Exception as exc:
            logger.error("Rocket.Chat connect failed: %s", exc)
            return False

    async def disconnect(self) -> None:
        """Stop the polling loop."""
        self._stopping = True
        if self._poll_task is not None:
            self._poll_task.cancel()
            self._poll_task = None
        logger.info("Rocket.Chat adapter disconnected")

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a text message to a Rocket.Chat room."""
        try:
            thread_id = (metadata or {}).get("thread_id")
            data = await asyncio.to_thread(
                _post_message, self._session, self.url, self._headers(),
                chat_id, content, thread_id,
            )

            if data.get("success"):
                msg_id = data.get("message", {}).get("_id")
                return SendResult(success=True, message_id=msg_id)
            return SendResult(success=False, error=f"Send failed: {data}")
        except Exception as exc:
            logger.error("Rocket.Chat send error: %s", exc)
            return SendResult(success=False, error=str(exc))

    async def send_typing(self, chat_id: str, metadata=None) -> None:
        """Rocket.Chat REST API has no typing indicator — no-op."""
        pass

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Return info about a Rocket.Chat room."""
        try:
            data = await asyncio.to_thread(self._api_get, "rooms.info", {"roomId": chat_id})
            if data.get("success"):
                room = data.get("room", {})
                return {
                    "name": room.get("name", chat_id),
                    "type": room.get("t", "c"),  # d=dm, c=channel
                    "chat_id": chat_id,
                }
        except Exception:
            pass
        return {"name": chat_id, "type": "channel", "chat_id": chat_id}

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Continuously poll Rocket.Chat for new messages."""
        while not self._stopping:
            try:
                await asyncio.sleep(self.poll_interval)
                await self._poll_dms()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Poll loop error: %s", exc)
                await asyncio.sleep(5)

    async def _poll_dms(self) -> None:
        """Fetch DM subscriptions and process new messages."""
        try:
            data = await asyncio.to_thread(self._api_get, "subscriptions.get", {})

            for sub in data.get("update", []):
                if sub.get("t") != "d":
                    continue
                room_id = sub.get("rid")
                if room_id:
                    await self._process_room(room_id)
        except Exception as exc:
            logger.error("Error polling DMs: %s", exc)

    async def _process_room(self, room_id: str) -> None:
        """Fetch recent DM history from a room, dispatch new messages to the gateway."""
        try:
            # im.history returns newest first. (chat.getMessages is a POST
            # lookup by message ID, not a room-history endpoint.)
            data = await asyncio.to_thread(
                self._api_get, "im.history", {"roomId": room_id, "count": HISTORY_COUNT}
            )
            messages = data.get("messages", [])

            seen = self._seen_by_room.get(room_id)
            if seen is None:
                # First time we see this room since startup: don't replay
                # history the bot already answered. Only messages after the
                # bot's most recent message in the room are treated as new.
                seen = set()
                for idx, msg in enumerate(messages):
                    if msg.get("u", {}).get("_id") == self._user_id:
                        seen.update(m.get("_id", "") for m in messages[idx:])
                        break
            # Bounded memory: only IDs still inside the history window matter.
            self._seen_by_room[room_id] = {m.get("_id", "") for m in messages}

            for msg in reversed(messages):  # oldest → newest
                msg_id = msg.get("_id", "")
                if msg_id in seen:
                    continue
                seen.add(msg_id)

                # Skip own messages
                if msg.get("u", {}).get("_id") == self._user_id:
                    continue

                # Skip system messages (user joined, room renamed, ...)
                if msg.get("t"):
                    continue

                msg_text = (msg.get("msg") or "").strip()
                if not msg_text:
                    continue

                sender_username = msg.get("u", {}).get("username", "unknown")

                # Authorization check
                if not self._is_authorized(sender_username):
                    logger.debug("Ignoring message from unauthorized user: %s", sender_username)
                    continue

                thread_id = msg.get("tmid")
                source = self.build_source(
                    chat_id=room_id,
                    chat_name=room_id,
                    chat_type="dm",
                    user_id=msg.get("u", {}).get("_id"),
                    user_name=sender_username,
                    thread_id=thread_id,
                    message_id=msg_id,
                )

                event = MessageEvent(
                    text=msg_text,
                    source=source,
                    message_id=msg_id,
                    timestamp=self._parse_timestamp(msg.get("ts")),
                )

                await self.handle_message(event)

        except Exception as exc:
            logger.error("Error processing room %s: %s", room_id, exc)

    def _parse_timestamp(self, ts: Any) -> datetime:
        """Parse a Rocket.Chat ISO timestamp."""
        if ts and isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                pass
        return datetime.now(timezone.utc)

    def _is_authorized(self, username: str) -> bool:
        """Check if a username is allowed to interact with the bot."""
        if self.allow_all:
            return True
        # Deny by default: this bot fronts an agent with tool access, so an
        # empty allowlist must not mean "anyone on the server".
        return username in self.allowed_users


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------

def register(ctx: Any) -> None:
    """Plugin entry point — called by the Hermes plugin system at startup."""
    ctx.register_platform(
        name="rocketchat",
        label="Rocket.Chat",
        adapter_factory=lambda cfg: RocketChatAdapter(cfg, Platform("rocketchat")),
        check_fn=check_requirements,
        validate_config=validate_config,
        is_connected=is_connected,
        required_env=["ROCKETCHAT_URL", "ROCKETCHAT_USER", "ROCKETCHAT_PASSWORD"],
        install_hint="pip install requests   # Rocket.Chat adapter",
        setup_fn=interactive_setup,
        env_enablement_fn=_env_enablement,
        cron_deliver_env_var="ROCKETCHAT_HOME_CHANNEL",
        standalone_sender_fn=_standalone_send,
        allowed_users_env="ROCKETCHAT_ALLOWED_USERS",
        allow_all_env="ROCKETCHAT_ALLOW_ALL_USERS",
        max_message_length=MAX_MESSAGE_LENGTH,
        emoji="🚀",
        pii_safe=True,
        allow_update_command=True,
        platform_hint=(
            "You are chatting via Rocket.Chat, a self-hosted messaging platform. "
            "Rocket.Chat supports standard markdown. Keep responses conversational. "
            "Threads are supported — reply in a thread by setting thread_id."
        ),
    )