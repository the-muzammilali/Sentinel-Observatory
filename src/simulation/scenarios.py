"""
Regime-shift stress testing scenarios for Project Sentinel.

Implements structured multi-phase stress tests that validate
agent policy stability under changing operational conditions.

This tests not just system uptime, but how the agent handles
transitions between different observational regimes.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Dict, Any, Callable, Tuple
import logging

logger = logging.getLogger(__name__)


class RegimePhase(Enum):
    """
    Distinct operational phases for stress testing.
    
    Each phase presents different challenges to test
    agent policy stability.
    """
    
    # Baseline phases
    QUIET_BASELINE = "quiet_baseline"  # No events, tests patience
    
    # Challenge phases
    FALSE_POSITIVE_CLUSTER = "false_positive_cluster"  # Heavy FP bombardment
    DELAYED_TRANSIENT = "delayed_transient"  # Real event after long wait
    POST_ALERT_DECAY = "post_alert_decay"  # Recovery after alert
    
    # Environmental phases
    WEATHER_DISRUPTION = "weather_disruption"  # Rapid weather changes
    POOR_SEEING = "poor_seeing"  # Sustained poor conditions
    
    # Resource pressure phases
    MULTI_CANDIDATE = "multi_candidate"  # Many simultaneous candidates
    BUDGET_PRESSURE = "budget_pressure"  # Limited follow-up budget
    
    # Edge cases
    AMBIGUOUS_SIGNALS = "ambiguous_signals"  # Edge-case detections
    MIXED_REGIME = "mixed_regime"  # Multiple challenges at once


@dataclass
class ScenarioPhase:
    """
    Configuration for a single phase within a scenario.
    
    Defines what happens during this phase and for how long.
    """
    
    phase_type: RegimePhase
    duration_hours: float
    
    # Phase-specific configuration
    config: Dict[str, Any] = field(default_factory=dict)
    
    # Optional description for logging
    description: str = ""
    
    # Timing (set during execution)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    def get_duration(self) -> timedelta:
        """Get phase duration as timedelta."""
        return timedelta(hours=self.duration_hours)
    
    def is_active(self, current_time: datetime) -> bool:
        """Check if phase is currently active."""
        if self.start_time is None or self.end_time is None:
            return False
        return self.start_time <= current_time < self.end_time
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "phase_type": self.phase_type.value,
            "duration_hours": self.duration_hours,
            "description": self.description,
            "config": self.config,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None
        }


@dataclass
class ScenarioResult:
    """Results from running a scenario."""
    
    scenario_name: str
    total_duration_hours: float
    phases_completed: int
    total_phases: int
    
    # Metrics collected during run
    events_injected: int = 0
    alerts_triggered: int = 0
    candidates_opened: int = 0
    candidates_closed: int = 0
    
    # Phase transition log
    transitions: List[Tuple[str, str]] = field(default_factory=list)
    
    # Success indicators
    completed_successfully: bool = False
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "scenario_name": self.scenario_name,
            "total_duration_hours": self.total_duration_hours,
            "phases_completed": self.phases_completed,
            "total_phases": self.total_phases,
            "events_injected": self.events_injected,
            "alerts_triggered": self.alerts_triggered,
            "candidates_opened": self.candidates_opened,
            "candidates_closed": self.candidates_closed,
            "transitions": self.transitions,
            "completed_successfully": self.completed_successfully,
            "error_message": self.error_message
        }


@dataclass
class MarathonScenario:
    """
    Configures and runs a multi-phase stress test.
    
    Orchestrates transitions between phases and applies
    phase-specific configurations to the universe.
    """
    
    name: str
    phases: List[ScenarioPhase]
    description: str = ""
    
    # Current execution state
    current_phase_index: int = 0
    start_time: Optional[datetime] = None
    
    def __post_init__(self):
        """Validate scenario configuration."""
        if not self.phases:
            raise ValueError("Scenario must have at least one phase")
    
    def get_total_duration_hours(self) -> float:
        """Calculate total scenario duration."""
        return sum(phase.duration_hours for phase in self.phases)
    
    def get_current_phase(self) -> Optional[ScenarioPhase]:
        """Get the currently active phase."""
        if 0 <= self.current_phase_index < len(self.phases):
            return self.phases[self.current_phase_index]
        return None
    
    def initialize(self, start_time: datetime) -> None:
        """
        Initialize scenario with start time.
        
        Calculates all phase start/end times.
        """
        self.start_time = start_time
        self.current_phase_index = 0
        
        current = start_time
        for phase in self.phases:
            phase.start_time = current
            phase.end_time = current + phase.get_duration()
            current = phase.end_time
        
        logger.info(f"Initialized scenario '{self.name}' with {len(self.phases)} phases")
    
    def update(self, current_time: datetime) -> Optional[RegimePhase]:
        """
        Update scenario state based on current time.
        
        Returns the new phase type if a transition occurred.
        """
        if self.start_time is None:
            return None
        
        # Check if current phase has ended
        current_phase = self.get_current_phase()
        if current_phase is None:
            return None
        
        if current_time >= current_phase.end_time:
            # Advance to next phase
            self.current_phase_index += 1
            
            new_phase = self.get_current_phase()
            if new_phase:
                logger.info(f"Phase transition: {current_phase.phase_type.value} -> "
                           f"{new_phase.phase_type.value}")
                return new_phase.phase_type
            else:
                logger.info("Scenario completed - all phases finished")
                return None
        
        return None
    
    def is_complete(self) -> bool:
        """Check if scenario has completed all phases."""
        return self.current_phase_index >= len(self.phases)
    
    def get_phase_at_time(self, query_time: datetime) -> Optional[ScenarioPhase]:
        """Find which phase is active at a given time."""
        for phase in self.phases:
            if phase.is_active(query_time):
                return phase
        return None
    
    def get_phase_transitions(self) -> List[Tuple[str, datetime]]:
        """
        Get list of phase transitions with timestamps.
        
        Returns list of (phase_name, start_time) tuples.
        """
        transitions = []
        for phase in self.phases:
            if phase.start_time:
                transitions.append((
                    phase.phase_type.value,
                    phase.start_time
                ))
        return transitions
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "total_duration_hours": self.get_total_duration_hours(),
            "phases": [p.to_dict() for p in self.phases],
            "current_phase_index": self.current_phase_index,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "is_complete": self.is_complete()
        }


# =============================================================================
# Pre-built Stress Scenarios
# =============================================================================

def create_standard_marathon() -> MarathonScenario:
    """
    Standard 4-phase stress test.
    
    Phases:
    1. Quiet baseline (2h) - Tests patience
    2. False positive cluster (1h) - Tests skepticism
    3. Delayed real transient (2h) - Tests vigilance
    4. Post-alert decay (1h) - Tests recovery
    """
    return MarathonScenario(
        name="Standard Marathon",
        description="4-phase test of patience, skepticism, vigilance, and recovery",
        phases=[
            ScenarioPhase(
                phase_type=RegimePhase.QUIET_BASELINE,
                duration_hours=2.0,
                description="No events - testing agent patience",
                config={"inject_events": False}
            ),
            ScenarioPhase(
                phase_type=RegimePhase.FALSE_POSITIVE_CLUSTER,
                duration_hours=1.0,
                description="Heavy false positive bombardment",
                config={
                    "inject_artifacts": True,
                    "artifact_count": 5,
                    "artifact_types": ["satellite_trail", "cosmic_ray"]
                }
            ),
            ScenarioPhase(
                phase_type=RegimePhase.DELAYED_TRANSIENT,
                duration_hours=2.0,
                description="Real transient after long wait",
                config={
                    "inject_transient": True,
                    "transient_delay_hours": 1.5,
                    "transient_brightness": 18.0
                }
            ),
            ScenarioPhase(
                phase_type=RegimePhase.POST_ALERT_DECAY,
                duration_hours=1.0,
                description="Recovery phase after alert",
                config={"inject_events": False}
            )
        ]
    )


def create_false_positive_stress() -> MarathonScenario:
    """
    Intensive false positive stress test.
    
    Heavy bombardment of artifacts to test skepticism.
    """
    return MarathonScenario(
        name="False Positive Stress",
        description="Heavy artifact bombardment to test skepticism",
        phases=[
            ScenarioPhase(
                phase_type=RegimePhase.QUIET_BASELINE,
                duration_hours=0.5,
                description="Brief calm before storm",
                config={}
            ),
            ScenarioPhase(
                phase_type=RegimePhase.FALSE_POSITIVE_CLUSTER,
                duration_hours=2.0,
                description="Sustained false positive pressure",
                config={
                    "artifact_count": 10,
                    "artifact_interval_hours": 0.1
                }
            ),
            ScenarioPhase(
                phase_type=RegimePhase.DELAYED_TRANSIENT,
                duration_hours=1.0,
                description="Hidden real transient in noise",
                config={
                    "inject_transient": True,
                    "transient_brightness": 19.5  # Faint, harder to spot
                }
            )
        ]
    )


def create_weather_chaos() -> MarathonScenario:
    """
    Rapid weather transition stress test.
    
    Tests agent handling of changing observability.
    """
    return MarathonScenario(
        name="Weather Chaos",
        description="Rapid weather transitions testing adaptability",
        phases=[
            ScenarioPhase(
                phase_type=RegimePhase.QUIET_BASELINE,
                duration_hours=0.5,
                description="Clear skies, good seeing",
                config={"weather": "excellent"}
            ),
            ScenarioPhase(
                phase_type=RegimePhase.WEATHER_DISRUPTION,
                duration_hours=1.0,
                description="Clouds rolling in",
                config={"weather": "poor", "seeing": 3.0}
            ),
            ScenarioPhase(
                phase_type=RegimePhase.QUIET_BASELINE,
                duration_hours=0.5,
                description="Brief clearing",
                config={"weather": "good"}
            ),
            ScenarioPhase(
                phase_type=RegimePhase.POOR_SEEING,
                duration_hours=1.5,
                description="Sustained turbulence",
                config={"seeing": 4.0}
            ),
            ScenarioPhase(
                phase_type=RegimePhase.DELAYED_TRANSIENT,
                duration_hours=1.0,
                description="Transient during poor conditions",
                config={
                    "inject_transient": True,
                    "seeing": 2.5
                }
            )
        ]
    )


def create_multi_candidate_pressure() -> MarathonScenario:
    """
    Multiple competing candidates stress test.
    
    Tests prioritization under resource pressure.
    """
    return MarathonScenario(
        name="Multi-Candidate Pressure",
        description="Multiple simultaneous candidates testing prioritization",
        phases=[
            ScenarioPhase(
                phase_type=RegimePhase.MULTI_CANDIDATE,
                duration_hours=2.0,
                description="5 simultaneous faint candidates",
                config={
                    "candidate_count": 5,
                    "magnitude_range": (19.0, 21.0)
                }
            ),
            ScenarioPhase(
                phase_type=RegimePhase.BUDGET_PRESSURE,
                duration_hours=1.0,
                description="Limited follow-up budget",
                config={
                    "followup_budget": 3,
                    "candidate_count": 4
                }
            ),
            ScenarioPhase(
                phase_type=RegimePhase.DELAYED_TRANSIENT,
                duration_hours=1.0,
                description="Real transient among false positives",
                config={
                    "inject_transient": True,
                    "transient_brightness": 18.5,
                    "false_positives": 2
                }
            )
        ]
    )


# Scenario registry for easy access
SCENARIOS = {
    "standard": create_standard_marathon,
    "false_positive": create_false_positive_stress,
    "weather": create_weather_chaos,
    "multi_candidate": create_multi_candidate_pressure
}


def get_scenario(name: str) -> MarathonScenario:
    """
    Get a pre-built scenario by name.
    
    Args:
        name: Scenario name (standard, false_positive, weather, multi_candidate)
        
    Returns:
        Configured MarathonScenario instance
        
    Raises:
        KeyError: If scenario name not found
    """
    if name not in SCENARIOS:
        available = ", ".join(SCENARIOS.keys())
        raise KeyError(f"Unknown scenario '{name}'. Available: {available}")
    
    return SCENARIOS[name]()


def list_scenarios() -> List[str]:
    """List available scenario names."""
    return list(SCENARIOS.keys())
