# Docker Setup for Rocket.Chat + Hermes Agent

**Pluto server config used in production** — your baseline for a working self-hosted Rocket.Chat deployment.

---

## docker-compose.yml (complete working config)

Tested on Pluto (Dell R720XD, Ubuntu 22.04, Docker).

```yaml
# Location: ~/services/docker-compose.yml

services:
  # ... (other services: qdrant, etc.)

  rocket-mongo:
    image: mongo:7.0
    restart: unless-stopped
    volumes:
      - ./rocketchat/mongo-data:/data/db
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      retries: 5

  rocketchat:
    image: registry.rocket.chat/rocketchat/rocket.chat:latest
    restart: unless-stopped
    ports:
      - "3030:3000"
    environment:
      MONGO_URL: mongodb://rocket-mongo:27017/rocketchat
      OVERWRITE_SETTING_Allow_Invalid_SelfSigned_Certs: "true"
    depends_on:
      rocket-mongo:
        condition: service_healthy
    labels:
      - "openclaw.service=true"
      - "openclaw.name=rocketchat"
```

> **Important:** Do NOT add `user: "0:0"` to the `rocketchat` or `rocket-mongo` containers. MongoDB 7+ containers run their own `mongo` user (uid 99999) internally. Forcing root causes permission failures on the data volume.

---

## Initial Setup

```bash
# 1. Create the mongo data directory
mkdir -p ~/services/rocketchat/mongo-data

# 2. Add the yaml above to ~/services/docker-compose.yml (or append using the snippet in README.md)

# 3. Start fresh (clears any existing broken data from mongo 6.0):
cd ~/services
docker compose stop rocketchat rocket-mongo
sudo rm -rf ~/services/rocketchat/mongo-data/*
docker compose up -d rocket-mongo
# Wait ~30s for mongo to start, then:
docker compose up -d rocketchat

# 4. Wait 2–3 minutes for Rocket.Chat to initialize
#    Then open http://localhost:3030 and create your admin account

# 5. Verify
curl -s http://localhost:3030 | grep -o 'Rocket.Chat [^"]*' | head -1
```

---

## Creating the bot user

1. Log in as admin at `http://localhost:3030`
2. **Administration → Users → New User**
   - Name: `hermes-bot`
   - Username: `hermes-bot`
   - Email: `hermes-bot@pluto.local`
   - Password: `<use a strong password>`
   - Roles: check **`bot`** (this is critical — the bot role is required for API access)
3. Click **Save**
4. Copy the password for the next step

### Verifying bot auth

```bash
curl -X POST http://localhost:3030/api/v1/login \
  -H "Content-Type: application/json" \
  -d '{"user":"hermes-bot","password":"your-password"}'
```

Expected response:
```json
{"status":"success","data":{"userId":"...","authToken":"..."}}
```

---

## Upgrading Rocket.Chat

```bash
cd ~/services
docker compose pull rocketchat
docker compose up -d rocketchat
# Rocket.Chat auto-migrates the DB on first start with the new image
```

---

## Data backup

```bash
# Stop writing to ensure consistent snapshot
docker compose stop rocketchat
tar -czf ~/backups/rocketchat-$(date +%Y%m%d).tar.gz ~/services/rocketchat/mongo-data/
docker compose start rocketchat
```

---

## Reset (full reinstall)

```bash
docker compose stop rocketchat rocket-mongo
sudo rm -rf ~/services/rocketchat/mongo-data/*
docker compose up -d rocket-mongo
# Wait for healthy...
docker compose up -d rocketchat
# Re-register at http://localhost:3030 to create admin account
# Re-create hermes-bot user
```