#!/usr/bin/env python3
"""
Standalone Rocket.Chat bridge — sends a message as hermes-bot.

Useful for testing, cron job delivery, or running the bridge as a
separate process from the Hermes gateway.

Usage:
    python standalone_example.py --room-id <room-id> --text "Hello from the bridge"
"""

import argparse
import asyncio
import os
import sys

# Add the plugin path for imports when running standalone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from plugin.adapter import _standalone_send, PlatformConfig


async def main():
    parser = argparse.ArgumentParser(description="Send a message via Rocket.Chat")
    parser.add_argument("--room-id", required=True, help="Rocket.Chat room ID (or username for DMs)")
    parser.add_argument("--text", required=True, help="Message text to send")
    parser.add_argument("--thread-id", help="Optional thread ID to reply in")
    args = parser.parse_args()

    pconfig = PlatformConfig(extra={})

    result = await _standalone_send(
        pconfig,
        chat_id=args.room_id,
        message=args.text,
        thread_id=args.thread_id,
    )

    if "error" in result:
        print(f"ERROR: {result['error']}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"Sent! message_id={result.get('message_id')}")


if __name__ == "__main__":
    asyncio.run(main())