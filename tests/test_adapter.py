"""Tests for RocketChatAdapter — authorization, restart replay and dedupe.

The adapter imports Hermes gateway modules that are not installed when the
plugin is developed standalone, so minimal stubs for ``gateway.config`` and
``gateway.platforms.base`` are injected into ``sys.modules`` before the adapter
is loaded (see ``tests/_gateway_stubs.py``). No test touches the network:
``requests.Session`` is replaced by an in-memory fake.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

from _gateway_stubs import (
    StubPlatform,
    StubPlatformConfig,
    install_gateway_stubs,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

ADAPTER_PATHS = [
    REPO_ROOT / "adapter.py",
    REPO_ROOT / "plugin" / "adapter.py",
    REPO_ROOT / "hermes-agent" / "plugins" / "platforms" / "rocketchat" / "adapter.py",
]


install_gateway_stubs()


def load_adapter(path: pathlib.Path, name: str):
    """Load one of the three (identical) adapter copies as a module."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ADAPTER = load_adapter(ADAPTER_PATHS[0], "rc_adapter_under_test")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENV_VARS = (
    "ROCKETCHAT_URL",
    "ROCKETCHAT_USER",
    "ROCKETCHAT_PASSWORD",
    "ROCKETCHAT_ALLOWED_USERS",
    "ROCKETCHAT_ALLOW_ALL_USERS",
    "ROCKETCHAT_POLL_INTERVAL",
    "ROCKETCHAT_HOME_CHANNEL",
)


class _FakeResponse:
    def __init__(self, payload) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self):
        return self.payload


class _FakeSession:
    """Stands in for ``requests.Session``; never leaves the process.

    ``messages`` is passed through as ``chat.getMessages`` returns it, i.e.
    newest first.
    """

    def __init__(self, messages=(), me=None, login=None) -> None:
        self.messages = list(messages)
        self.me = me or {"username": "hermes-bot", "_id": "bot-id"}
        self.login = login or {
            "status": "success",
            "data": {"authToken": "token", "userId": "bot-id"},
        }
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", url))
        if "chat.getMessages" in url:
            return _FakeResponse({"messages": self.messages})
        if url.endswith("/api/v1/me"):
            return _FakeResponse(self.me)
        return _FakeResponse({})

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url))
        if url.endswith("/api/v1/login"):
            return _FakeResponse(self.login)
        return _FakeResponse({"success": True})


