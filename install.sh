#!/usr/bin/env bash
# install.sh — Install the Rocket.Chat Hermes plugin into an existing Hermes Agent
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_DIR="$HERMES_HOME/hermes-agent/plugins/platforms/rocketchat"

echo "Installing Rocket.Chat Hermes plugin..."
echo "  Target: $PLUGIN_DIR"
echo ""

# Locate the plugin source (relative to this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR/hermes-agent/plugins/platforms/rocketchat"

if [ ! -d "$SOURCE_DIR" ]; then
  echo "ERROR: Cannot find plugin source at $SOURCE_DIR"
  echo "Make sure you're running this from the project root."
  exit 1
fi

# Check Hermes is installed
if [ ! -d "$HERMES_HOME/hermes-agent" ]; then
  echo "ERROR: Hermes Agent not found at $HERMES_HOME/hermes-agent"
  echo "Is Hermes installed? Try: curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash"
  exit 1
fi

# Create and copy
mkdir -p "$PLUGIN_DIR"
cp "$SOURCE_DIR"/*.py "$PLUGIN_DIR/"
cp "$SOURCE_DIR"/plugin.yaml "$PLUGIN_DIR/"

echo "✓ Plugin files installed"
echo ""
echo "Next steps:"
echo ""
echo "1. Create a bot user in Rocket.Chat (Admin > Users > New User, role: bot)"
echo ""
echo "2. Add these env vars to $HERMES_HOME/.env:"
echo "   ROCKETCHAT_URL=http://localhost:3000"
echo "   ROCKETCHAT_USER=hermes-bot"
echo "   ROCKETCHAT_PASSWORD=<bot-password>"
echo ""
echo "3. Restart the gateway:"
echo "   hermes gateway restart"
echo "   sleep 3"
echo "   hermes gateway status"
echo ""
echo "For more details, see README.md"
