# Troubleshooting Guide

## Bot doesn't respond after gateway restart

**Cause:** The gateway caches discovered plugins at startup. If the gateway was
running before you added the rocketchat plugin, it won't see it until restarted.

**Fix:**
```bash
hermes gateway restart
```

Verify the plugin is loaded:
```bash
hermes gateway status
# or
grep -i rocketchat ~/.hermes/gateway.log
```

---

## "MongoDB is not supported" error

Rocket.Chat 8.x requires MongoDB 7.0 or higher. If you previously used MongoDB 6.0,
the existing data is incompatible.

**Fix — clean reset (WARNING: destroys Rocket.Chat data):**
```bash
cd ~/services
docker compose stop rocketchat rocket-mongo
sudo rm -rf ~/services/rocketchat/mongo-data/*
docker compose up -d rocket-mongo
# Wait 30s for mongo to be healthy
docker compose up -d rocketchat
```

---

## "permission denied" on mongo-data volume

Do NOT use `user: "0:0"` in your docker-compose for the rocket-mongo container.
MongoDB 7+ images run their `mongod` process as a non-root user internally.

If you already have permission errors:
```bash
docker compose stop rocketchat rocket-mongo
sudo rm -rf ~/services/rocketchat/mongo-data/*
docker compose up -d rocket-mongo
docker compose up -d rocketchat
```

---

## Auth failing (401 / 403)

Manually verify bot credentials:
```bash
curl -X POST http://localhost:3030/api/v1/login \
  -H "Content-Type: application/json" \
  -d '{"user":"hermes-bot","password":"your-password"}'
```

Expected: `{"status":"success","data":{"userId":"...","authToken":"..."}}`

If it fails:
- Double-check the username (it must match exactly, case-sensitive)
- Make sure the user has the **`bot`** role in Rocket.Chat (Admin → Users → edit user → Roles)
- Try resetting the password in Rocket.Chat Admin panel

---

## Bot responds to some users but not others

By default (`ROCKETCHAT_ALLOW_ALL_USERS=false` and no `ROCKETCHAT_ALLOWED_USERS` set),
the bot ignores **all** messages and logs a warning at startup.

To restrict to specific users, in `~/.hermes/.env`:
```bash
ROCKETCHAT_ALLOWED_USERS=alice,bob
```

Or allow everyone:
```bash
ROCKETCHAT_ALLOW_ALL_USERS=true
```

---

## Messages sent to wrong room / duplicate messages

The plugin tracks seen message IDs in memory. After a restart it only processes
messages newer than the bot's last reply in each DM, so answered messages are not replayed.

If you see many duplicates in a short window, check that only one instance of the
gateway is running:
```bash
ps aux | grep hermes
docker ps | grep rocketchat
```

---

## Rocket.Chat not starting — "already using exceptions"

Usually means MongoDB 7.0 wiredTiger incompatibilities with old data from MongoDB 6.0.

```bash
# Full reset
docker compose stop rocketchat rocket-mongo
sudo rm -rf ~/services/rocketchat/mongo-data/*
docker compose up -d rocket-mongo
# Wait for: "Rocket.Chat MongoDB is waiting for connections"
docker compose up -d rocketchat
```

---

## Plugin loads but never polls (gateway log shows no errors)

Check the poll interval — if set too high, messages appear to never get picked up:
```bash
# In ~/.hermes/.env
ROCKETCHAT_POLL_INTERVAL=1   # seconds (default: 3, min recommended: 1)
```

Also check that the `requests` library is installed:
```bash
python -c "import requests; print('requests OK')"
```

---

## Self-test commands

```bash
# 1. Check requirements
python -c "from plugin.adapter import check_requirements; print('reqs:', check_requirements())"

# 2. Check config validation
python -c "from plugin.adapter import validate_config, PlatformConfig; \
cfg = PlatformConfig(extra={'url':'http://localhost:3030','username':'hermes-bot','password':'secret'}); \
print('valid:', validate_config(cfg))"

# 3. Check connectivity
python -c "from plugin.adapter import is_connected, PlatformConfig; \
cfg = PlatformConfig(extra={}); print('connected:', is_connected(cfg))"
```

Add `export ROCKETCHAT_URL=http://localhost:3030
export ROCKETCHAT_USER=hermes-bot
export ROCKETCHAT_PASSWORD=secret` before step 3 to test with real credentials.

---

## Getting help

- Rocket.Chat docs: https://docs.rocket.chat
- Hermes Agent repo: https://github.com/nousresearch/hermes-agent
- Open an issue at the Hermes Agent repo with `rocketchat` in the title