"""Rocket.Chat platform plugin for Hermes Agent."""

try:  # normal case: imported as a package by the Hermes plugin loader
    from .adapter import (
        RocketChatAdapter,
        check_requirements,
        validate_config,
        is_connected,
        interactive_setup,
        register,
    )
except ImportError:  # imported as a top-level module (standalone / test tooling)
    from adapter import (  # type: ignore[no-redef]
        RocketChatAdapter,
        check_requirements,
        validate_config,
        is_connected,
        interactive_setup,
        register,
    )

__all__ = [
    "RocketChatAdapter",
    "check_requirements",
    "validate_config",
    "is_connected",
    "interactive_setup",
    "register",
]