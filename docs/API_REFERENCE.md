# Rocket.Chat REST API endpoints used by the hermes-rocketchat plugin
# Reference: https://developer.rocket.chat/reference/api/rest-api

## Authentication

### POST /api/v1/login
Authenticate and obtain auth token + user ID.

Request:
```json
{
  "user": "hermes-bot",
  "password": "secret"
}
```

Response:
```json
{
  "status": "success",
  "data": {
    "userId": "rocket.cat",
    "authToken": "abcd..."
  }
}
```

Required headers for all subsequent requests:
```
X-Auth-Token: <authToken>
X-User-Id: <userId>
Content-Type: application/json
```

---

## Messaging

### POST /api/v1/chat.sendMessage
Send a message to a room.

```json
{
  "message": {
    "rid": "<room-id>",
    "text": "Hello world"
  }
}
```

With thread reply:
```json
{
  "message": {
    "rid": "<room-id>",
    "tmid": "<thread-id>",
    "text": "Reply in thread"
  }
}
```

Response:
```json
{
  "success": true,
  "message": {
    "_id": "<message-id>",
    "rid": "<room-id>",
    "msg": "Hello world",
    "ts": "2026-05-22T12:00:00.000Z"
  }
}
```

---

### GET /api/v1/im.history
Fetch recent messages from a DM room (newest first).

Query params:
- `roomId` (required) — room ID
- `count` (optional, the adapter uses 20) — max messages to return

Note: `chat.getMessages` is *not* a room-history endpoint — since 8.9.0 it is a
`POST` that looks messages up by `messageIds`.

Response:
```json
{
  "messages": [
    {
      "_id": "<msg-id>",
      "rid": "<room-id>",
      "msg": "Hello",
      "u": { "_id": "rocket.cat", "username": "rocket.cat" },
      "ts": "2026-05-22T12:00:00.000Z",
      "tmid": null
    }
  ]
}
```

---

## Subscriptions

### GET /api/v1/subscriptions.get
List all rooms (DMs + channels) the bot is a member of.

Query params:
- `limit` (optional, default 50)

Response:
```json
{
  "update": [
    {
      "rid": "<room-id>",
      "t": "d",
      "name": "rocket.cat"
    }
  ]
}
```

`"t": "d"` = DM, `"t": "c"` = public channel, `"t": "p"` = private channel.

---

## Rooms

### GET /api/v1/rooms.info
Get metadata about a specific room.

Query params:
- `roomId` (required)

Response:
```json
{
  "success": true,
  "room": {
    "_id": "<room-id>",
    "name": "general",
    "t": "c"
  }
}
```

---

## Users

### GET /api/v1/me
Get the authenticated user's own profile. Used to resolve the bot's username after login.

Response:
```json
{
  "_id": "rocket.cat",
  "username": "rocket.cat",
  "status": "online"
}
```

---

## Error codes

| HTTP status | Meaning |
|---|---|
| 400 | Bad request (missing params) |
| 401 | Authentication failed (bad credentials) |
| 403 | Forbidden (user lacks permission) |
| 404 | Room/user not found |
| 500 | Rocket.Chat server error |