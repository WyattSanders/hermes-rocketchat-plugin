"""Stub the Hermes gateway modules so adapter.py can be imported offline."""
import dataclasses
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, Optional

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _install_gateway_stubs():
    gateway = types.ModuleType("gateway")
    config = types.ModuleType("gateway.config")
    platforms = types.ModuleType("gateway.platforms")
    base = types.ModuleType("gateway.platforms.base")

    @dataclasses.dataclass
    class PlatformConfig:
        extra: Optional[dict] = None

    class Platform(str):
        pass

    @dataclasses.dataclass
    class SendResult:
        success: bool
        message_id: Optional[str] = None
        error: Optional[str] = None

    @dataclasses.dataclass
    class MessageEvent:
        text: str
        source: Any
        message_id: str
        timestamp: Any

    class BasePlatformAdapter:
        def __init__(self, config, platform):
            self.config = config
            self.platform = platform
            self.handled = []

        def build_source(self, **kw):
            return kw

        async def handle_message(self, event):
            self.handled.append(event)

    config.PlatformConfig = PlatformConfig
    config.Platform = Platform
    base.BasePlatformAdapter = BasePlatformAdapter
    base.MessageEvent = MessageEvent
    base.MessageType = object
    base.SendResult = SendResult
    sys.modules.update({
        "gateway": gateway, "gateway.config": config,
        "gateway.platforms": platforms, "gateway.platforms.base": base,
    })


_install_gateway_stubs()


def load_adapter(path):
    spec = importlib.util.spec_from_file_location(f"rc_adapter_{abs(hash(str(path)))}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def adapter_mod():
    return load_adapter(ROOT / "adapter.py")
