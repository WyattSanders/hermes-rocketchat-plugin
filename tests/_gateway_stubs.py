"""Minimal stubs for the Hermes gateway modules the adapter imports.

The plugin is developed standalone, where ``gateway.config`` and
``gateway.platforms.base`` do not exist. Both ``tests/conftest.py`` (so the
plugin package itself stays importable during pytest's package setup) and the
test module use these stubs instead of installing Hermes.
"""

from __future__ import annotations

import sys
import types


class StubPlatform:
    def __init__(self, name: str = "rocketchat") -> None:
        self.name = name

    def __str__(self) -> str:
        return self.name


class StubPlatformConfig:
    def __init__(self, extra: dict | None = None) -> None:
        self.extra = extra or {}


class StubMessageEvent:
    def __init__(self, text=None, source=None, message_id=None, timestamp=None) -> None:
        self.text = text
        self.source = source
        self.message_id = message_id
        self.timestamp = timestamp


class StubSendResult:
    def __init__(self, success=True, message_id=None, error=None) -> None:
        self.success = success
        self.message_id = message_id
        self.error = error


class StubBasePlatformAdapter:
    def __init__(self, config, platform) -> None:
        self.config = config
        self.platform = platform
        self.dispatched = []

    def build_source(self, **kwargs):
        return dict(kwargs)

    async def handle_message(self, event) -> None:
        self.dispatched.append(event)


def install_gateway_stubs() -> None:
    """Register fake ``gateway.*`` modules so the adapter can be imported."""
    gateway = types.ModuleType("gateway")
    config = types.ModuleType("gateway.config")
    platforms = types.ModuleType("gateway.platforms")
    base = types.ModuleType("gateway.platforms.base")

    setattr(config, "Platform", StubPlatform)
    setattr(config, "PlatformConfig", StubPlatformConfig)
    setattr(base, "BasePlatformAdapter", StubBasePlatformAdapter)
    setattr(base, "MessageEvent", StubMessageEvent)
    setattr(base, "MessageType", types.SimpleNamespace(TEXT="text"))
    setattr(base, "SendResult", StubSendResult)
    setattr(gateway, "config", config)
    setattr(gateway, "platforms", platforms)
    setattr(platforms, "base", base)

    sys.modules.setdefault("gateway", gateway)
    sys.modules.setdefault("gateway.config", config)
    sys.modules.setdefault("gateway.platforms", platforms)
    sys.modules.setdefault("gateway.platforms.base", base)
