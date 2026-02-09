"""
Authentication middleware for Sentinel Observatory
Simple username/password authentication for hackathon deployment
"""

import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, Security, status, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import hashlib

# Hardcoded credentials for hackathon (can be overridden by env vars)
DEFAULT_USERNAME = "sentinel"
DEFAULT_PASSWORD = "observatory2024"

# Get credentials from environment or use defaults
AUTH_USERNAME = os.getenv("AUTH_USERNAME", DEFAULT_USERNAME)
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", DEFAULT_PASSWORD)

# Simple session store (in-memory for hackathon)
# In production, use Redis or database
active_sessions = {}
SESSION_DURATION = timedelta(hours=24)

security_basic = HTTPBasic()
security_bearer = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    message: str


def hash_password(password: str) -> str:
    """Simple password hashing for comparison."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_credentials(username: str, password: str) -> bool:
    """Verify username and password."""
    return username == AUTH_USERNAME and password == AUTH_PASSWORD


def create_session_token() -> str:
    """Generate a secure session token."""
    return secrets.token_urlsafe(32)


def verify_session_token(token: str) -> bool:
    """Verify if session token is valid and not expired."""
    if token not in active_sessions:
        return False
    
    session = active_sessions[token]
    if datetime.now() > session["expires"]:
        # Session expired, remove it
        del active_sessions[token]
        return False
    
    return True


def create_session(username: str) -> str:
    """Create a new session and return token."""
    token = create_session_token()
    active_sessions[token] = {
        "username": username,
        "created": datetime.now(),
        "expires": datetime.now() + SESSION_DURATION,
    }
    return token


def cleanup_expired_sessions():
    """Remove expired sessions from memory."""
    now = datetime.now()
    expired = [token for token, session in active_sessions.items() 
               if now > session["expires"]]
    for token in expired:
        del active_sessions[token]


async def verify_auth_basic(credentials: HTTPBasicCredentials = Depends(security_basic)) -> str:
    """Verify HTTP Basic Auth credentials."""
    if not verify_credentials(credentials.username, credentials.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


async def verify_auth_token(credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer)) -> str:
    """Verify Bearer token authentication."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not verify_session_token(credentials.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Return username from session
    return active_sessions[credentials.credentials]["username"]


async def optional_auth(credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer)) -> Optional[str]:
    """Optional authentication - returns username if authenticated, None otherwise."""
    if not credentials:
        return None
    
    if verify_session_token(credentials.credentials):
        return active_sessions[credentials.credentials]["username"]
    
    return None


def get_session_info() -> dict:
    """Get information about active sessions (for monitoring)."""
    cleanup_expired_sessions()
    return {
        "active_sessions": len(active_sessions),
        "sessions": [
            {
                "username": session["username"],
                "created": session["created"].isoformat(),
                "expires": session["expires"].isoformat(),
            }
            for session in active_sessions.values()
        ]
    }
