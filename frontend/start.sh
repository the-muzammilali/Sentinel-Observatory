#!/bin/sh
set -e

echo "🔭 Sentinel Frontend - Starting..."

# Note: We rely on Nginx lazy resolution (set $variable) to handle backend unavailability
# without crashing. We don't block startup here so the frontend becomes healthy immediately.

echo "🚀 Starting Nginx..."

# Start Nginx
exec nginx -g "daemon off;"
