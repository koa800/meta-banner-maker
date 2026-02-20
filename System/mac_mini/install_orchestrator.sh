#!/bin/bash
# Installs the agent orchestrator as a macOS LaunchAgent (runs on user login, auto-restart).
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ORCH_DIR="$SCRIPT_DIR/agent_orchestrator"
VENV_PYTHON="$HOME/agent-env/bin/python3"
PLIST_NAME="com.addness.agent-orchestrator"
PLIST_DST="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
LOG_DIR="$ORCH_DIR/logs"

mkdir -p "$LOG_DIR"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "ERROR: Virtual env not found at $VENV_PYTHON"
    echo "       Run setup_phase1.sh first."
    exit 1
fi

cat > "$PLIST_DST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/caffeinate</string>
        <string>-s</string>
        <string>${VENV_PYTHON}</string>
        <string>-m</string>
        <string>agent_orchestrator</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>PYTHONPATH</key>
        <string>${SCRIPT_DIR}</string>
    </dict>
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
PLIST

echo "Plist created: $PLIST_DST"

launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

echo ""
echo "Agent orchestrator installed and started."
echo ""
echo "Commands:"
echo "  launchctl list | grep $PLIST_NAME   # Check status"
echo "  launchctl stop $PLIST_NAME          # Stop"
echo "  launchctl start $PLIST_NAME         # Start"
echo "  launchctl unload $PLIST_DST         # Uninstall"
echo ""
echo "Logs:"
echo "  tail -f $LOG_DIR/stdout.log"
echo "  tail -f $LOG_DIR/stderr.log"
echo "  tail -f $LOG_DIR/orchestrator.log"
echo ""
echo "API:"
echo "  curl http://localhost:8500/health"
echo "  curl http://localhost:8500/tasks"
echo "  curl -X POST http://localhost:8500/run/ai_news_notify"
