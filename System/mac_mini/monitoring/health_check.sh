#!/bin/bash
# Health check script for the agent orchestrator.
# Run manually or via cron as a safety net.

PLIST_NAME="com.addness.agent-orchestrator"
HEALTH_URL="http://localhost:8500/health"
LOG_DIR="$HOME/Desktop/cursor/System/mac_mini/agent_orchestrator/logs"

echo "========================================"
echo "  Agent Health Check - $(date)"
echo "========================================"

# [1] LaunchAgent status
echo ""
echo "[1/4] LaunchAgent Status"
if launchctl list 2>/dev/null | grep -q "$PLIST_NAME"; then
    PID=$(launchctl list | grep "$PLIST_NAME" | awk '{print $1}')
    echo "  Status: RUNNING (PID: $PID)"
else
    echo "  Status: NOT RUNNING"
    echo "  -> Attempting restart..."
    PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
    if [ -f "$PLIST_PATH" ]; then
        launchctl load "$PLIST_PATH"
        echo "  -> Restart issued"
    else
        echo "  -> Plist not found at $PLIST_PATH"
    fi
fi

# [2] HTTP health endpoint
echo ""
echo "[2/4] HTTP Health Endpoint"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$HEALTH_URL" 2>/dev/null)
if [ "$RESPONSE" = "200" ]; then
    echo "  Endpoint: OK (HTTP $RESPONSE)"
    curl -s "$HEALTH_URL" 2>/dev/null | python3 -m json.tool 2>/dev/null | head -20
else
    echo "  Endpoint: FAILED (HTTP $RESPONSE)"
fi

# [3] Disk usage
echo ""
echo "[3/4] Disk Usage"
DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}')
echo "  Root disk: $DISK_USAGE used"
DISK_PCT=$(echo "$DISK_USAGE" | sed 's/%//')
if [ "$DISK_PCT" -gt 85 ]; then
    echo "  WARNING: Disk usage above 85%"
fi

# [4] Log file sizes
echo ""
echo "[4/4] Log Files"
if [ -d "$LOG_DIR" ]; then
    du -sh "$LOG_DIR"/*.log 2>/dev/null | while read size file; do
        echo "  $file: $size"
    done
else
    echo "  Log directory not found"
fi

echo ""
echo "========================================"
echo "  Health check complete"
echo "========================================"
