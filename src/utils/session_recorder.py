"""
Session Recorder for marathon playback.

Records marathon sessions to disk for later replay, including:
- Session metadata (config, timing, summary)
- Per-iteration data (candidates, decisions, weather)
- Telescope images for each iteration
"""

import json
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class IterationData:
    """Data captured for a single iteration."""
    iteration: int
    timestamp: str
    simulated_time: Optional[str] = None
    weather: Optional[Dict[str, Any]] = None
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    decision: Optional[Dict[str, Any]] = None
    num_detections: int = 0
    alerts_triggered: int = 0
    ground_truth: Optional[Dict[str, Any]] = None
    image_filename: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SessionMetadata:
    """Metadata for a recorded session."""
    session_id: str
    start_time: str
    end_time: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    total_iterations: int = 0
    completed: bool = False
    confirmed_count: int = 0
    rejected_count: int = 0
    ground_truth_summary: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SessionRecorder:
    """
    Records marathon sessions for playback.
    
    Creates a session directory with structure:
    data/sessions/{session_id}/
        session.json          - Session metadata
        iterations/
            iteration_001.json
            iteration_002.json
            ...
        images/
            iteration_001.png
            iteration_002.png
            ...
    """
    
    def __init__(self, base_dir: str = "data/sessions"):
        """
        Initialize the session recorder.
        
        Args:
            base_dir: Base directory for storing sessions
        """
        self.base_dir = Path(base_dir)
        self.session_id: Optional[str] = None
        self.session_dir: Optional[Path] = None
        self.metadata: Optional[SessionMetadata] = None
        self._iterations: List[IterationData] = []
    
    def start_session(self, config: Optional[Dict[str, Any]] = None) -> str:
        """
        Start a new recording session.
        
        Args:
            config: Marathon configuration used for this session
            
        Returns:
            Session ID
        """
        # Generate unique session ID from timestamp (includes microseconds to prevent collisions)
        now = datetime.now()
        self.session_id = f"session_{now.strftime('%Y%m%d_%H%M%S_%f')}"
        
        # Create session directory structure
        self.session_dir = self.base_dir / self.session_id
        (self.session_dir / "iterations").mkdir(parents=True, exist_ok=True)
        (self.session_dir / "images").mkdir(parents=True, exist_ok=True)
        
        # Initialize metadata
        self.metadata = SessionMetadata(
            session_id=self.session_id,
            start_time=now.isoformat(),
            config=config,
        )
        
        # Clear iterations list
        self._iterations = []
        
        logger.info(f"Started recording session: {self.session_id}")
        return self.session_id
    
    def record_iteration(
        self,
        iteration: int,
        context_state: Dict[str, Any],
        source_image_path: Optional[str] = None,
    ) -> None:
        """
        Record data for a single iteration.
        
        Args:
            iteration: Iteration number (1-based)
            context_state: Current context state from OODA loop
            source_image_path: Path to the iteration image to copy
        """
        if not self.session_dir:
            logger.warning("No active session, cannot record iteration")
            return
        
        # Prepare iteration data
        iteration_data = IterationData(
            iteration=iteration,
            timestamp=datetime.now().isoformat(),
            simulated_time=context_state.get("simulated_time"),
            weather=context_state.get("weather"),
            candidates=context_state.get("candidates", []),
            decision=context_state.get("decision"),
            num_detections=context_state.get("num_detections", 0),
            alerts_triggered=context_state.get("alerts_triggered", 0),
            ground_truth=context_state.get("ground_truth"),
        )
        
        # Copy image if available
        if source_image_path:
            source_path = Path(source_image_path)
            if source_path.exists():
                image_filename = f"iteration_{iteration:03d}.png"
                dest_path = self.session_dir / "images" / image_filename
                shutil.copy2(source_path, dest_path)
                iteration_data.image_filename = image_filename
                logger.debug(f"Copied image to {dest_path}")
        
        # Save iteration data to JSON
        iteration_file = self.session_dir / "iterations" / f"iteration_{iteration:03d}.json"
        with open(iteration_file, "w") as f:
            json.dump(iteration_data.to_dict(), f, indent=2)
        
        self._iterations.append(iteration_data)
        logger.debug(f"Recorded iteration {iteration}")
    
    def finalize_session(
        self,
        ground_truth_summary: Optional[Dict[str, Any]] = None,
    ) -> SessionMetadata:
        """
        Finalize and save the session.
        
        Args:
            ground_truth_summary: Final ground truth metrics
            
        Returns:
            Final session metadata
        """
        if not self.session_dir or not self.metadata:
            logger.warning("No active session to finalize")
            return SessionMetadata(session_id="", start_time="")
        
        # Calculate summary statistics
        confirmed_count = 0
        rejected_count = 0
        
        for iteration in self._iterations:
            for candidate in iteration.candidates:
                status = candidate.get("status", "").upper()
                if status in ("BRIGHTENING", "ALERTED"):
                    confirmed_count += 1
                elif status == "REJECTED":
                    rejected_count += 1
        
        # Update metadata
        self.metadata.end_time = datetime.now().isoformat()
        self.metadata.total_iterations = len(self._iterations)
        self.metadata.completed = True
        self.metadata.confirmed_count = confirmed_count
        self.metadata.rejected_count = rejected_count
        self.metadata.ground_truth_summary = ground_truth_summary
        
        # Save session metadata
        session_file = self.session_dir / "session.json"
        with open(session_file, "w") as f:
            json.dump(self.metadata.to_dict(), f, indent=2)
        
        logger.info(
            f"Finalized session {self.session_id}: "
            f"{self.metadata.total_iterations} iterations, "
            f"{confirmed_count} confirmed"
        )
        
        return self.metadata
    
    @classmethod
    def list_sessions(cls, base_dir: str = "data/sessions") -> List[Dict[str, Any]]:
        """
        List all recorded sessions.
        
        Args:
            base_dir: Base directory for sessions
            
        Returns:
            List of session metadata dictionaries
        """
        sessions_dir = Path(base_dir)
        if not sessions_dir.exists():
            return []
        
        sessions = []
        for session_dir in sorted(sessions_dir.iterdir(), reverse=True):
            if not session_dir.is_dir():
                continue
            
            session_file = session_dir / "session.json"
            if session_file.exists():
                try:
                    with open(session_file) as f:
                        metadata = json.load(f)
                        sessions.append(metadata)
                except Exception as e:
                    logger.warning(f"Failed to load session {session_dir}: {e}")
        
        return sessions
    
    @classmethod
    def get_session(cls, session_id: str, base_dir: str = "data/sessions") -> Optional[Dict[str, Any]]:
        """
        Get session metadata by ID.
        
        Args:
            session_id: The session ID
            base_dir: Base directory for sessions
            
        Returns:
            Session metadata or None if not found
        """
        session_file = Path(base_dir) / session_id / "session.json"
        if not session_file.exists():
            return None
        
        with open(session_file) as f:
            return json.load(f)
    
    @classmethod
    def get_iteration(
        cls,
        session_id: str,
        iteration: int,
        base_dir: str = "data/sessions",
    ) -> Optional[Dict[str, Any]]:
        """
        Get iteration data for a session.
        
        Args:
            session_id: The session ID
            iteration: Iteration number (1-based)
            base_dir: Base directory for sessions
            
        Returns:
            Iteration data or None if not found
        """
        iteration_file = (
            Path(base_dir) / session_id / "iterations" / f"iteration_{iteration:03d}.json"
        )
        if not iteration_file.exists():
            return None
        
        with open(iteration_file) as f:
            return json.load(f)
    
    @classmethod
    def get_image_path(
        cls,
        session_id: str,
        iteration: int,
        base_dir: str = "data/sessions",
    ) -> Optional[Path]:
        """
        Get path to iteration image.
        
        Args:
            session_id: The session ID
            iteration: Iteration number (1-based)
            base_dir: Base directory for sessions
            
        Returns:
            Path to image or None if not found
        """
        image_path = (
            Path(base_dir) / session_id / "images" / f"iteration_{iteration:03d}.png"
        )
        return image_path if image_path.exists() else None
