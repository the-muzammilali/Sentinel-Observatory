"""
Scripted Regime Marathon for demonstrating all agent capabilities.

Provides a pre-scripted 30-60 minute real-time marathon with deliberate
regime phases to showcase all agent behaviors in a reproducible format.

Phases:
1. QUIET - No events, agent should correctly WAIT
2. FALSE_POSITIVE_CLUSTER - Artifacts to detect and reject
3. WEATHER_DEGRADATION - Bad weather, agent should wait
4. WEATHER_RECOVERY - Clear + delayed transient detection
5. COMPETING_CANDIDATES - Multiple candidates to prioritize
6. CONFIRMATION - Alert trigger and victory lap
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Optional, Callable, Any
import logging

from .ground_truth import GroundTruthTracker, TransientType, EvaluationMetrics
from .scenarios import RegimePhase

logger = logging.getLogger(__name__)


class MarathonPhase(Enum):
    """Marathon phase types (more detailed than RegimePhase)."""
    QUIET = "quiet"
    FALSE_POSITIVE_CLUSTER = "false_positive_cluster"
    WEATHER_DEGRADATION = "weather_degradation"
    WEATHER_RECOVERY = "weather_recovery"
    COMPETING_CANDIDATES = "competing_candidates"
    CONFIRMATION = "confirmation"
    COMPLETE = "complete"


@dataclass
class PhaseConfig:
    """Configuration for a marathon phase."""
    
    phase_type: MarathonPhase
    duration_hours: float  # Simulated time duration
    
    # Weather settings
    cloud_range: tuple = (0.0, 0.2)
    seeing_range: tuple = (1.0, 1.5)
    
    # Event injection
    inject_transients: int = 0
    inject_artifacts: int = 0
    
    # Expected agent behavior
    expected_action: Optional[str] = None  # "wait", "observe", "alert"
    
    # Description for narration
    description: str = ""
    narration: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "phase_type": self.phase_type.value,
            "duration_hours": self.duration_hours,
            "cloud_range": self.cloud_range,
            "seeing_range": self.seeing_range,
            "inject_transients": self.inject_transients,
            "inject_artifacts": self.inject_artifacts,
            "expected_action": self.expected_action,
            "description": self.description,
            "narration": self.narration
        }


@dataclass
class MarathonResult:
    """Result of a completed marathon."""
    
    total_iterations: int
    total_duration_hours: float
    
    # Phase results
    phases_completed: int
    current_phase: str
    
    # Performance metrics
    metrics: EvaluationMetrics = field(default_factory=EvaluationMetrics)
    
    # Scoring
    score: float = 0.0
    
    # Timeline
    events_log: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "total_iterations": self.total_iterations,
            "total_duration_hours": self.total_duration_hours,
            "phases_completed": self.phases_completed,
            "current_phase": self.current_phase,
            "metrics": self.metrics.to_dict(),
            "score": self.score,
            "events_count": len(self.events_log)
        }


# Pre-built marathon configurations

STANDARD_MARATHON = [
    PhaseConfig(
        phase_type=MarathonPhase.QUIET,
        duration_hours=2.0,
        cloud_range=(0.0, 0.1),
        seeing_range=(1.0, 1.2),
        expected_action="wait",
        description="Quiet baseline - no events",
        narration="The night is calm. Agent correctly waits for activity."
    ),
    PhaseConfig(
        phase_type=MarathonPhase.FALSE_POSITIVE_CLUSTER,
        duration_hours=2.0,
        cloud_range=(0.1, 0.2),
        seeing_range=(1.2, 1.5),
        inject_artifacts=3,
        expected_action="observe",
        description="False positive cluster - 3 artifacts",
        narration="Cosmic rays, satellite streaks appear. Agent investigates and rejects."
    ),
    PhaseConfig(
        phase_type=MarathonPhase.WEATHER_DEGRADATION,
        duration_hours=1.0,
        cloud_range=(0.5, 0.8),
        seeing_range=(2.0, 3.0),
        inject_transients=1,  # Real transient starts during bad weather
        expected_action="wait",
        description="Weather degradation + hidden transient",
        narration="Clouds roll in. A real supernova appears but is obscured."
    ),
    PhaseConfig(
        phase_type=MarathonPhase.WEATHER_RECOVERY,
        duration_hours=2.0,
        cloud_range=(0.0, 0.2),
        seeing_range=(1.0, 1.5),
        expected_action="observe",
        description="Weather clears - delayed transient detection",
        narration="Skies clear. Agent detects the rising supernova."
    ),
    PhaseConfig(
        phase_type=MarathonPhase.COMPETING_CANDIDATES,
        duration_hours=2.0,
        cloud_range=(0.1, 0.3),
        seeing_range=(1.2, 1.8),
        inject_transients=1,
        inject_artifacts=2,
        expected_action="observe",
        description="Competing candidates - prioritization test",
        narration="Multiple signals compete. Agent must prioritize wisely."
    ),
    PhaseConfig(
        phase_type=MarathonPhase.CONFIRMATION,
        duration_hours=1.0,
        cloud_range=(0.0, 0.1),
        seeing_range=(1.0, 1.2),
        expected_action="alert",
        description="Confirmation and alert",
        narration="Supernova confirmed! Agent triggers alert. Victory lap."
    )
]


class MarathonOrchestrator:
    """
    Orchestrates a scripted regime marathon.
    
    Manages phase transitions, ground truth tracking, and scoring
    for reproducible demonstration runs.
    """
    
    def __init__(
        self,
        phases: Optional[List[PhaseConfig]] = None,
        seed: int = 42
    ):
        """
        Initialize marathon orchestrator.
        
        Args:
            phases: List of phase configs (defaults to STANDARD_MARATHON)
            seed: Random seed for reproducibility
        """
        self.phases = phases or STANDARD_MARATHON.copy()
        self.seed = seed
        
        self.current_phase_idx = 0
        self.phase_start_time: Optional[datetime] = None
        self.marathon_start_time: Optional[datetime] = None
        
        self.ground_truth = GroundTruthTracker()
        self.iteration_count = 0
        
        self._events_log: List[Dict] = []
        self._is_complete = False
    
    @property
    def current_phase(self) -> PhaseConfig:
        """Get current phase configuration."""
        if self.current_phase_idx >= len(self.phases):
            return PhaseConfig(
                phase_type=MarathonPhase.COMPLETE,
                duration_hours=0,
                description="Marathon complete"
            )
        return self.phases[self.current_phase_idx]
    
    @property
    def is_complete(self) -> bool:
        """Check if marathon is complete."""
        return self._is_complete or self.current_phase_idx >= len(self.phases)
    
    def start(self, start_time: Optional[datetime] = None):
        """Start the marathon."""
        self.marathon_start_time = start_time or datetime.now()
        self.phase_start_time = self.marathon_start_time
        self.current_phase_idx = 0
        self.iteration_count = 0
        self._is_complete = False
        
        self._log_event("marathon_start", {
            "time": self.marathon_start_time.isoformat(),
            "total_phases": len(self.phases)
        })
        
        logger.info(
            f"Marathon started with {len(self.phases)} phases "
            f"(seed={self.seed})"
        )
    
    def tick(self, current_time: datetime) -> Dict:
        """
        Advance marathon state for a simulation tick.
        
        Args:
            current_time: Current simulated time
            
        Returns:
            Dict with current state and any injections needed
        """
        if self.is_complete:
            return {"phase": "complete", "inject": None}
        
        self.iteration_count += 1
        
        # Check for phase transition
        if self._should_transition(current_time):
            self._transition_to_next_phase(current_time)
        
        phase = self.current_phase
        
        return {
            "phase": phase.phase_type.value,
            "phase_idx": self.current_phase_idx,
            "cloud_range": phase.cloud_range,
            "seeing_range": phase.seeing_range,
            "inject_transients": phase.inject_transients,
            "inject_artifacts": phase.inject_artifacts,
            "description": phase.description,
            "narration": phase.narration,
            "iteration": self.iteration_count
        }
    
    def _should_transition(self, current_time: datetime) -> bool:
        """Check if we should transition to next phase."""
        if self.phase_start_time is None:
            return False
        
        phase = self.current_phase
        elapsed = (current_time - self.phase_start_time).total_seconds() / 3600
        
        return elapsed >= phase.duration_hours
    
    def _transition_to_next_phase(self, current_time: datetime):
        """Transition to the next phase."""
        old_phase = self.current_phase
        
        self._log_event("phase_complete", {
            "phase": old_phase.phase_type.value,
            "time": current_time.isoformat()
        })
        
        self.current_phase_idx += 1
        self.phase_start_time = current_time
        
        if not self.is_complete:
            new_phase = self.current_phase
            self._log_event("phase_start", {
                "phase": new_phase.phase_type.value,
                "time": current_time.isoformat()
            })
            logger.info(f"Phase transition: {new_phase.phase_type.value}")
        else:
            self._is_complete = True
            self._log_event("marathon_complete", {
                "time": current_time.isoformat(),
                "iterations": self.iteration_count
            })
            logger.info("Marathon complete!")
    
    def record_action(
        self,
        action: str,
        candidate_id: Optional[str] = None,
        ra: Optional[float] = None,
        dec: Optional[float] = None,
        time: Optional[datetime] = None
    ):
        """Record an agent action for scoring."""
        action_time = time or datetime.now()
        
        self._log_event("agent_action", {
            "action": action,
            "candidate_id": candidate_id,
            "time": action_time.isoformat()
        })
        
        # Track alerts in ground truth
        if action == "trigger_alert" and ra is not None and dec is not None:
            self.ground_truth.record_alert(
                candidate_id=candidate_id or "unknown",
                ra=ra,
                dec=dec,
                alert_time=action_time.isoformat()
            )
    
    def record_detection(
        self,
        candidate_id: str,
        ra: float,
        dec: float,
        time: Optional[datetime] = None
    ):
        """Record a detection for ground truth matching."""
        detection_time = time or datetime.now()
        self.ground_truth.record_detection(
            candidate_id=candidate_id,
            ra=ra,
            dec=dec,
            detection_time=detection_time.isoformat()
        )
    
    def finalize(self) -> MarathonResult:
        """Finalize marathon and compute results."""
        metrics = self.ground_truth.finalize_metrics()
        
        # Calculate overall score
        score = self._calculate_score(metrics)
        
        total_duration = 0.0
        if self.marathon_start_time:
            for phase in self.phases:
                total_duration += phase.duration_hours
        
        result = MarathonResult(
            total_iterations=self.iteration_count,
            total_duration_hours=total_duration,
            phases_completed=self.current_phase_idx,
            current_phase=self.current_phase.phase_type.value,
            metrics=metrics,
            score=score,
            events_log=self._events_log.copy()
        )
        
        return result
    
    def _calculate_score(self, metrics: EvaluationMetrics) -> float:
        """
        Calculate overall marathon score.
        
        Scoring formula:
        - Base: F1 score (0-100 points)
        - Latency bonus: Up to 20 points for fast alerts
        - False positive penalty: -5 per FP
        """
        # Base score from F1
        score = metrics.f1_score * 100
        
        # Latency bonus (20 points for < 1 hour average)
        if metrics.mean_latency_hours > 0:
            latency_bonus = max(0, 20 - metrics.mean_latency_hours * 10)
            score += latency_bonus
        
        # False positive penalty
        score -= metrics.false_positives * 5
        
        return max(0, round(score, 1))
    
    def _log_event(self, event_type: str, data: Dict):
        """Log an event to the timeline."""
        self._events_log.append({
            "type": event_type,
            "iteration": self.iteration_count,
            **data
        })
    
    def get_status(self) -> Dict:
        """Get current marathon status."""
        return {
            "phase_idx": self.current_phase_idx,
            "phase": self.current_phase.phase_type.value,
            "phase_description": self.current_phase.description,
            "narration": self.current_phase.narration,
            "iteration": self.iteration_count,
            "is_complete": self.is_complete,
            "total_phases": len(self.phases)
        }
    
    def get_progress(self) -> float:
        """Get marathon progress as percentage."""
        if len(self.phases) == 0:
            return 100.0
        return (self.current_phase_idx / len(self.phases)) * 100


# Convenience functions for common marathon types

def create_standard_marathon(seed: int = 42) -> MarathonOrchestrator:
    """Create standard 6-phase marathon."""
    return MarathonOrchestrator(phases=STANDARD_MARATHON, seed=seed)


def create_quick_demo(seed: int = 42) -> MarathonOrchestrator:
    """Create quick 3-phase demo marathon."""
    quick_phases = [
        PhaseConfig(
            phase_type=MarathonPhase.QUIET,
            duration_hours=0.5,
            description="Brief quiet period",
            narration="Quick scan of the sky."
        ),
        PhaseConfig(
            phase_type=MarathonPhase.WEATHER_RECOVERY,
            duration_hours=1.0,
            inject_transients=1,
            description="Transient detection",
            narration="Supernova detected!"
        ),
        PhaseConfig(
            phase_type=MarathonPhase.CONFIRMATION,
            duration_hours=0.5,
            expected_action="alert",
            description="Alert trigger",
            narration="Alert triggered. Demo complete."
        )
    ]
    return MarathonOrchestrator(phases=quick_phases, seed=seed)
