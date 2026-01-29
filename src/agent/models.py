"""
Pydantic models for Gemini AI Agent structured I/O.

These models define the data structures used for:
- Agent memory/state persistence (ContextState)
- Transient candidate tracking (Candidate)
- Agent decision outputs (AgentDecision)
- Weather context (WeatherContext)
"""

from datetime import datetime
from typing import List, Literal, Optional, Tuple
from pydantic import BaseModel, Field, ConfigDict


class CandidateHistory(BaseModel):
    """Single observation entry for a transient candidate."""
    
    model_config = ConfigDict(extra="forbid")
    
    time: str = Field(
        ...,
        description="ISO timestamp of the observation"
    )
    magnitude: Optional[float] = Field(
        None,
        ge=10.0,
        le=25.0,
        description="Estimated magnitude (brightness), lower = brighter"
    )
    note: str = Field(
        default="",
        description="Observation notes or comments"
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Detection confidence (0.0-1.0)"
    )


class Candidate(BaseModel):
    """Tracked transient candidate with observation history."""
    
    model_config = ConfigDict(extra="forbid")
    
    id: str = Field(
        ...,
        pattern=r"^CAND_\d+$",
        description="Unique identifier (e.g., 'CAND_01')"
    )
    x: int = Field(
        ...,
        ge=0,
        description="Pixel X coordinate"
    )
    y: int = Field(
        ...,
        ge=0,
        description="Pixel Y coordinate"
    )
    first_detected: str = Field(
        ...,
        description="ISO timestamp of first detection"
    )
    last_observed: str = Field(
        ...,
        description="ISO timestamp of most recent observation"
    )
    history: List[CandidateHistory] = Field(
        default_factory=list,
        description="Timeline of observations"
    )
    status: Literal["NEW", "MONITORING", "CONFIRMED", "REJECTED"] = Field(
        default="NEW",
        description="Current tracking status"
    )
    hypothesis: Optional[str] = Field(
        None,
        description="Classification hypothesis (e.g., 'Type Ia Supernova')"
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Overall detection confidence (0.0-1.0)"
    )
    
    def add_observation(
        self,
        time: str,
        magnitude: Optional[float] = None,
        note: str = "",
        confidence: float = 0.5
    ) -> None:
        """Add a new observation to the candidate's history."""
        self.history.append(CandidateHistory(
            time=time,
            magnitude=magnitude,
            note=note,
            confidence=confidence
        ))
        self.last_observed = time
        
        # Auto-upgrade status based on observation count
        if len(self.history) >= 3 and self.status == "MONITORING":
            # Check for brightening pattern
            mags = [h.magnitude for h in self.history[-3:] if h.magnitude is not None]
            if len(mags) >= 2 and mags[-1] < mags[0]:  # Brightening (lower mag = brighter)
                self.status = "CONFIRMED"
        elif len(self.history) >= 2 and self.status == "NEW":
            self.status = "MONITORING"


class WeatherContext(BaseModel):
    """Current atmospheric conditions affecting observations."""
    
    model_config = ConfigDict(extra="forbid")
    
    seeing: float = Field(
        ...,
        ge=0.3,
        le=5.0,
        description="Atmospheric blur in arcseconds"
    )
    cloud_extinction: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Cloud opacity (0.0 = clear, 1.0 = opaque)"
    )
    observability: Literal["EXCELLENT", "GOOD", "POOR", "UNUSABLE"] = Field(
        default="GOOD",
        description="Overall observing conditions"
    )
    
    @classmethod
    def from_weather_system(cls, seeing: float, cloud_extinction: float) -> "WeatherContext":
        """Create from weather system values with automatic observability calculation."""
        if cloud_extinction > 0.6:
            observability = "UNUSABLE"
        elif cloud_extinction > 0.3 or seeing > 2.0:
            observability = "POOR"
        elif cloud_extinction > 0.1 or seeing > 1.2:
            observability = "GOOD"
        else:
            observability = "EXCELLENT"
        
        return cls(
            seeing=seeing,
            cloud_extinction=cloud_extinction,
            observability=observability
        )


