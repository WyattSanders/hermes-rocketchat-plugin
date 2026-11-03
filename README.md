# Hermes Agent — Rocket.Chat Platform Plugin 🚀

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) platform plugin that connects to a self-hosted [Rocket.Chat](https://rocket.chat/) server via REST API polling.

Supports DMs, channel messages, threaded replies, and cron job delivery. No external dependencies beyond `requests`.

## Features

- **Bi-directional chat** — talk to Hermes via Rocket.Chat DMs
- **Thread support** — threaded replies map to Rocket.Chat threads
- **Channel delivery** — send cron job output to any room
- **Authorization** — allowlist users or open it up to everyone
- **Zero dependencies** — only needs the built-in `requests` library

## Quick Install

### Option 1: `hermes plugins install` (recommended)

```bash
hermes plugins install WyattSanders/hermes-rocketchat-plugin
hermes plugins enable rocketchat-platform
```

Then set your env vars and restart the gateway:

```bash
cat >> ~/.hermes/.env << 'EOF'
ROCKETCHAT_URL=http://localhost:3000
ROCKETCHAT_USER=hermes-bot
ROCKETCHAT_PASSWORD=your-bot-password
ROCKETCHAT_ALLOW_ALL_USERS=true
ROCKETCHAT_HOME_CHANNEL=hermes-cron
EOF

hermes gateway restart
hermes gateway status
```

### Option 2: Manual copy

```bash
# Clone and copy the plugin files into your Hermes Agent installation
git clone https://github.com/WyattSanders/hermes-rocketchat-plugin.git
cp -r hermes-rocketchat-plugin/hermes-agent/plugins/platforms/rocketchat \
      ~/.hermes/hermes-agent/plugins/platforms/rocketchat/

# OR use the install script
cd hermes-rocketchat-plugin
bash install.sh
```

Then set env vars and restart as above.

## Prerequisites

- A running Rocket.Chat server (self-hosted or cloud)
- A **bot user** created in Rocket.Chat with the `bot` role

### Creating a Bot User

1. Open your Rocket.Chat instance (e.g. `http://localhost:3000`)
2. Go to **Administration → Users → New User**
3. Fill in:
   - **Username:** `hermes-bot`
   - **Roles:** click "Add Role" and select `bot`
4. Save and copy the password

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ROCKETCHAT_URL` | Yes | — | Rocket.Chat server URL (e.g. `http://pluto:3030`) |
| `ROCKETCHAT_USER` | Yes | — | Bot username |
| `ROCKETCHAT_PASSWORD` | Yes | — | Bot password |
| `ROCKETCHAT_POLL_INTERVAL` | No | `3` | Seconds between message polls |
| `ROCKETCHAT_ALLOWED_USERS` | No | — | Comma-separated usernames allowed to chat. If neither this nor `ROCKETCHAT_ALLOW_ALL_USERS` is set, all messages are ignored |
| `ROCKETCHAT_ALLOW_ALL_USERS` | No | `false` | Allow any user to interact with the bot (required if no allowlist is set) |
| `ROCKETCHAT_HOME_CHANNEL` | No | — | Room ID for cron/notification delivery |

### YAML Config (alternative)

```yaml
# ~/.hermes/config.yaml
gateway:
  platforms:
    rocketchat:
      enabled: true
      extra:
        url: "http://localhost:3000"
        username: "hermes-bot"
        password: "secret"
        poll_interval: 3
```

## Usage

### Chat via DM

1. Open Rocket.Chat and search for your bot user (e.g. `hermes-bot`)
2. Start a direct message
3. Send any message — Hermes will respond!

### Cron Delivery

```bash
# Schedule a daily briefing delivered to Rocket.Chat
hermes cron create \
  --name "daily-brief" \
  --deliver rocketchat:hermes-cron \
  --schedule "0 8 * * *" \
  "Summarize today's headlines"
```

### Standalone Sender

For scripts or cron jobs outside the gateway process:

```bash
python standalone_example.py --room-id GENERAL --text "Hello from the bridge"
```

## Verification

Test auth manually:

```bash
curl -X POST http://localhost:3000/api/v1/login \
  -H "Content-Type: application/json" \
  -d '{"user":"hermes-bot","password":"your-password"}'
# → {"status":"success","data":{"authToken":"...","userId":"..."}}
```

## How It Works

```
Hermes Gateway → RocketChatAdapter → Rocket.Chat REST API
                 (polling loop)      (DMs, channels)
```

The adapter polls Rocket.Chat's `subscriptions.get` endpoint every N seconds, processes new DM messages, and dispatches them to the Hermes gateway as `MessageEvent` objects. Outgoing messages are sent via `chat.sendMessage`.

## Troubleshooting

**Plugin not showing up in `hermes gateway status`**
- If installed via `hermes plugins install`, make sure to enable it: `hermes plugins enable rocketchat-platform`
- The gateway caches discovered platforms at startup. Restart after installing.
- `hermes gateway restart && sleep 3 && hermes gateway status`

**Auth failures**
- Verify the bot user exists and has the `bot` role in Rocket.Chat admin
- Test credentials with the curl command above

**MongoDB compatibility**
- Rocket.Chat 8.x requires MongoDB 8.0+. Consider using MongoDB 7.0 for stability until Rocket.Chat 9 releases.

## Project Structure

```
├── plugin.yaml          # Hermes plugin manifest (kind: platform)
├── __init__.py          # Plugin entry point
├── adapter.py           # Full RocketChatAdapter (522 lines)
├── standalone_example.py  # Send messages without the gateway
├── install.sh           # Manual install script
├── docs/                # API reference, Docker setup, troubleshooting
└── hermes-agent/        # Manual copy layout (same files)
```

## License

MIT
