"""
Confidence dynamics for transient candidate tracking.

Implements non-monotonic belief evolution with:
- Time-based decay (uncertainty grows without new evidence)
- Regression on conflicting data (null detections reduce confidence)
- Boost on confirming evidence
- Maximum confidence cap (prevents permanent certainty)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Tuple, Optional, Dict
import logging

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceDynamics:
    """
    Manages confidence evolution with realistic dynamics.
    
    Models scientific skepticism where:
    - Beliefs decay without continuous evidence
    - Conflicting data reduces confidence
    - Maximum confidence is capped (healthy uncertainty)
    """
    
    # Decay parameters
    decay_rate_per_hour: float = 0.05  # 5% decay per hour
    
    # Confidence bounds
    max_confidence: float = 0.95  # Never fully certain
    min_confidence: float = 0.05  # Never fully dismiss
    
    # Boost/regression factors
    confirming_boost_base: float = 0.15  # Base boost for confirming observation
    conflicting_penalty_base: float = 0.20  # Base penalty for null detection
    
    def apply_decay(
        self,
        confidence: float,
        hours_elapsed: float
    ) -> Tuple[float, str]:
        """
        Apply time-based decay to confidence.
        
        Decays exponentially: confidence * (1 - rate)^hours
        
        Args:
            confidence: Current confidence value
            hours_elapsed: Hours since last observation
            
        Returns:
            Tuple of (new_confidence, reason_string)
        """
        if hours_elapsed <= 0:
            return confidence, "no_decay"
        
        decay_factor = (1 - self.decay_rate_per_hour) ** hours_elapsed
        new_conf = confidence * decay_factor
        new_conf = max(self.min_confidence, new_conf)
        
        decay_amount = confidence - new_conf
        reason = f"decay_{decay_amount:.3f}_over_{hours_elapsed:.1f}h"
        
        logger.debug(f"Confidence decay: {confidence:.3f} -> {new_conf:.3f} "
                    f"({hours_elapsed:.1f}h elapsed)")
        
        return new_conf, reason
    
    def apply_boost(
        self,
        confidence: float,
        signal_strength: float = 1.0
    ) -> Tuple[float, str]:
        """
        Boost confidence on confirming observation.
        
        Boost is scaled by signal strength and diminishes as
        confidence approaches maximum.
        
        Args:
            confidence: Current confidence value
            signal_strength: Quality of detection (0.0-1.0)
            
        Returns:
            Tuple of (new_confidence, reason_string)
        """
        # Boost diminishes as we approach max (harder to get more certain)
        headroom = self.max_confidence - confidence
        boost = self.confirming_boost_base * signal_strength * (headroom / self.max_confidence)
        
        new_conf = min(self.max_confidence, confidence + boost)
        reason = f"boost_{boost:.3f}_signal_{signal_strength:.2f}"
        
        logger.debug(f"Confidence boost: {confidence:.3f} -> {new_conf:.3f} "
                    f"(signal={signal_strength:.2f})")
        
        return new_conf, reason
    
    def apply_regression(
        self,
        confidence: float,
        conflict_weight: float = 1.0
    ) -> Tuple[float, str]:
        """
        Apply regression on conflicting/null observation.
        
        Reduces confidence when expected signal is not found.
        
        Args:
            confidence: Current confidence value
            conflict_weight: Severity of conflict (0.0-1.0)
            
        Returns:
            Tuple of (new_confidence, reason_string)
        """
        penalty = self.conflicting_penalty_base * conflict_weight
        new_conf = max(self.min_confidence, confidence - penalty)
        
        reason = f"regression_{penalty:.3f}_conflict_{conflict_weight:.2f}"
        
        logger.debug(f"Confidence regression: {confidence:.3f} -> {new_conf:.3f} "
                    f"(conflict={conflict_weight:.2f})")
        
        return new_conf, reason
    
    def clamp(self, confidence: float) -> float:
        """Clamp confidence to valid bounds."""
        return max(self.min_confidence, min(self.max_confidence, confidence))


@dataclass
class ConfidenceTracker:
    """
    Tracks confidence history for a single candidate.
    
    Maintains a timeline of confidence changes with reasons
    for explainability.
    """
    
    initial_confidence: float = 0.5
    current_confidence: float = 0.5
    last_update_time: Optional[datetime] = None
    
    # History as (timestamp, confidence, reason) tuples
    history: List[Tuple[str, float, str]] = field(default_factory=list)
    
    dynamics: ConfidenceDynamics = field(default_factory=ConfidenceDynamics)
    
    def __post_init__(self):
        """Record initial state."""
        if not self.history:
            self.history.append(("init", self.initial_confidence, "initial"))
            self.current_confidence = self.initial_confidence
    
    def update(
        self,
        current_time: datetime,
        detection_result: str,  # "confirming", "conflicting", "null"
        signal_strength: float = 1.0
    ) -> float:
        """
        Update confidence based on observation result.
        
        Args:
            current_time: Current observation time
            detection_result: Type of observation result
            signal_strength: Quality of detection (0.0-1.0)
            
        Returns:
            New confidence value
        """
        # Apply time decay first
        if self.last_update_time is not None:
            hours = (current_time - self.last_update_time).total_seconds() / 3600
            if hours > 0:
                self.current_confidence, reason = self.dynamics.apply_decay(
                    self.current_confidence, hours
                )
                self.history.append((
                    current_time.isoformat(), self.current_confidence, reason
                ))
        
        # Apply observation effect
        if detection_result == "confirming":
            self.current_confidence, reason = self.dynamics.apply_boost(
                self.current_confidence, signal_strength
            )
        elif detection_result in ("conflicting", "null"):
            conflict_weight = 1.0 if detection_result == "conflicting" else 0.5
            self.current_confidence, reason = self.dynamics.apply_regression(
                self.current_confidence, conflict_weight
            )
        else:
            reason = "no_change"
        
        # Record update
        self.history.append((
            current_time.isoformat(), self.current_confidence, reason
        ))
        self.last_update_time = current_time
        
        return self.current_confidence
    
    def get_trend(self) -> str:
        """Analyze recent confidence trend."""
        if len(self.history) < 2:
            return "stable"
        
        recent = [h[1] for h in self.history[-5:]]
        if len(recent) < 2:
            return "stable"
        
        delta = recent[-1] - recent[0]
        if delta > 0.1:
            return "rising"
        elif delta < -0.1:
            return "falling"
        return "stable"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "current": round(self.current_confidence, 3),
            "initial": self.initial_confidence,
            "last_update": self.last_update_time.isoformat() if self.last_update_time else None,
            "trend": self.get_trend(),
            "history_length": len(self.history)
        }