class ContextState(BaseModel):
    """Complete agent state passed to Gemini each iteration.
    
    This implements the "Thought Signature" pattern for memory persistence.
    """
    
    model_config = ConfigDict(extra="forbid")
    
    iteration: int = Field(
        ...,
        ge=1,
        description="Current iteration number (1-indexed)"
    )
    simulated_time: str = Field(
        ...,
        description="Current simulated time (ISO format)"
    )
    current_focus: str = Field(
        default="Field_Primary",
        description="Current field identifier being observed"
    )
    weather: WeatherContext = Field(
        ...,
        description="Current atmospheric conditions"
    )
    candidates: List[Candidate] = Field(
        default_factory=list,
        description="All tracked transient candidates"
    )
    alerts_triggered: int = Field(
        default=0,
        ge=0,
        description="Total alerts triggered this session"
    )
    last_action_reasoning: str = Field(
        default="Initial observation - no previous actions",
        description="Reasoning from the previous decision"
    )
    total_observations: int = Field(
        default=0,
        ge=0,
        description="Total observations made this session"
    )
    
    def get_active_candidates(self) -> List[Candidate]:
        """Return only non-rejected candidates."""
        return [c for c in self.candidates if c.status != "REJECTED"]
    
    def get_candidate_by_id(self, candidate_id: str) -> Optional[Candidate]:
        """Find a candidate by its ID."""
        for c in self.candidates:
            if c.id == candidate_id:
                return c
        return None
    
    def next_candidate_id(self) -> str:
        """Generate the next available candidate ID."""
        if not self.candidates:
            return "CAND_01"
        max_num = max(int(c.id.split("_")[1]) for c in self.candidates)
        return f"CAND_{max_num + 1:02d}"


class AgentDecision(BaseModel):
    """Structured output from the Gemini agent.
    
    This is the expected response format that Gemini must produce.
    """
    
    model_config = ConfigDict(extra="forbid")
    
    action: Literal["observe_again", "slew_to", "trigger_alert", "wait"] = Field(
        ...,
        description="The decided action to take"
    )
    target_coordinates: Optional[Tuple[float, float]] = Field(
        None,
        description="Target (x, y) coordinates for slew_to action"
    )
    reasoning: str = Field(
        ...,
        min_length=10,
        description="Detailed explanation for the decision"
    )
    updated_candidates: List[Candidate] = Field(
        default_factory=list,
        description="Updated candidate list with any status changes"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Decision confidence (0.0-1.0)"
    )
    thought_signature_update: str = Field(
        default="",
        description="Summary note for the next iteration's context"
    )
    new_detections: int = Field(
        default=0,
        ge=0,
        description="Number of new candidates detected this iteration"
    )
    
    def validate_slew_action(self) -> bool:
        """Validate that slew_to action has coordinates."""
        if self.action == "slew_to" and self.target_coordinates is None:
            return False
        return True


# Default decision for error fallback
def create_default_wait_decision(reason: str = "Agent fallback - API error") -> AgentDecision:
    """Create a safe default wait decision for error handling."""
    return AgentDecision(
        action="wait",
        target_coordinates=None,
        reasoning=reason,
        updated_candidates=[],
        confidence=0.1,
        thought_signature_update="Fallback action due to processing error",
        new_detections=0
    )


# Utility function to create initial context
def create_initial_context(
    simulated_time: str,
    weather: WeatherContext
) -> ContextState:
    """Create a fresh context for the first iteration."""
    return ContextState(
        iteration=1,
        simulated_time=simulated_time,
        current_focus="Field_Primary",
        weather=weather,
        candidates=[],
        alerts_triggered=0,
        last_action_reasoning="Initial observation - starting marathon",
        total_observations=0
    )
