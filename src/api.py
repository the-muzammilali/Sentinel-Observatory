"""
Sentinel Observatory - FastAPI Backend
Real-time API layer with WebSocket and SSE for frontend dashboard.
"""

import os
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, AsyncGenerator
import base64

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel

from src.utils.session_recorder import SessionRecorder
from src.auth import (
    verify_auth_token, 
    verify_credentials, 
    create_session, 
    cleanup_expired_sessions,
    LoginRequest,
    LoginResponse,
    get_session_info
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# STATE MANAGEMENT
# ============================================================================

class MarathonState:
    """Global state for marathon execution."""
    
    def __init__(self):
        self.is_running = False
        self.is_paused = False
        self.current_iteration = 0
        self.max_iterations = 16
        self.status = "idle"  # idle, running, paused, completed, error
        self.start_time: Optional[str] = None
        self.context_state: Optional[dict] = None
        self.ooda_loop = None
        self._websocket_clients: list[WebSocket] = []
        self._log_queue: asyncio.Queue = asyncio.Queue()
        self._stop_requested = False
        self._log_history: list[dict] = []  # Store logs for retrieval on refresh
        self._max_log_history = 1000  # Limit log history to prevent memory issues
    
    def add_log(self, log_entry: dict):
        """Add log entry with size limit."""
        self._log_history.append(log_entry)
        # Keep only last N entries to prevent unbounded growth
        if len(self._log_history) > self._max_log_history:
            self._log_history = self._log_history[-self._max_log_history:]
    
    def cleanup(self):
        """Clean up resources."""
        # Clean up OODA loop
        if self.ooda_loop:
            try:
                self.ooda_loop.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up OODA loop: {e}")
            self.ooda_loop = None
        
        # Clear state
        self.context_state = None
        self._log_history = []
        
        # Close WebSocket connections
        for ws in self._websocket_clients[:]:
            try:
                asyncio.create_task(ws.close())
            except Exception:
                pass
        self._websocket_clients = []
    
    def to_dict(self):
        return {
            "isRunning": self.is_running,
            "isPaused": self.is_paused,
            "currentIteration": self.current_iteration,
            "maxIterations": self.max_iterations,
            "status": self.status,
            "startTime": self.start_time,
        }

# Global state
marathon_state = MarathonState()

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class MarathonConfig(BaseModel):
    max_iterations: int = 16
    num_stars: int = 100
    num_transients: int = 2
    inject_false_positives: bool = True
    false_positive_rate: float = 0.3
    step_interval_hours: float = 0.5
    confirm_threshold: float = 0.8
    weather_enabled: bool = True
    random_seed: Optional[int] = None  # None = random each run

class StatusResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None

# ============================================================================
# LIFESPAN (Startup/Shutdown)
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("🔭 Sentinel Observatory API starting...")
    
    # Cleanup expired sessions periodically
    async def cleanup_task():
        while True:
            await asyncio.sleep(3600)  # Every hour
            cleanup_expired_sessions()
    
    cleanup_task_handle = asyncio.create_task(cleanup_task())
    
    yield
    
    logger.info("🔭 Sentinel Observatory API shutting down...")
    
    # Cancel cleanup task
    cleanup_task_handle.cancel()
    
    # Clean up marathon state
    marathon_state.cleanup()
    
    logger.info("✓ Cleanup complete")

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="Sentinel Observatory API",
    description="Real-time API for astronomical transient detection dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for frontend
# In production, replace with your actual frontend domain
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@app.post("/api/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Login endpoint - returns session token."""
    if not verify_credentials(request.username, request.password):
        return LoginResponse(
            success=False,
            message="Invalid username or password"
        )
    
    # Create session
    token = create_session(request.username)
    
    return LoginResponse(
        success=True,
        token=token,
        message="Login successful"
    )


@app.post("/api/auth/logout")
async def logout(username: str = Depends(verify_auth_token)):
    """Logout endpoint - invalidates session token."""
    # Token is already verified by dependency
    return {"success": True, "message": "Logged out successfully"}


@app.get("/api/auth/verify")
async def verify_auth(username: str = Depends(verify_auth_token)):
    """Verify if current token is valid."""
    return {"authenticated": True, "username": username}


# ============================================================================
# MARATHON CONTROL ENDPOINTS
# ============================================================================

@app.post("/api/marathon/start", response_model=StatusResponse)
async def start_marathon(config: MarathonConfig, username: str = Depends(verify_auth_token)):
    """Start a new observation marathon."""
    if marathon_state.is_running:
        raise HTTPException(status_code=400, detail="Marathon already running")
    
    # Clear old observation files to prevent stale images from loading
    obs_dir = Path("data/observations")
    if obs_dir.exists():
        for img_file in obs_dir.glob("iteration_*.png"):
            try:
                img_file.unlink()
            except Exception:
                pass
        for img_file in obs_dir.glob("iteration_*_diff.png"):
            try:
                img_file.unlink()
            except Exception:
                pass
    
    # Clear any lingering context state and log history
    marathon_state.context_state = None
    marathon_state._log_history = []
    
    marathon_state.is_running = True
    marathon_state.is_paused = False
    marathon_state.status = "running"
    marathon_state.current_iteration = 0
    marathon_state.max_iterations = config.max_iterations
    marathon_state.start_time = datetime.now().isoformat()
    marathon_state._stop_requested = False
    
    # Broadcast state update
    await broadcast_state_update()
    
    # Start marathon in background
    asyncio.create_task(run_marathon_async(config))
    
    return StatusResponse(
        success=True,
        message="Marathon started",
        data=marathon_state.to_dict()
    )

@app.post("/api/marathon/stop", response_model=StatusResponse)
async def stop_marathon(username: str = Depends(verify_auth_token)):
    """Stop the current marathon."""
    if not marathon_state.is_running:
        raise HTTPException(status_code=400, detail="No marathon running")
    
    marathon_state._stop_requested = True
    marathon_state.is_running = False
    marathon_state.status = "idle"
    marathon_state.current_iteration = 0
    
    # Clean up resources
    marathon_state.cleanup()
    
    await broadcast_state_update()
    
    return StatusResponse(success=True, message="Marathon stopped")

@app.post("/api/marathon/pause", response_model=StatusResponse)
async def pause_marathon(username: str = Depends(verify_auth_token)):
    """Pause/resume the current marathon."""
    if not marathon_state.is_running:
        raise HTTPException(status_code=400, detail="No marathon running")
    
    marathon_state.is_paused = not marathon_state.is_paused
    marathon_state.status = "paused" if marathon_state.is_paused else "running"
    
    await broadcast_state_update()
    
    return StatusResponse(
        success=True,
        message=f"Marathon {'paused' if marathon_state.is_paused else 'resumed'}"
    )

@app.get("/api/marathon/status")
async def get_marathon_status():
    """Get current marathon status."""
    return {
        "marathon": marathon_state.to_dict(),
        "context": marathon_state.context_state,
    }

@app.get("/api/marathon/logs")
async def get_marathon_logs():
    """Get log history for current/last marathon session.
    
    Used to restore logs after page refresh during active session.
    """
    return {
        "logs": marathon_state._log_history,
        "count": len(marathon_state._log_history),
    }

# ============================================================================
# DATA ENDPOINTS
# ============================================================================

@app.get("/api/iterations")
async def get_iterations():
    """Get all iterations from current/last marathon."""
    # TODO: Return actual iteration data from OODA loop
    return {"iterations": []}

@app.get("/api/iteration/{iteration_num}/image")
async def get_iteration_image(
    iteration_num: int,
    type: str = Query("current", enum=["current", "reference", "diff"])
):
    """Get telescope image for a specific iteration."""
    import io
    from PIL import Image
    
    obs_dir = Path("data/observations")
    image_path = None
    
    if type == "reference":
        # Reference can be in different locations
        candidates = [
            obs_dir / "reference.fits",
            obs_dir / "reference.png",
            obs_dir / "reference" / "observation.fits",
            obs_dir / "reference" / "observation.png",
        ]
    else:
        # Try both flat file structure and subdirectory structure
        iter_name = f"iteration_{iteration_num:03d}"
        if type == "diff":
            candidates = [
                obs_dir / f"{iter_name}_diff.png",
                obs_dir / iter_name / "diff.png",
            ]
        else:
            candidates = [
                obs_dir / f"{iter_name}.png",
                obs_dir / f"{iter_name}.fits",
                obs_dir / iter_name / "observation.png",
                obs_dir / iter_name / "observation.fits",
            ]
    
    # Find first existing file
    for path in candidates:
        if path.exists():
            image_path = path
            break
    
    if image_path is None:
        raise HTTPException(
            status_code=404, 
            detail=f"Image not found. Checked: {[str(p) for p in candidates]}"
        )
    
    # Load and return image
    if image_path.suffix == ".fits":
        try:
            from astropy.io import fits
            with fits.open(image_path) as hdul:
                data = hdul[0].data
                # Normalize to 0-255
                data = data - data.min()
                if data.max() > 0:
                    data = (data / data.max() * 255).astype('uint8')
                else:
                    data = data.astype('uint8')
                img = Image.fromarray(data)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to load FITS: {e}")
    else:
        img = Image.open(image_path)
    
    # Convert to PNG bytes
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    
    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"}  # Prevent caching of iteration images
    )


@app.get("/api/ground-truth")
async def get_ground_truth():
    """Get ground truth metrics for current marathon."""
    # Return from context state if available
    if marathon_state.context_state and "ground_truth" in marathon_state.context_state:
        gt = marathon_state.context_state["ground_truth"]
        return {
            "precision": gt.get("precision", 0),
            "recall": gt.get("recall", 0),
            "f1_score": gt.get("f1_score", 0),
            "true_positives": gt.get("true_positives", 0),
            "false_positives": gt.get("false_positives", 0),
            "false_negatives": gt.get("false_negatives", 0),
            "total_transients": gt.get("true_positives", 0) + gt.get("false_negatives", 0),
            "detected_transients": gt.get("true_positives", 0),
        }
    
    # Get from active OODA loop if available
    if marathon_state.ooda_loop and marathon_state.ooda_loop._ground_truth:
        try:
            gt = marathon_state.ooda_loop._ground_truth
            metrics = gt.get_metrics()
            # Count only real transients, not artifacts/false positives
            real_transients = sum(1 for e in gt.events.values() if e.is_real_transient)
            # Count detected transients (real transients where agent triggered an alert)
            detected_count = sum(1 for e in gt.events.values() if e.is_real_transient and e.alert_triggered)
            logger.debug(f"Ground truth: TP={metrics.true_positives}, alerted={detected_count}, total_real={real_transients}")
            return {
                "precision": metrics.precision,
                "recall": metrics.recall,
                "f1_score": metrics.f1_score,
                "true_positives": metrics.true_positives,
                "false_positives": metrics.false_positives,
                "false_negatives": metrics.false_negatives,
                "total_transients": real_transients,
                "detected_transients": detected_count,  # Count of real transients detected by agent
            }
        except Exception as e:
            logger.error(f"Error getting ground truth metrics: {e}")
            pass
    
    return {
        "precision": 0,
        "recall": 0,
        "f1_score": 0,
        "true_positives": 0,
        "false_positives": 0,
        "false_negatives": 0,
        "total_transients": 0,
        "detected_transients": 0,
    }


@app.get("/api/executions")
async def get_executions():
    """Get list of saved marathon executions for playback (legacy endpoint)."""
    # Redirect to new sessions endpoint for backwards compatibility
    sessions = SessionRecorder.list_sessions()
    return {
        "executions": [
            {
                "id": s["session_id"],
                "timestamp": s["start_time"],
                "total_iterations": s["total_iterations"],
                "confirmed_count": s.get("confirmed_count", 0),
            }
            for s in sessions[:20]
        ]
    }


@app.get("/api/sessions")
async def list_sessions():
    """Get list of all recorded sessions."""
    sessions = SessionRecorder.list_sessions()
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details by ID."""
    session = SessionRecorder.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/api/sessions/{session_id}/iterations/{iteration_num}")
async def get_session_iteration(session_id: str, iteration_num: int):
    """Get iteration data for a session."""
    iteration = SessionRecorder.get_iteration(session_id, iteration_num)
    if not iteration:
        raise HTTPException(
            status_code=404,
            detail=f"Iteration {iteration_num} not found in session {session_id}"
        )
    return iteration


@app.get("/api/sessions/{session_id}/iterations/{iteration_num}/image")
async def get_session_iteration_image(session_id: str, iteration_num: int):
    """Get iteration image for a session."""
    from PIL import Image
    import io
    
    image_path = SessionRecorder.get_image_path(session_id, iteration_num)
    if not image_path:
        raise HTTPException(
            status_code=404,
            detail=f"Image not found for iteration {iteration_num} in session {session_id}"
        )
    
    img = Image.open(image_path)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    
    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "max-age=3600"}
    )

# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================

@app.websocket("/ws/marathon")
async def websocket_marathon(websocket: WebSocket):
    """WebSocket endpoint for real-time marathon updates."""
    await websocket.accept()
    marathon_state._websocket_clients.append(websocket)
    
    try:
        # Send initial state
        # Only send context if marathon is actively running
        # This ensures page refresh shows clean state when not in active session
        initial_context = marathon_state.context_state if marathon_state.is_running else None
        await websocket.send_json({
            "type": "state_update",
            "marathon": marathon_state.to_dict(),
            "context": initial_context,
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
                # Handle control messages if needed
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if websocket in marathon_state._websocket_clients:
            marathon_state._websocket_clients.remove(websocket)

async def broadcast_state_update():
    """Broadcast state update to all connected WebSocket clients."""
    if not marathon_state._websocket_clients:
        return
    
    message = {
        "type": "state_update",
        "marathon": marathon_state.to_dict(),
        "context": marathon_state.context_state,
    }
    
    for ws in marathon_state._websocket_clients[:]:
        try:
            await ws.send_json(message)
        except Exception:
            marathon_state._websocket_clients.remove(ws)

async def broadcast_iteration_complete(iteration: int, context: dict):
    """Broadcast iteration completion to all connected clients."""
    message = {
        "type": "iteration_complete",
        "iteration": iteration,
        "context": context,
    }
    
    for ws in marathon_state._websocket_clients[:]:
        try:
            await ws.send_json(message)
        except Exception:
            marathon_state._websocket_clients.remove(ws)

# ============================================================================
# SERVER-SENT EVENTS (SSE) FOR LOG STREAMING
# ============================================================================

@app.get("/stream/agent-log")
async def stream_agent_log():
    """SSE endpoint for streaming agent log messages."""
    
    async def generate() -> AsyncGenerator[str, None]:
        """Generate SSE events from log queue."""
        while True:
            try:
                # Wait for log message (with timeout for keepalive)
                try:
                    message = await asyncio.wait_for(
                        marathon_state._log_queue.get(),
                        timeout=15.0
                    )
                    yield f"data: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield ": keepalive\n\n"
            except Exception as e:
                logger.error(f"SSE error: {e}")
                break
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

async def emit_log_message(message_type: str, content: str, **kwargs):
    """Emit a log message to SSE stream and store in history."""
    log_entry = {
        "type": message_type,
        "content": content,
        "iteration": marathon_state.current_iteration,
        "timestamp": datetime.now().isoformat(),
        **kwargs,
    }
    # Store in history with size limit
    marathon_state.add_log(log_entry)
    # Also queue for SSE streaming
    await marathon_state._log_queue.put(log_entry)

# ============================================================================
# MARATHON EXECUTION (ASYNC)
# ============================================================================

async def run_marathon_async(config: MarathonConfig):
    """Run marathon asynchronously with real-time updates."""
    # Initialize session recorder
    recorder = SessionRecorder()
    session_id = recorder.start_session(config.model_dump())
    
    try:
        logger.info(f"Starting marathon with config: {config} (session: {session_id})")
        
        # Import OODA loop (lazy import to avoid startup delay)
        from src.ooda_loop import OODALoop, LoopConfig
        
        # Create OODA loop config
        # Generate truly random seed if not provided (using system entropy)
        if config.random_seed is not None:
            effective_seed = config.random_seed
        else:
            import os
            import time as time_module
            # Use system entropy + time for truly random seed (1-10000 range for ScopeSim)
            entropy = int.from_bytes(os.urandom(4), 'big') ^ int(time_module.time() * 1000)
            effective_seed = (entropy % 10000) + 1
        
        loop_config = LoopConfig(
            max_iterations=config.max_iterations,
            num_stars=config.num_stars,
            num_transients=config.num_transients,
            inject_false_positives=config.inject_false_positives,
            num_false_positives=int(config.false_positive_rate * 10),  # Scale 0.0-1.0 to 0-10 artifacts
            step_interval_hours=config.step_interval_hours,
            confirm_threshold=config.confirm_threshold,
            weather_enabled=config.weather_enabled,
            random_seed=effective_seed,
        )
        logger.info(f"Using random seed: {effective_seed}")
        
        # Initialize OODA loop
        await emit_log_message("info", "Initializing OODA loop components...")
        
        # Run initialization in thread pool to not block event loop
        loop = asyncio.get_event_loop()
        ooda = OODALoop(config=loop_config)
        
        # Initialize in background (heavy operation)
        init_success = await loop.run_in_executor(None, ooda.initialize)
        
        if not init_success:
            marathon_state.status = "error"
            await emit_log_message("error", "Failed to initialize OODA loop")
            await broadcast_state_update()
            return
        
        marathon_state.ooda_loop = ooda
        await emit_log_message("info", "OODA loop initialized successfully")
        
        # Run iterations
        for i in range(config.max_iterations):
            if marathon_state._stop_requested:
                logger.info("Marathon stop requested")
                break
            
            while marathon_state.is_paused:
                await asyncio.sleep(0.5)
                if marathon_state._stop_requested:
                    break
            
            if marathon_state._stop_requested:
                break
            
            marathon_state.current_iteration = i + 1
            
            # Run iteration in thread pool
            result = await loop.run_in_executor(None, ooda.run_iteration)
            
            # Get simulated time string for logs
            sim_time_str = ""
            if result.simulated_time:
                sim_time_str = result.simulated_time.strftime("%H:%M UT")
            
            # Stream the decision reasoning
            if result.decision:
                reasoning = result.decision.reasoning or ""
                
                # Emit deliberation with full reasoning content
                await emit_log_message(
                    "deliberation",
                    reasoning,
                    sim_time=sim_time_str,
                )
                
                # Brief pause to let deliberation render
                await asyncio.sleep(0.1)
                
                # Emit decision summary
                await emit_log_message(
                    "decision",
                    "",
                    action=result.decision.action,
                    reasoning=reasoning,
                    confidence=result.decision.confidence,
                    sim_time=sim_time_str,
                )
            
            # Update context state from OODA loop
            context = ooda._context
            weather = result.weather
            
            marathon_state.context_state = {
                "iteration": result.iteration,
                "simulated_time": result.simulated_time.isoformat() if result.simulated_time else None,
                "weather": {
                    "seeing": weather.seeing if weather else 1.0,
                    "cloud_extinction": weather.cloud_extinction if weather else 0.0,
                    "observability": weather.observability.value if weather and hasattr(weather, 'observability') else "GOOD",
                },
                "candidates": [
                    {
                        "id": c.id,
                        "x": c.x,
                        "y": c.y,
                        "status": c.status.value if hasattr(c.status, 'value') else str(c.status),
                        "confidence": c.confidence,
                        "observations": len(c.history) if hasattr(c, 'history') else 0,
                        "hypothesis": c.hypothesis,
                        "history": [
                            {
                                "time": h.time if hasattr(h, 'time') else None,
                                "magnitude": h.magnitude if hasattr(h, 'magnitude') else None,
                                "confidence": h.confidence if hasattr(h, 'confidence') else 0,
                                "note": h.note if hasattr(h, 'note') else "",
                            }
                            for h in (c.history if hasattr(c, 'history') else [])
                        ],
                    }
                    for c in (context.candidates if context else [])
                ],
                "decision": {
                    "action": result.decision.action if result.decision else None,
                    "reasoning": result.decision.reasoning if result.decision else None,
                    "confidence": result.decision.confidence if result.decision else 0,
                },
                "num_detections": result.num_detections,
                "alerts_triggered": context.alerts_triggered if context else 0,
            }
            
            # Record iteration for playback
            iteration_num = i + 1
            image_path = f"data/observations/iteration_{iteration_num:03d}.png"
            recorder.record_iteration(
                iteration=iteration_num,
                context_state=marathon_state.context_state,
                source_image_path=image_path,
            )
            
            # Broadcast update
            await broadcast_state_update()
            await broadcast_iteration_complete(i + 1, marathon_state.context_state)
            
            # Small delay between iterations
            await asyncio.sleep(0.5)
        
        # Get ground truth metrics if available
        ground_truth_summary = None
        if ooda._ground_truth:
            metrics = ooda._ground_truth.finalize_metrics()
            ground_truth_summary = {
                "precision": metrics.precision,
                "recall": metrics.recall,
                "f1_score": metrics.f1_score,
                "true_positives": metrics.true_positives,
                "false_positives": metrics.false_positives,
                "false_negatives": metrics.false_negatives,
            }
            marathon_state.context_state["ground_truth"] = ground_truth_summary
        
        # Finalize session recording
        recorder.finalize_session(ground_truth_summary)
        
        # Marathon complete
        marathon_state.is_running = False
        marathon_state.status = "completed"
        await emit_log_message("info", f"Marathon completed! {marathon_state.current_iteration} iterations finished. Session saved: {session_id}")
        await broadcast_state_update()
        
        logger.info(f"Marathon completed successfully. Session: {session_id}")
        
    except Exception as e:
        logger.error(f"Marathon error: {e}")
        import traceback
        traceback.print_exc()
        marathon_state.is_running = False
        marathon_state.status = "error"
        await emit_log_message("error", f"Marathon error: {str(e)}")
        await broadcast_state_update()
        
        # Still try to finalize the session even on error
        try:
            recorder.finalize_session()
        except Exception:
            pass


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "marathon_status": marathon_state.status,
    }

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
