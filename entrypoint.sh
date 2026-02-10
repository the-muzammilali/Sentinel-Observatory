#!/bin/bash
set -e

# Fix permissions for data and logs directories
# This ensures the 'sentinel' user can write to mounted volumes
if [ "$(id -u)" = '0' ]; then
    echo "🔧 Fixing permissions for /app/data and /app/logs..."
    chown -R sentinel:sentinel /app/data /app/logs
    
    # Drop privileges and execute the command
    echo "👤 Switching to user 'sentinel'..."
    exec gosu sentinel "$@"
fi

# If already running as non-root, just execute
exec "$@"
