# hermes-rocketchat plugin (Hermes Agent v2)
# Copy or symlink this directory into your Hermes Agent plugins/platforms/ directory:
#
#   macOS/Linux:  ~/.hermes/hermes-agent/plugins/platforms/rocketchat/
#   Windows:      %USERPROFILE%\.hermes\hermes-agent\plugins\platforms\rocketchat\
#
# After adding/changing the plugin, restart the gateway:
#   hermes gateway restart

hermes-rocketchat/
├── plugin/
│   ├── __init__.py          # Public exports (copy this)
│   ├── adapter.py           # RocketChatAdapter + helpers (copy this)
│   ├── plugin.yaml          # Plugin manifest (copy this)
│   └── standalone_example.py # Standalone sender for cron jobs (optional)
├── docs/
│   └── DOCKER_SETUP.md      # Detailed Rocket.Chat Docker setup
└── README.md                # Full documentation