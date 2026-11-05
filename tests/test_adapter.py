import asyncio
import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BOT_ID = "bot123"


class FakeResp:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, history):
        self.history = history  # newest first, like im.history
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", url, params))
        if url.endswith("/im.history"):
            return FakeResp({"messages": list(self.history), "success": True})
        return FakeResp({}, 404)

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json))
        return FakeResp({"success": True, "message": {"_id": "sent1"}})


def msg(mid, uid, text="hi", **kw):
    return {"_id": mid, "u": {"_id": uid, "username": uid}, "msg": text, **kw}


def make(adapter_mod, monkeypatch, history, **env):
    for k in ("ROCKETCHAT_ALLOWED_USERS", "ROCKETCHAT_ALLOW_ALL_USERS"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    a = adapter_mod.RocketChatAdapter(adapter_mod.PlatformConfig(extra={"url": "http://rc"}), "rocketchat")
    a._session = FakeSession(history)
    a._user_id = BOT_ID
    return a


def test_uses_im_history_not_chat_getmessages(adapter_mod, monkeypatch):
    a = make(adapter_mod, monkeypatch, [], ROCKETCHAT_ALLOW_ALL_USERS="true")
    asyncio.run(a._process_room("r1"))
    urls = [c[1] for c in a._session.calls]
    assert urls == ["http://rc/api/v1/im.history"]


def test_startup_does_not_replay_answered_history(adapter_mod, monkeypatch):
    history = [msg("m3", "alice", "new question"), msg("m2", BOT_ID, "answer"), msg("m1", "alice", "old")]
    a = make(adapter_mod, monkeypatch, history, ROCKETCHAT_ALLOW_ALL_USERS="true")
    asyncio.run(a._process_room("r1"))
    assert [e.text for e in a.handled] == ["new question"]
    # Second poll with one more message only dispatches the new one.
    a._session.history.insert(0, msg("m4", "alice", "follow up"))
    asyncio.run(a._process_room("r1"))
    assert [e.text for e in a.handled] == ["new question", "follow up"]


def test_system_messages_skipped(adapter_mod, monkeypatch):
    a = make(adapter_mod, monkeypatch, [msg("m1", "alice", "alice", t="uj")], ROCKETCHAT_ALLOW_ALL_USERS="true")
    asyncio.run(a._process_room("r1"))
    assert a.handled == []


def test_deny_by_default(adapter_mod, monkeypatch):
    a = make(adapter_mod, monkeypatch, [msg("m1", "mallory")])
    asyncio.run(a._process_room("r1"))
    assert a.handled == []
    assert a._is_authorized("anyone") is False


def test_allowlist(adapter_mod, monkeypatch):
    a = make(adapter_mod, monkeypatch, [msg("m2", "bob"), msg("m1", "mallory")],
             ROCKETCHAT_ALLOWED_USERS="alice, bob")
    asyncio.run(a._process_room("r1"))
    assert [e.source["user_name"] for e in a.handled] == ["bob"]


def test_send_room_id_vs_channel_name(adapter_mod, monkeypatch):
    a = make(adapter_mod, monkeypatch, [])
    r = asyncio.run(a.send("ROOMID", "hello", metadata={"thread_id": "t1"}))
    assert r.success and r.message_id == "sent1"
    assert a._session.calls[-1][1].endswith("/chat.sendMessage")
    assert a._session.calls[-1][2] == {"message": {"text": "hello", "roomId": "ROOMID", "tmid": "t1"}}
    asyncio.run(a.send("#hermes-cron", "cron output"))
    assert a._session.calls[-1][1].endswith("/chat.postMessage")
    assert a._session.calls[-1][2] == {"channel": "#hermes-cron", "text": "cron output"}


def test_plugin_copies_are_identical():
    """The three shipped copies of the plugin must not drift apart."""
    def digest(p):
        return hashlib.sha256(p.read_bytes()).hexdigest()
    for name in ("adapter.py", "__init__.py", "plugin.yaml"):
        copies = [ROOT / name, ROOT / "plugin" / name,
                  ROOT / "hermes-agent/plugins/platforms/rocketchat" / name]
        assert len({digest(c) for c in copies}) == 1, name
