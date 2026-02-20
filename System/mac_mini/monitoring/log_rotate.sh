#!/bin/bash
# Rotate agent logs to prevent disk exhaustion.
# Run weekly via cron: 0 3 * * 0 bash ~/Desktop/cursor/System/mac_mini/monitoring/log_rotate.sh

LOG_DIR="$HOME/Desktop/cursor/System/mac_mini/agent_orchestrator/logs"
MAX_SIZE_MB=50
KEEP_DAYS=30

if [ ! -d "$LOG_DIR" ]; then
    exit 0
fi

for logfile in "$LOG_DIR"/*.log; do
    [ -f "$logfile" ] || continue

    size_bytes=$(stat -f%z "$logfile" 2>/dev/null || stat --format=%s "$logfile" 2>/dev/null)
    size_mb=$((size_bytes / 1048576))

    if [ "$size_mb" -gt "$MAX_SIZE_MB" ]; then
        timestamp=$(date +%Y%m%d_%H%M%S)
        mv "$logfile" "${logfile}.${timestamp}"
        gzip "${logfile}.${timestamp}" 2>/dev/null &
        touch "$logfile"
        echo "Rotated: $(basename "$logfile") (${size_mb}MB)"
    fi
done

find "$LOG_DIR" -name "*.gz" -mtime +$KEEP_DAYS -delete 2>/dev/null
