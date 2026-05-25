"""Rocket.Chat platform plugin for Hermes Agent."""

from .adapter import (
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