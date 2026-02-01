"""
Ground truth tracking for honest evaluation of agent performance.

Maintains hidden ground truth throughout the marathon and computes:
- True positives: Correctly detected real transients
- False positives: Alerts on non-transients
- Alert latency: Time from transient appearance to alert

Provides optional demo toggle to reveal truth for demonstrations.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TransientType(Enum):
    """Types of transient events."""
    SN_IA = "SN_Ia"
    SN_II = "SN_II"
    CV = "CV"
    NOVA = "nova"
    ASTEROID = "asteroid"
    GAMMA_RAY_BURST = "GRB"
    UNKNOWN = "unknown"


@dataclass
class GroundTruthEvent:
    """
    A known transient event (hidden from agent).
    
    This is the "answer key" that the agent never sees.
    """
    
    id: str
    event_type: TransientType
    ra: float
    dec: float
    
    # Timing
    appearance_time: str  # ISO timestamp when transient starts
    peak_time: Optional[str] = None  # When it reaches maximum brightness
    fade_time: Optional[str] = None  # When it becomes undetectable
    
    # Properties
    peak_magnitude: float = 18.0
    is_real_transient: bool = True  # False = artifact, cosmic ray, etc.
    
    # Tracking
    detected_by_agent: bool = False
    alert_triggered: bool = False
    alert_time: Optional[str] = None
    matched_candidate_id: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "ra": self.ra,
            "dec": self.dec,
            "appearance_time": self.appearance_time,
            "peak_time": self.peak_time,
            "fade_time": self.fade_time,
            "peak_magnitude": self.peak_magnitude,
            "is_real_transient": self.is_real_transient,
            "detected_by_agent": self.detected_by_agent,
            "alert_triggered": self.alert_triggered,
            "alert_time": self.alert_time,
            "matched_candidate_id": self.matched_candidate_id
        }


@dataclass
class EvaluationMetrics:
    """
    Performance metrics computed from ground truth.
    """
    
    # Detection metrics
    true_positives: int = 0  # Correctly triggered alerts on real transients
    false_positives: int = 0  # Alerts on non-transients
    false_negatives: int = 0  # Missed real transients (no alert)
    true_negatives: int = 0  # Correctly ignored non-transients
    
    # Latency metrics
    total_detections: int = 0
    total_latency_hours: float = 0.0
    min_latency_hours: float = float('inf')
    max_latency_hours: float = 0.0
    
    # Derived metrics
    @property
    def precision(self) -> float:
        """Fraction of alerts that were correct."""
        if self.true_positives + self.false_positives == 0:
            return 1.0
        return self.true_positives / (self.true_positives + self.false_positives)
    
    @property
    def recall(self) -> float:
        """Fraction of real transients that were alerted."""
        if self.true_positives + self.false_negatives == 0:
            return 1.0
        return self.true_positives / (self.true_positives + self.false_negatives)
    
    @property
    def f1_score(self) -> float:
        """Harmonic mean of precision and recall."""
        p, r = self.precision, self.recall
        if p + r == 0:
            return 0.0
        return 2 * (p * r) / (p + r)
    
    @property
    def mean_latency_hours(self) -> float:
        """Average time from appearance to alert."""
        if self.total_detections == 0:
            return 0.0
        return self.total_latency_hours / self.total_detections
    
    def to_dict(self) -> Dict:
        return {
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "true_negatives": self.true_negatives,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "mean_latency_hours": round(self.mean_latency_hours, 2),
            "min_latency_hours": round(self.min_latency_hours, 2) if self.min_latency_hours != float('inf') else None,
            "max_latency_hours": round(self.max_latency_hours, 2) if self.max_latency_hours > 0 else None
        }


class GroundTruthTracker:
    """
    Tracks hidden ground truth and evaluates agent performance.
    
    The agent never sees this data - it's the "answer key" used
    to objectively measure detection accuracy and latency.
    """
    
    # Position matching tolerance
    # NOTE: Coordinates are in arcseconds from field center
    # FOV is 10 arcsec, so 1 arcsec tolerance is ~10% of field
    MATCH_RADIUS_ARCSEC = 2.0  # arcsec tolerance for matching (accounts for centroid offset)
    
    def __init__(self, reveal_mode: bool = False):
        """
        Initialize ground truth tracker.
        
        Args:
            reveal_mode: If True, truth can be revealed for demos
        """
        self.events: Dict[str, GroundTruthEvent] = {}
        self.reveal_mode = reveal_mode
        self._next_id = 1
        self._metrics = EvaluationMetrics()
        self._alerts_by_candidate: Dict[str, str] = {}  # candidate_id -> event_id
    
    def add_event(
        self,
        event_type: TransientType,
        ra: float,
        dec: float,
        appearance_time: str,
        peak_magnitude: float = 18.0,
        is_real: bool = True,
        event_id: Optional[str] = None
    ) -> str:
        """
        Add a ground truth event.
        
        Args:
            event_type: Type of transient
            ra: Right ascension
            dec: Declination
            appearance_time: ISO timestamp
            peak_magnitude: Brightest magnitude
            is_real: True for real transients, False for artifacts
            event_id: Optional custom ID
            
        Returns:
            Event ID
        """
        if event_id is None:
            event_id = f"GT_{self._next_id:03d}"
            self._next_id += 1
        
        event = GroundTruthEvent(
            id=event_id,
            event_type=event_type,
            ra=ra,
            dec=dec,
            appearance_time=appearance_time,
            peak_magnitude=peak_magnitude,
            is_real_transient=is_real
        )
        
        self.events[event_id] = event
        logger.debug(f"Added ground truth event: {event_id} ({event_type.value})")
        
        return event_id
    
    def record_detection(
        self,
        candidate_id: str,
        ra: float,
        dec: float,
        detection_time: str
    ) -> Optional[str]:
        """
        Record that the agent detected something at a position.
        
        Args:
            candidate_id: Agent's candidate ID
            ra: Detected position RA
            dec: Detected position Dec
            detection_time: ISO timestamp
            
        Returns:
            Matched ground truth event ID, or None
        """
        for event_id, event in self.events.items():
            if self._positions_match(ra, dec, event.ra, event.dec):
                event.detected_by_agent = True
                event.matched_candidate_id = candidate_id
                return event_id
        
        return None
    
    def record_alert(
        self,
        candidate_id: str,
        ra: float,
        dec: float,
        alert_time: str
    ) -> bool:
        """
        Record that the agent triggered an alert.
        
        Args:
            candidate_id: Agent's candidate ID
            ra: Alert position RA
            dec: Alert position Dec
            alert_time: ISO timestamp
            
        Returns:
            True if alert was for a real transient (true positive)
        """
        for event_id, event in self.events.items():
            if self._positions_match(ra, dec, event.ra, event.dec):
                event.alert_triggered = True
                event.alert_time = alert_time
                self._alerts_by_candidate[candidate_id] = event_id
                
                if event.is_real_transient:
                    self._metrics.true_positives += 1
                    
                    # Calculate latency
                    try:
                        appear = datetime.fromisoformat(event.appearance_time)
                        alert = datetime.fromisoformat(alert_time)
                        latency = (alert - appear).total_seconds() / 3600
                        
                        self._metrics.total_detections += 1
                        self._metrics.total_latency_hours += latency
                        self._metrics.min_latency_hours = min(
                            self._metrics.min_latency_hours, latency
                        )
                        self._metrics.max_latency_hours = max(
                            self._metrics.max_latency_hours, latency
                        )
                    except (ValueError, TypeError):
                        pass
                    
                    logger.info(
                        f"TRUE POSITIVE: Alert on {event_id} "
                        f"({event.event_type.value})"
                    )
                    return True
                else:
                    self._metrics.false_positives += 1
                    logger.warning(
                        f"FALSE POSITIVE: Alert on non-transient {event_id}"
                    )
                    return False
        
        # Alert on unknown position - false positive
        self._metrics.false_positives += 1
        logger.warning(f"FALSE POSITIVE: Alert on unknown position")
        return False
    
    def finalize_metrics(self) -> EvaluationMetrics:
        """
        Compute final metrics at end of marathon.
        
        Call this after the simulation completes to count
        missed detections (false negatives).
        
        Returns:
            Complete evaluation metrics
        """
        for event in self.events.values():
            if event.is_real_transient and not event.alert_triggered:
                self._metrics.false_negatives += 1
            elif not event.is_real_transient and not event.alert_triggered:
                self._metrics.true_negatives += 1
        
        return self._metrics
    
    def get_metrics(self) -> EvaluationMetrics:
        """Get current metrics (may be incomplete during marathon)."""
        return self._metrics
    
    def reveal_truth(self) -> Optional[Dict]:
        """
        Reveal ground truth for demo mode.
        
        Returns:
            All ground truth events if reveal_mode is True, else None
        """
        if not self.reveal_mode:
            logger.warning("Attempted to reveal truth but reveal_mode is False")
            return None
        
        return {
            event_id: event.to_dict()
            for event_id, event in self.events.items()
        }
    
    def get_summary(self) -> Dict:
        """
        Get summary suitable for display.
        
        Does not reveal individual events unless in reveal mode.
        """
        metrics = self._metrics
        
        summary = {
            "total_events": len(self.events),
            "real_transients": sum(
                1 for e in self.events.values() if e.is_real_transient
            ),
            "artifacts": sum(
                1 for e in self.events.values() if not e.is_real_transient
            ),
            "metrics": metrics.to_dict(),
            "reveal_mode": self.reveal_mode
        }
        
        if self.reveal_mode:
            summary["events"] = self.reveal_truth()
        
        return summary
    
    def _positions_match(
        self,
        ra1: float, dec1: float,
        ra2: float, dec2: float
    ) -> bool:
        """Check if two positions are within matching radius."""
        return (
            abs(ra1 - ra2) <= self.MATCH_RADIUS_ARCSEC and
            abs(dec1 - dec2) <= self.MATCH_RADIUS_ARCSEC
        )
    
    def enable_reveal_mode(self):
        """Enable truth revelation for demos."""
        self.reveal_mode = True
        logger.info("Ground truth reveal mode ENABLED")
    
    def disable_reveal_mode(self):
        """Disable truth revelation."""
        self.reveal_mode = False
        logger.info("Ground truth reveal mode DISABLED")
