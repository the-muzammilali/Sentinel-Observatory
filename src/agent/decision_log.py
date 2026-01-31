"""
Decision logging for Project Sentinel agent.

Implements structured logging for all agent decisions, with special
emphasis on making WAIT (inaction) decisions visible as intelligent
restraint rather than silence.

This addresses the "Inaction Is a Decision" principle - judges should
see that the agent's restraint is deliberate and reasoned.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
import logging
import json

logger = logging.getLogger(__name__)


class WaitReason(Enum):
    """
    Structured reasons for WAIT decisions.
    
    Each reason explains why the agent chose inaction,
    making restraint visible as intelligent behavior.
    """
    
    # Observation-related
    INSUFFICIENT_PERSISTENCE = "Candidate needs more observations to confirm"
    PERSISTENCE_CHECK = "Waiting for mandatory persistence check interval"
    
    # Weather-related
    WEATHER_UNCERTAINTY = "Atmospheric conditions too poor for reliable observation"
    WEATHER_PREDICTED_IMPROVEMENT = "Waiting for predicted weather improvement"
    
    # Confidence-related
    CONFIDENCE_TOO_LOW = "Detection confidence below action threshold"
    CONFIDENCE_DECAYING = "Confidence dropping, waiting for stabilization"
    
    # Resource-related
    BUDGET_EXHAUSTED = "Follow-up observation budget depleted"
    COOLDOWN_PERIOD = "Mandatory cooldown between observations"
    
    # Strategic
    PRIORITIZATION = "Higher priority candidates require attention first"
    AWAITING_DATA = "Waiting for additional data from other sources"
    
    # Closure reasons
    NON_PERSISTENCE = "Candidate closed due to non-persistence"
    FALSE_POSITIVE_CONFIRMED = "Candidate closed as confirmed false positive"
    ARTIFACT_IDENTIFIED = "Candidate closed - identified as known artifact"


class ActionType(Enum):
    """Types of agent actions for logging."""
    
    WAIT = "wait"
    OBSERVE = "observe_again"
    SLEW = "slew_to"
    ALERT = "trigger_alert"
    CLOSE_CANDIDATE = "close_candidate"


@dataclass
class DecisionLogEntry:
    """
    Structured log entry for a single agent decision.
    
    Captures all context needed to understand why an action
    was taken (or not taken).
    """
    
    timestamp: str
    action: ActionType
    reason_type: WaitReason
    reason_detail: str
    candidate_id: Optional[str] = None
    confidence: float = 0.0
    weather_conditions: Optional[str] = None
    additional_context: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp,
            "action": self.action.value,
            "reason_type": self.reason_type.name,
            "reason_detail": self.reason_detail,
            "candidate_id": self.candidate_id,
            "confidence": round(self.confidence, 3),
            "weather_conditions": self.weather_conditions,
            "additional_context": self.additional_context
        }
    
    def to_human_readable(self) -> str:
        """Generate human-readable log message."""
        action_str = self.action.value.upper()
        
        if self.candidate_id:
            return f"[{self.timestamp}] {action_str} ({self.candidate_id}): {self.reason_detail}"
        return f"[{self.timestamp}] {action_str}: {self.reason_detail}"


@dataclass
class DecisionLogger:
    """
    Logs all agent decisions with structured reasoning.
    
    Provides methods for logging different decision types
    and retrieving decision history for analysis.
    """
    
    history: List[DecisionLogEntry] = field(default_factory=list)
    max_history: int = 1000  # Prevent unbounded growth
    
    def log_wait(
        self,
        reason: WaitReason,
        detail: str,
        candidate_id: Optional[str] = None,
        confidence: float = 0.0,
        weather: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> DecisionLogEntry:
        """
        Log a WAIT decision with explicit reasoning.
        
        This is the key method for surfacing restraint as
        intelligent behavior.
        
        Args:
            reason: Structured reason type
            detail: Human-readable explanation
            candidate_id: Associated candidate (if any)
            confidence: Current confidence level
            weather: Current weather conditions
            context: Additional context data
            
        Returns:
            The created log entry
        """
        entry = DecisionLogEntry(
            timestamp=datetime.now().isoformat(),
            action=ActionType.WAIT,
            reason_type=reason,
            reason_detail=detail,
            candidate_id=candidate_id,
            confidence=confidence,
            weather_conditions=weather,
            additional_context=context
        )
        
        self._add_entry(entry)
        logger.info(f"WAIT: {reason.name} - {detail}")
        
        return entry
    
    def log_action(
        self,
        action: ActionType,
        target: Optional[str] = None,
        detail: str = "",
        confidence: float = 0.0,
        context: Optional[Dict[str, Any]] = None
    ) -> DecisionLogEntry:
        """
        Log an active decision (OBSERVE, SLEW, ALERT).
        
        Args:
            action: The action type
            target: Target candidate or coordinates
            detail: Explanation for the action
            confidence: Decision confidence
            context: Additional context
            
        Returns:
            The created log entry
        """
        # Use a neutral reason for active decisions
        if action == ActionType.ALERT:
            reason = WaitReason.CONFIDENCE_TOO_LOW  # Placeholder
        else:
            reason = WaitReason.PERSISTENCE_CHECK  # Placeholder
        
        entry = DecisionLogEntry(
            timestamp=datetime.now().isoformat(),
            action=action,
            reason_type=reason,
            reason_detail=detail,
            candidate_id=target,
            confidence=confidence,
            additional_context=context
        )
        
        self._add_entry(entry)
        logger.info(f"{action.value.upper()}: {detail}")
        
        return entry
    
    def log_closure(
        self,
        candidate_id: str,
        reason: WaitReason,
        detail: str,
        final_confidence: float = 0.0
    ) -> DecisionLogEntry:
        """
        Log candidate closure with reasoning.
        
        Important for showing that closures are deliberate
        decisions, not oversights.
        
        Args:
            candidate_id: The closed candidate
            reason: Closure reason
            detail: Explanation
            final_confidence: Confidence at closure
            
        Returns:
            The created log entry
        """
        entry = DecisionLogEntry(
            timestamp=datetime.now().isoformat(),
            action=ActionType.CLOSE_CANDIDATE,
            reason_type=reason,
            reason_detail=detail,
            candidate_id=candidate_id,
            confidence=final_confidence
        )
        
        self._add_entry(entry)
        logger.info(f"CLOSED {candidate_id}: {reason.name} - {detail}")
        
        return entry
    
    def _add_entry(self, entry: DecisionLogEntry) -> None:
        """Add entry with history size management."""
        self.history.append(entry)
        
        # Trim if exceeds max
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
    
    def get_decision_history(
        self,
        action_filter: Optional[ActionType] = None,
        limit: int = 50
    ) -> List[DecisionLogEntry]:
        """
        Retrieve decision history with optional filtering.
        
        Args:
            action_filter: Filter by action type
            limit: Maximum entries to return
            
        Returns:
            List of matching log entries
        """
        entries = self.history
        
        if action_filter:
            entries = [e for e in entries if e.action == action_filter]
        
        return entries[-limit:]
    
    def get_wait_decisions(self, limit: int = 20) -> List[DecisionLogEntry]:
        """Get recent WAIT decisions specifically."""
        return self.get_decision_history(ActionType.WAIT, limit)
    
    def get_wait_summary(self) -> Dict[str, int]:
        """
        Summarize WAIT decisions by reason type.
        
        Useful for showing distribution of restraint reasons.
        """
        summary: Dict[str, int] = {}
        
        for entry in self.get_wait_decisions(limit=100):
            reason_name = entry.reason_type.name
            summary[reason_name] = summary.get(reason_name, 0) + 1
        
        return summary
    
    def to_json(self) -> str:
        """Serialize entire history to JSON."""
        return json.dumps(
            [e.to_dict() for e in self.history],
            indent=2
        )
    
    def clear(self) -> None:
        """Clear decision history."""
        self.history.clear()
