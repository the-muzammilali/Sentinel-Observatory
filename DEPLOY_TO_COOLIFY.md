# 🚀 Deploy to Coolify - Quick Guide

## Your Configuration

**Domains:**

- Frontend: `sentinel.itpyx.pk`
- Backend: `api.sentinel.itpyx.pk`

---

## Step 1: Prepare Environment Variables

Create these in Coolify for the **backend** service:

```bash
AUTH_USERNAME=sentinel
AUTH_PASSWORD=observatory2024
GOOGLE_API_KEYS=your_api_keys_here
ALLOWED_ORIGINS=https://sentinel.itpyx.pk
GEMINI_MODEL=gemini-3.0-flash
USE_SCOPESIM=true
SIMULATION_SPEED=2
IMAGE_SIZE=1024
FIELD_OF_VIEW=60
NUM_STATIC_STARS=500
```

For the **frontend** service:

```bash
# No environment variables needed for frontend (uses relative paths)
```

---

## Step 2: Update DNS

Make sure these DNS records exist:

```
Type    Name                        Value
----    ----                        -----
A       sentinel.itpyx.pk          YOUR_VPS_IP
A       api.sentinel.itpyx.pk      YOUR_VPS_IP
```

---

## Step 3: Deploy in Coolify

### 1. Create New Resource

- Click "New Resource"
- Select "Docker Compose"
- Name: `sentinel-observatory`

### 2. Paste Docker Compose

Copy the entire `docker-compose.yml` file and paste it.

### 3. Configure Services

**Backend Service:**

- Service name: `backend`
- Domain: `api.sentinel.itpyx.pk`
- Port: `8000`
- Enable HTTPS ✅

**Frontend Service:**

- Service name: `frontend`
- Domain: `sentinel.itpyx.pk`
- Port: `80`
- Enable HTTPS ✅

### 4. Add Environment Variables

Add the variables from Step 1 to each service.

### 5. Deploy

Click "Deploy" and wait 5-10 minutes.

---

## Step 4: Verify Deployment

### Test Backend

```bash
curl https://api.sentinel.itpyx.pk/health
```

Should return:

```json
{ "status": "healthy", "timestamp": "...", "marathon_status": "idle" }
```

### Test Frontend

Open: `https://sentinel.itpyx.pk`

Should show login screen.

### Test API Docs

Open: `https://api.sentinel.itpyx.pk/docs`

Should show FastAPI documentation.

---

## Step 5: First Login

1. Go to `https://sentinel.itpyx.pk`
2. Login with:
   - Username: `sentinel` (or what you set)
   - Password: `observatory2024` (or what you set)
3. Start a marathon!

---

## Troubleshooting

### Frontend shows "Connection error"

- Check backend is running: `curl https://api.sentinel.itpyx.pk/health`
- Check CORS in backend environment variables
- Check browser console for errors

### Login fails

- Check backend logs in Coolify
- Verify credentials match environment variables
- Check `/api/auth/login` endpoint works

### WebSocket won't connect

- Check browser console for WebSocket errors
- Verify SSL is enabled on backend domain
- Check firewall allows WebSocket connections

---

## Quick Commands

### View Logs

In Coolify, click on service → "Logs"

### Restart Service

In Coolify, click on service → "Restart"

### Update Environment

In Coolify, click on service → "Environment" → Edit → Save → Restart

---

## 🎉 Done!

Your Sentinel Observatory is now live at:

- **Frontend:** https://sentinel.itpyx.pk
- **Backend:** https://api.sentinel.itpyx.pk
- **API Docs:** https://api.sentinel.itpyx.pk/docs

Good luck with your hackathon! 🔭✨
