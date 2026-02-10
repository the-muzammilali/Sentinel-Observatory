/**
 * Centralized API configuration
 * 
 * Handles URL construction for:
 * - Local development (npm run dev) -> localhost:8000
 * - Production (Docker/Nginx) -> relative paths (proxied by Nginx)
 */

const isDev = import.meta.env.DEV;

// API Base URL
// Dev: http://localhost:8000
// Prod: relative path (allows Nginx to proxy /api requests)
export const API_BASE_URL = isDev ? 'http://localhost:8000' : '';

// WebSocket Base URL
// Dev: ws://localhost:8000
// Prod: ws://<current_host> (Nginx proxies /ws requests)
export const WS_BASE_URL = isDev 
  ? 'ws://localhost:8000' 
  : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;

// Stream Base URL (for EventSource/SSE)
// Dev: http://localhost:8000
// Prod: relative path (allows Nginx to proxy /stream requests)
export const STREAM_BASE_URL = isDev ? 'http://localhost:8000' : '';
