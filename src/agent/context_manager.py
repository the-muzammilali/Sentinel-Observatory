"""
Context Manager for Sentinel Agent state persistence.

Handles:
- State initialization
- State updates between iterations
- JSON serialization/deserialization
- History compression for long marathons
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from .models import (
    ContextState,
    AgentDecision,
    Candidate,
    CandidateHistory,
    WeatherContext,
    create_initial_context
)

logger = logging.getLogger(__name__)


class ContextManager:
    """
    Manages agent state persistence across iterations.
    
    The ContextManager implements the "Thought Signature" pattern where
    all agent memory is explicitly passed between iterations rather than
    relying on implicit conversation history.
    
    Attributes:
        state_dir: Directory for saving state JSON files
        max_history_per_candidate: Maximum observations to keep per candidate
    """
    
    def __init__(
        self,
        state_dir: str = "data/agent_state",
        max_history_per_candidate: int = 20
    ):
        """
        Initialize the ContextManager.
        
        Args:
            state_dir: Directory to save/load state files
            max_history_per_candidate: Max observations per candidate before compression
        """
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.max_history_per_candidate = max_history_per_candidate
        
        logger.info(f"ContextManager initialized with state_dir: {self.state_dir}")
    
    def initialize_context(
        self,
        simulated_time: str,
        weather: WeatherContext,
        field_focus: str = "Field_Primary"
    ) -> ContextState:
        """
        Create a fresh context for the first iteration.
        
        Args:
            simulated_time: Starting simulated time (ISO format)
            weather: Initial weather conditions
            field_focus: Initial field identifier
        
        Returns:
            Fresh ContextState for iteration 1
        """
        context = ContextState(
            iteration=1,
            simulated_time=simulated_time,
            current_focus=field_focus,
            weather=weather,
            candidates=[],
            alerts_triggered=0,
            last_action_reasoning="Starting observation marathon",
            total_observations=0
        )
        
        logger.info(f"Initialized new context for time: {simulated_time}")
        return context
    
    def update_context(
        self,
        old_context: ContextState,
        decision: AgentDecision,
        new_weather: WeatherContext,
        new_simulated_time: str
    ) -> ContextState:
        """
        Apply an agent decision to evolve the context state.
        
        This is called after each iteration to:
        - Increment iteration counter
        - Update weather conditions
        - Merge candidate updates from the decision
        - Update action history
        
        Args:
            old_context: Previous iteration's context
            decision: Agent's decision from this iteration
            new_weather: Updated weather conditions
            new_simulated_time: New simulated time after time step
        
        Returns:
            Updated ContextState for the next iteration
        """
        # Merge candidates: start with agent's updates, add any missing from old context
        merged_candidates = self._merge_candidates(
            old_candidates=old_context.candidates,
            updated_candidates=decision.updated_candidates
        )
        
        # Compress history if needed
        for candidate in merged_candidates:
            if len(candidate.history) > self.max_history_per_candidate:
                candidate.history = self._compress_history(candidate.history)
        
        # Determine new focus field
        new_focus = old_context.current_focus
        if decision.action == "slew_to" and decision.target_coordinates:
            new_focus = f"Field_{decision.target_coordinates[0]:.0f}_{decision.target_coordinates[1]:.0f}"
        
        # Count alerts
        alerts = old_context.alerts_triggered
        if decision.action == "trigger_alert":
            alerts += 1
        
        # Create new context
        new_context = ContextState(
            iteration=old_context.iteration + 1,
            simulated_time=new_simulated_time,
            current_focus=new_focus,
            weather=new_weather,
            candidates=merged_candidates,
            alerts_triggered=alerts,
            last_action_reasoning=decision.reasoning,
            total_observations=old_context.total_observations + 1
        )
        
        logger.info(
            f"Context updated: iteration {old_context.iteration} → {new_context.iteration}, "
            f"candidates: {len(merged_candidates)}, alerts: {alerts}"
        )
        
        return new_context
    
    def _merge_candidates(
        self,
        old_candidates: List[Candidate],
        updated_candidates: List[Candidate]
    ) -> List[Candidate]:
        """
        Merge old and updated candidate lists.
        
        Priority:
        1. Candidates in updated_candidates replace old ones with same ID
        2. Old candidates not in updated list are preserved (unless rejected)
        3. New candidates in updated list are added
        
        Args:
            old_candidates: Previous candidate list
            updated_candidates: Candidates from agent decision
        
        Returns:
            Merged candidate list
        """
        # Build lookup of updated candidates by ID
        updated_lookup = {c.id: c for c in updated_candidates}
        
        # Start with updated candidates
        merged = list(updated_candidates)
        
        # Add old candidates not in updated list (if not rejected)
        for old_c in old_candidates:
            if old_c.id not in updated_lookup:
                # Preserve if not explicitly rejected
                if old_c.status != "REJECTED":
                    merged.append(old_c)
        
        return merged
    
    def _compress_history(
        self,
        history: List[CandidateHistory]
    ) -> List[CandidateHistory]:
        """
        Compress candidate history to save tokens in the prompt.
        
        Strategy:
        - Keep first observation (important for classification)
        - Keep last N observations (recent data)
        - Summarize middle observations
        
        Args:
            history: Full observation history
        
        Returns:
            Compressed history list
        """
        if len(history) <= self.max_history_per_candidate // 2:
            return history
        
        # Keep first 2 and last 8 observations
        keep_first = 2
        keep_last = self.max_history_per_candidate // 2 - keep_first
        
        compressed = history[:keep_first] + history[-keep_last:]
        
        # Add a note about compression
        if keep_first < len(history):
            compressed[keep_first - 1] = CandidateHistory(
                time=compressed[keep_first - 1].time,
                magnitude=compressed[keep_first - 1].magnitude,
                note=f"[{len(history) - keep_first - keep_last} observations compressed]",
                confidence=compressed[keep_first - 1].confidence
            )
        
        return compressed
    
    def save_context(
        self,
        context: ContextState,
        filename: Optional[str] = None
    ) -> Path:
        """
        Serialize context to JSON file.
        
        Args:
            context: Context state to save
            filename: Optional filename. Defaults to iter_{N:03d}.json
        
        Returns:
            Path to the saved file
        """
        if filename is None:
            filename = f"iter_{context.iteration:03d}.json"
        
        filepath = self.state_dir / filename
        
        # Serialize to JSON
        with open(filepath, 'w') as f:
            json.dump(context.model_dump(), f, indent=2, default=str)
        
        logger.debug(f"Saved context to {filepath}")
        return filepath
    
    def load_context(self, filename: str) -> ContextState:
        """
        Deserialize context from JSON file.
        
        Args:
            filename: Name of the file to load (relative to state_dir)
        
        Returns:
            Loaded ContextState
        """
        filepath = self.state_dir / filename
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        context = ContextState.model_validate(data)
        logger.debug(f"Loaded context from {filepath}")
        return context
    
    def load_latest_context(self) -> Optional[ContextState]:
        """
        Load the most recent context file.
        
        Returns:
            Latest ContextState or None if no files exist
        """
        json_files = sorted(self.state_dir.glob("iter_*.json"))
        
        if not json_files:
            logger.info("No existing context files found")
            return None
        
        latest = json_files[-1]
        return self.load_context(latest.name)
    
    def clear_state(self) -> None:
        """Remove all saved state files (for fresh restart)."""
        for filepath in self.state_dir.glob("iter_*.json"):
            filepath.unlink()
        logger.info(f"Cleared all state files from {self.state_dir}")
    
    def get_session_summary(self) -> dict:
        """
        Generate a summary of the current marathon session.
        
        Returns:
            Dictionary with session statistics
        """
        json_files = sorted(self.state_dir.glob("iter_*.json"))
        
        if not json_files:
            return {"status": "no_session", "iterations": 0}
        
        # Load first and last contexts
        first = self.load_context(json_files[0].name)
        latest = self.load_context(json_files[-1].name)
        
        return {
            "status": "active",
            "total_iterations": len(json_files),
            "current_iteration": latest.iteration,
            "start_time": first.simulated_time,
            "current_time": latest.simulated_time,
            "total_candidates": len(latest.candidates),
            "confirmed_candidates": len([c for c in latest.candidates if c.status in ("BRIGHTENING", "ALERTED")]),
            "alerts_triggered": latest.alerts_triggered,
            "total_observations": latest.total_observations
        }


def create_context_manager(
    state_dir: str = "data/agent_state"
) -> ContextManager:
    """
    Factory function to create a ContextManager.
    
    Args:
        state_dir: Directory for state files
    
    Returns:
        Configured ContextManager instance
    """
    return ContextManager(state_dir=state_dir)