def run(coro):
    """Run a coroutine, cancelling the adapter's background poll task after."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()


def make_adapter(
    monkeypatch,
    *,
    allowed_users=(),
    allow_all=False,
    messages=(),
    url="http://localhost:3000",
    poll_interval=0.0,
    me=None,
    login=None,
):
    """Build an adapter wired to a fake session, with a clean environment."""
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    cfg = StubPlatformConfig(
        extra={
            "url": url,
            "username": "hermes-bot",
            "password": "secret",
            "poll_interval": poll_interval,
            "allowed_users": list(allowed_users),
            "allow_all_users": allow_all,
        }
    )
    adapter = ADAPTER.RocketChatAdapter(cfg, StubPlatform("rocketchat"))
    adapter._session = _FakeSession(messages=messages, me=me, login=login)
    adapter._user_id = "bot-id"
    return adapter


def mark_connected(adapter, offset_minutes=45):
    """Pretend the adapter connected a while ago (isolates replay logic)."""
    adapter._connected_at = datetime.now(timezone.utc) - timedelta(minutes=offset_minutes)
    return adapter


def msg(message_id, username, ts, text="hello"):
    return {
        "_id": message_id,
        "msg": text,
        "ts": ts,
        "u": {"_id": f"id-{username}", "username": username},
    }


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Bug 1 — authorization fails closed
# ---------------------------------------------------------------------------

def test_no_allowlist_and_allow_all_false_denies_everyone(monkeypatch):
    adapter = make_adapter(monkeypatch)
    assert adapter.allowed_users == set()
    assert adapter.allow_all is False

    assert adapter._is_authorized("alice") is False
    assert adapter._is_authorized("hermes-bot") is False
    assert adapter._is_authorized("") is False


def test_allowlist_allows_only_listed_users(monkeypatch):
    adapter = make_adapter(monkeypatch, allowed_users=["alice", "bob"])

    assert adapter._is_authorized("alice") is True
    assert adapter._is_authorized("bob") is True
    assert adapter._is_authorized("mallory") is False
    assert adapter._is_authorized("Alice") is False


def test_allow_all_accepts_any_user(monkeypatch):
    adapter = make_adapter(monkeypatch, allow_all=True)

    assert adapter._is_authorized("alice") is True
    assert adapter._is_authorized("whoever") is True


def test_no_allowlist_ignores_incoming_messages(monkeypatch):
    adapter = make_adapter(monkeypatch, messages=[msg("m1", "mallory", iso(NOW))])
    mark_connected(adapter)

    run(adapter._process_room("room-1"))

    assert adapter.dispatched == []


def test_allowlisted_user_message_is_dispatched(monkeypatch):
    adapter = make_adapter(
        monkeypatch,
        allowed_users=["alice"], messages=[msg("m1", "alice", iso(NOW))]
    )
    mark_connected(adapter)

    run(adapter._process_room("room-1"))

    assert [e.message_id for e in adapter.dispatched] == ["m1"]


def test_connect_warns_once_when_nobody_is_allowed(monkeypatch, caplog):
    adapter = make_adapter(monkeypatch)

    with caplog.at_level(logging.WARNING):
        assert run(adapter.connect()) is True

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "all messages will be ignored" in warnings[0].getMessage()


def test_connect_does_not_warn_when_allowlist_is_configured(monkeypatch, caplog):
    adapter = make_adapter(monkeypatch, allowed_users=["alice"])

    with caplog.at_level(logging.WARNING):
        assert run(adapter.connect()) is True

    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


def test_connect_does_not_warn_when_allow_all(monkeypatch, caplog):
    adapter = make_adapter(monkeypatch, allow_all=True)

    with caplog.at_level(logging.WARNING):
        assert run(adapter.connect()) is True

    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


# ---------------------------------------------------------------------------
# Bug 2 — no replay of pre-connect history after a restart
# ---------------------------------------------------------------------------

def test_connect_records_utc_connect_time(monkeypatch):
    adapter = make_adapter(monkeypatch)

    before = datetime.now(timezone.utc)
    run(adapter.connect())
    after = datetime.now(timezone.utc)

    assert adapter._connected_at is not None
    assert adapter._connected_at.tzinfo is not None
    assert before <= adapter._connected_at <= after


def test_pre_connect_messages_are_skipped_but_marked_seen(monkeypatch):
    old = iso(NOW - timedelta(minutes=5))
    fresh = iso(NOW + timedelta(minutes=1))
    adapter = make_adapter(
        monkeypatch,
        allowed_users=["alice"],
        messages=[
            msg("old-1", "alice", old),
            msg("old-2", "alice", old),
            msg("new-1", "alice", fresh),
        ],
    )
    adapter._connected_at = NOW

    run(adapter._process_room("room-1"))

    assert [e.message_id for e in adapter.dispatched] == ["new-1"]
    # Pre-connect ids are marked seen so a later poll cannot replay them.
    assert {"old-1", "old-2", "new-1"} <= adapter._seen_message_ids


def test_restart_does_not_replay_history(monkeypatch):
    """After reconnect, the same room history must not be dispatched again."""
    # chat.getMessages returns newest first; the adapter replays oldest → newest.
    history = [
        msg("h3", "alice", iso(NOW - timedelta(minutes=10))),
        msg("h2", "alice", iso(NOW - timedelta(minutes=20))),
        msg("h1", "alice", iso(NOW - timedelta(minutes=30))),
    ]
    adapter = make_adapter(monkeypatch, allowed_users=["alice"], messages=history)
    mark_connected(adapter, offset_minutes=45)

    run(adapter._process_room("room-1"))
    assert [e.message_id for e in adapter.dispatched] == ["h1", "h2", "h3"]

    # Simulate a gateway restart: same adapter state, new connect time.
    adapter.dispatched.clear()
    adapter._connected_at = datetime.now(timezone.utc)
    run(adapter._process_room("room-1"))

    assert adapter.dispatched == []


def test_second_poll_does_not_redispatch_seen_messages(monkeypatch):
    adapter = make_adapter(
        monkeypatch,
        allowed_users=["alice"], messages=[msg("m1", "alice", iso(NOW))]
    )
    mark_connected(adapter)

    run(adapter._process_room("room-1"))
    adapter.dispatched.clear()
    run(adapter._process_room("room-1"))

    assert adapter.dispatched == []


def test_timestamp_without_timezone_is_compared_as_utc(monkeypatch):
    naive_old = (NOW - timedelta(minutes=5)).replace(tzinfo=None).isoformat()
    adapter = make_adapter(
        monkeypatch,
        allowed_users=["alice"], messages=[msg("old-naive", "alice", naive_old)]
    )
    adapter._connected_at = NOW

    run(adapter._process_room("room-1"))

    assert adapter.dispatched == []
    assert "old-naive" in adapter._seen_message_ids


def test_own_messages_are_ignored(monkeypatch):
    own = msg("own-1", "hermes-bot", iso(NOW + timedelta(minutes=1)))
    own["u"]["_id"] = "bot-id"
    adapter = make_adapter(monkeypatch, allowed_users=["alice"], messages=[own])
    adapter._connected_at = NOW

    run(adapter._process_room("room-1"))

    assert adapter.dispatched == []


# ---------------------------------------------------------------------------
# Bug 3 — the seen-id set is bounded
# ---------------------------------------------------------------------------

def test_seen_ids_are_capped_at_max(monkeypatch):
    adapter = make_adapter(monkeypatch)
    cap = ADAPTER.MAX_SEEN_MESSAGE_IDS
    assert cap == 5_000

    for i in range(cap + 25):
        adapter._mark_seen(f"m{i}")

    assert len(adapter._seen_message_ids) == cap
    assert len(adapter._seen_message_order) == cap
    assert f"m{cap + 24}" in adapter._seen_message_ids
    assert "m0" not in adapter._seen_message_ids
    assert "m24" not in adapter._seen_message_ids
    assert "m25" in adapter._seen_message_ids


def test_remark_seen_id_does_not_grow_state(monkeypatch):
    adapter = make_adapter(monkeypatch)

    adapter._mark_seen("dup")
    adapter._mark_seen("dup")
    adapter._mark_seen("")

    assert adapter._seen_message_ids == {"dup"}
    assert list(adapter._seen_message_order) == ["dup"]


def test_polling_many_messages_keeps_state_bounded(monkeypatch):
    cap = ADAPTER.MAX_SEEN_MESSAGE_IDS
    messages = [
        msg(f"m{i}", "alice", iso(NOW + timedelta(seconds=i))) for i in range(cap + 100)
    ]
    adapter = make_adapter(monkeypatch, allowed_users=["alice"], messages=messages)
    mark_connected(adapter)

    run(adapter._process_room("room-1"))

    assert len(adapter.dispatched) == cap + 100
    assert len(adapter._seen_message_ids) == cap
    assert len(adapter._seen_message_order) == cap


# ---------------------------------------------------------------------------
# The three copies must stay byte-identical and carry the same fixes
# ---------------------------------------------------------------------------

def test_adapter_copies_are_byte_identical():
    contents = [p.read_bytes() for p in ADAPTER_PATHS]

    assert all(p.exists() for p in ADAPTER_PATHS)
    assert len({c for c in contents}) == 1


@pytest.mark.parametrize("path", ADAPTER_PATHS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_every_copy_denies_without_allowlist(monkeypatch, path):
    module = load_adapter(path, f"rc_copy_{path.parts[-3]}_{path.parts[-2]}")
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    adapter = module.RocketChatAdapter(
        StubPlatformConfig(
            extra={"url": "http://localhost:3000", "username": "u", "password": "p"}
        ),
        StubPlatform("rocketchat"),
    )

    assert adapter._is_authorized("alice") is False
    assert module.MAX_SEEN_MESSAGE_IDS == 5_000