#!/bin/sh
set -e

echo "🔭 Sentinel Frontend - Starting..."

# Wait for backend to be ready
echo "⏳ Waiting for backend to be ready at http://backend:8000..."
max_retries=30
counter=0

while ! wget --spider --quiet http://backend:8000/health; do
    counter=$((counter+1))
    if [ $counter -gt $max_retries ]; then
        echo "❌ Backend failed to start after $max_retries attempts."
        # We don't exit here to allow Nginx to start anyway (in case health check endpoint is different)
        # but we log the error clearly.
        break
    fi
    echo "   ... waiting for backend ($counter/$max_retries)"
    sleep 2
done

echo "✅ Backend is reachable (or timeout reached)"
echo "🚀 Starting Nginx..."

# Start Nginx
exec nginx -g "daemon off;"
