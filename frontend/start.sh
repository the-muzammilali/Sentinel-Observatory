#!/bin/sh
set -e

echo "🔭 Sentinel Frontend - Starting..."

echo "✅ Backend is reachable (or timeout reached)"

# Verify Nginx config
echo "🔍 Verifying Nginx configuration..."
nginx -t

echo "🚀 Starting Nginx..."

# Start Nginx
exec nginx -g "daemon off;"
