"""
UniverseController - Manages the "ground truth" of astronomical objects

This class maintains:
- Static star field (unchanging background)
- Dynamic transient events (supernovae, novae)
- Time progression
- Ground truth for validation
"""

import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TransientType(Enum):
    """Types of transient astronomical events"""
    SUPERNOVA_IA = "Supernova Type Ia"
    SUPERNOVA_II = "Supernova Type II"
    NOVA = "Nova"
    VARIABLE_STAR = "Variable Star"


class ArtifactType(Enum):
    """Types of false positive artifacts that should be rejected"""
    COSMIC_RAY = "Cosmic Ray"           # Single-frame spike, random location
    HOT_PIXEL = "Hot Pixel"             # Fixed location, persistent but not varying
    SATELLITE_STREAK = "Satellite"      # Linear streak across field
    DETECTOR_ARTIFACT = "Detector"      # Edge effects, readout patterns


@dataclass
class TransientEvent:
    """
    Represents a transient astronomical event with a time-varying light curve.
    
    The event follows a Gaussian brightness profile centered on peak_time:
    - Starts invisible at start_time
    - Reaches maximum brightness at peak_time
    - Returns to invisible at end_time
    """
    id: str
    x: float  # X position in arcseconds (field coordinates)
    y: float  # Y position in arcseconds
    start_time: datetime
    peak_time: datetime
    end_time: datetime
    base_magnitude: float  # Magnitude when invisible (e.g., 24.0 = very faint)
    peak_magnitude: float  # Magnitude at maximum brightness (e.g., 16.0 = bright)
    event_type: TransientType = TransientType.SUPERNOVA_IA
    
    def get_magnitude_at_time(self, current_time: datetime) -> float:
        """
        Calculate the current magnitude using a Gaussian light curve.
        
        Args:
            current_time: The time to calculate magnitude for
            
        Returns:
            Magnitude (lower = brighter). Returns base_magnitude if outside event window.
        """
        # Check if event is active
        if current_time < self.start_time or current_time > self.end_time:
            return self.base_magnitude
        
        # Calculate time relative to peak (in hours)
        time_from_peak = (current_time - self.peak_time).total_seconds() / 3600.0
        
        # Calculate width of Gaussian (standard deviation in hours)
        # Duration is the FWHM, so sigma = duration / (2 * sqrt(2*ln(2))) ≈ duration / 2.355
        duration_hours = (self.end_time - self.start_time).total_seconds() / 3600.0
        sigma = duration_hours / 2.355
        
        # Gaussian brightness variation (in magnitude space)
        # Magnitude is inverted (lower = brighter), so we subtract from base
        magnitude_amplitude = self.base_magnitude - self.peak_magnitude
        gaussian = np.exp(-0.5 * (time_from_peak / sigma) ** 2)
        
        current_magnitude = self.base_magnitude - (magnitude_amplitude * gaussian)
        
        return float(current_magnitude)
    
    def get_flux_at_time(self, current_time: datetime) -> float:
        """
        Calculate flux (not magnitude) for easier combination with stars.
        
        Flux ∝ 10^(-0.4 * magnitude)
        
        Args:
            current_time: The time to calculate flux for
            
        Returns:
            Relative flux (arbitrary units)
        """
        mag = self.get_magnitude_at_time(current_time)
        # Normalize so base_magnitude gives flux ≈ 0
        flux = 10 ** (-0.4 * (mag - self.base_magnitude))
        return float(flux)
    
    def is_active(self, current_time: datetime) -> bool:
        """Check if the transient is currently active (visible)"""
        return self.start_time <= current_time <= self.end_time


@dataclass
class Star:
    """Represents a static star"""
    x: float  # arcseconds
    y: float  # arcseconds
    magnitude: float


@dataclass
class ArtifactEvent:
    """
    False positive artifact with short-lived or non-physical behavior.
    
    Key differences from TransientEvent:
    - Very short duration (seconds, not hours)
    - Instant on/off profile (not Gaussian)
    - Should be rejected by the agent after investigation
    
    Used for testing agent's ability to distinguish real transients from noise.
    """
    id: str
    x: float  # X position in arcseconds
    y: float  # Y position in arcseconds
    artifact_time: datetime           # When it appears
    duration_seconds: float           # How long it lasts (very short)
    brightness_magnitude: float       # How bright it appears
    artifact_type: ArtifactType
    is_ground_truth_artifact: bool = True  # Always True - marks as false positive
    
    def is_visible(self, current_time: datetime) -> bool:
        """Check if artifact is visible at current time (instant on/off)"""
        end_time = self.artifact_time + timedelta(seconds=self.duration_seconds)
        return self.artifact_time <= current_time <= end_time
    
    def get_magnitude_at_time(self, current_time: datetime) -> float:
        """
        Non-Gaussian profile: instant brightness when visible, invisible otherwise.
        
        Unlike TransientEvent which has gradual brightening/dimming,
        artifacts appear and disappear instantly (like cosmic rays).
        """
        if self.is_visible(current_time):
            return self.brightness_magnitude
        return 99.0  # Completely invisible
    
    def get_flux_at_time(self, current_time: datetime) -> float:
        """Calculate flux for combination with other sources"""
        mag = self.get_magnitude_at_time(current_time)
        if mag > 30:  # Invisible
            return 0.0
        # Same flux calculation as TransientEvent
        base_mag = 24.0
        flux = 10 ** (-0.4 * (mag - base_mag))
        return float(flux)


@dataclass
class UniverseState:
    """
    Snapshot of the universe at a specific time.
    Used for generating observations and tracking ground truth.
    """
    current_time: datetime
    static_stars: List[Star]
    active_transients: List[TransientEvent]
    total_sources: int
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for logging/serialization"""
        return {
            "time": self.current_time.isoformat(),
            "num_stars": len(self.static_stars),
            "num_active_transients": len(self.active_transients),
            "total_sources": self.total_sources,
            "transients": [
                {
                    "id": t.id,
                    "type": t.event_type.value,
                    "magnitude": t.get_magnitude_at_time(self.current_time),
                    "position": (t.x, t.y)
                }
                for t in self.active_transients
            ]
        }


@dataclass
class FollowUpBudget:
    """
    Tracks agent resource constraints for follow-up observations.
    
    Creates prioritization pressure by limiting how many targets
    can be followed up within a given time window.
    """
    max_followups_per_hour: int = 2
    current_followups: int = 0
    window_start: Optional[datetime] = None
    
    def use_followup(self) -> bool:
        """
        Attempt to use a follow-up slot.
        
        Returns:
            True if follow-up was allowed, False if budget exhausted
        """
        if self.current_followups < self.max_followups_per_hour:
            self.current_followups += 1
            return True
        return False
    
    def reset(self, new_window_start: datetime) -> None:
        """Reset budget for a new time window"""
        self.current_followups = 0
        self.window_start = new_window_start
    
    def remaining(self) -> int:
        """Return number of remaining follow-up slots"""
        return max(0, self.max_followups_per_hour - self.current_followups)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for agent state"""
        return {
            "max_per_hour": self.max_followups_per_hour,
            "used": self.current_followups,
            "remaining": self.remaining(),
            "window_start": self.window_start.isoformat() if self.window_start else None
        }


@dataclass
class RandomizationConfig:
    """
    Configuration for bounded randomization of universe parameters.
    
    Allows controlled variance in transient properties while maintaining
    reproducibility through deterministic seeds.
    """
    # Transient timing variance
    start_time_jitter_hours: float = 0.5  # ±30 min from specified start
    duration_variance: float = 0.2  # ±20% of specified duration
    
    # Brightness variance
    magnitude_variance: float = 0.5  # ±0.5 mag from specified peak
    
    # Weather bounds
    seeing_range: Tuple[float, float] = (0.6, 2.0)
    cloud_range: Tuple[float, float] = (0.0, 0.5)
    
    # Reproducibility
    seed: Optional[int] = None
    
    def __post_init__(self):
        """Initialize RNG if seed provided"""
        if self.seed is not None:
            self._rng = np.random.default_rng(self.seed)
        else:
            self._rng = np.random.default_rng()
    
    def jitter_value(self, base: float, variance: float) -> float:
        """Apply random jitter within ±variance"""
        return base + self._rng.uniform(-variance, variance)
    
    def jitter_percent(self, base: float, percent: float) -> float:
        """Apply random jitter as ±percent of base value"""
        delta = base * percent
        return base + self._rng.uniform(-delta, delta)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "start_time_jitter_hours": self.start_time_jitter_hours,
            "duration_variance": self.duration_variance,
            "magnitude_variance": self.magnitude_variance,
            "seeing_range": self.seeing_range,
            "cloud_range": self.cloud_range,
            "seed": self.seed
        }


class UniverseController:
    """
    Controls the "ground truth" of the universe.
    
    Responsibilities:
    - Maintain static star field
    - Manage transient events (real astronomical phenomena)
    - Manage artifact events (false positives for testing)
    - Advance simulation time
    - Provide source lists for telescope observations
    """
    
    def __init__(
        self,
        field_size: float = 10.0,  # arcseconds
        num_stars: int = 500,
        start_time: Optional[datetime] = None,
        random_seed: Optional[int] = 42
    ):
        """
        Initialize the universe.
        
        Args:
            field_size: Size of the field in arcseconds (square)
            num_stars: Number of static stars to generate
            start_time: Starting time for simulation (defaults to now)
            random_seed: Seed for reproducible star positions
        """
        self.field_size = field_size
        self.current_time = start_time or datetime.now()
        self.start_time = self.current_time
        
        # Set GLOBAL seed for ScopeSim compatibility (it uses np.random internally)
        # Without this, ScopeSim may hang on certain random states
        if random_seed is not None:
            np.random.seed(random_seed)
        
        # ALSO use isolated RNG for our own reproducible star generation
        self._rng = np.random.default_rng(random_seed)
        
        # Generate static star field
        self.static_stars: List[Star] = self._generate_stars(num_stars)
        
        # Transient events (real astronomical phenomena)
        self.transients: List[TransientEvent] = []
        
        # Artifact events (false positives for ambiguity testing)
        self.artifacts: List[ArtifactEvent] = []
        
        # Follow-up budget for resource constraint pressure
        self.followup_budget = FollowUpBudget(window_start=self.current_time)
        
        logger.info(f"Universe initialized with {num_stars} stars at {self.current_time}")
    
    def _generate_stars(self, num_stars: int) -> List[Star]:
        """Generate random static stars"""
        stars = []
        
        # Random positions across the field (using isolated RNG)
        half_field = self.field_size / 2
        x_positions = self._rng.uniform(-half_field, half_field, num_stars)
        y_positions = self._rng.uniform(-half_field, half_field, num_stars)
        
        # Realistic magnitude distribution (more faint stars than bright)
        # Power law distribution: N(m) ∝ 10^(0.6*m)
        magnitudes = self._rng.power(2.0, num_stars) * 6 + 14  # Range ~14-20
        
        for x, y, mag in zip(x_positions, y_positions, magnitudes):
            stars.append(Star(x=float(x), y=float(y), magnitude=float(mag)))
        
        return stars
    
    def add_transient(
        self,
        x: float,
        y: float,
        start_offset_hours: float,
        duration_hours: float,
        peak_magnitude: float,
        event_type: TransientType = TransientType.SUPERNOVA_IA
    ) -> TransientEvent:
        """
        Add a new transient event to the universe.
        
        Args:
            x, y: Position in arcseconds
            start_offset_hours: Hours from current_time when event starts
            duration_hours: Total duration of event
            peak_magnitude: Brightest magnitude (at peak)
            event_type: Type of transient
            
        Returns:
            The created TransientEvent
        """
        start_time = self.current_time + timedelta(hours=start_offset_hours)
        peak_time = start_time + timedelta(hours=duration_hours / 2)
        end_time = start_time + timedelta(hours=duration_hours)
        
        transient = TransientEvent(
            id=f"TRANSIENT_{len(self.transients):03d}",
            x=x,
            y=y,
            start_time=start_time,
            peak_time=peak_time,
            end_time=end_time,
            base_magnitude=24.0,  # Invisible when not active
            peak_magnitude=peak_magnitude,
            event_type=event_type
        )
        
        self.transients.append(transient)
        logger.info(f"Added {event_type.value} at ({x:.1f}, {y:.1f}), "
                   f"peak at {peak_time}, mag {peak_magnitude}")
        
        return transient
    
    def add_transient_randomized(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        start_offset_hours: float = 0.0,
        duration_hours: float = 2.0,
        peak_magnitude: float = 18.0,
        event_type: Optional[TransientType] = None,
        config: Optional[RandomizationConfig] = None
    ) -> TransientEvent:
        """
        Add a transient with bounded randomization applied.
        
        Applies jitter to timing, magnitude, and duration to avoid
        a "scripted" feel while maintaining physical plausibility.
        
        Args:
            x, y: Base position (randomized if None)
            start_offset_hours: Base start offset (jittered)
            duration_hours: Base duration (jittered by ±20%)
            peak_magnitude: Base peak brightness (jittered by ±0.5 mag)
            event_type: Type of transient (random if None)
            config: Randomization configuration
            
        Returns:
            The created TransientEvent
        """
        config = config or RandomizationConfig()
        
        # Randomize position if not specified
        half_field = self.field_size / 2
        if x is None:
            x = config._rng.uniform(-half_field * 0.8, half_field * 0.8)
        if y is None:
            y = config._rng.uniform(-half_field * 0.8, half_field * 0.8)
        
        # Apply jitter to timing
        jittered_offset = config.jitter_value(
            start_offset_hours, config.start_time_jitter_hours
        )
        
        # Apply jitter to duration (±percent)
        jittered_duration = config.jitter_percent(
            duration_hours, config.duration_variance
        )
        jittered_duration = max(0.5, jittered_duration)  # Minimum 30 min
        
        # Apply jitter to magnitude
        jittered_mag = config.jitter_value(
            peak_magnitude, config.magnitude_variance
        )
        
        # Random event type if not specified
        if event_type is None:
            event_types = list(TransientType)
            event_type = config._rng.choice(event_types)
        
        return self.add_transient(
            x=x,
            y=y,
            start_offset_hours=jittered_offset,
            duration_hours=jittered_duration,
            peak_magnitude=jittered_mag,
            event_type=event_type
        )
    
    def generate_random_scenario(
        self,
        n_transients: int = 2,
        n_artifacts: int = 1,
        config: Optional[RandomizationConfig] = None
    ) -> Dict:
        """
        Generate a complete random scenario with reproducible seed.
        
        Creates a mixed scenario with transients and artifacts for
        testing agent robustness.
        
        Args:
            n_transients: Number of real transients to inject
            n_artifacts: Number of false positives to inject
            config: Randomization configuration (with seed for reproducibility)
            
        Returns:
            Dictionary describing the generated scenario
        """
        config = config or RandomizationConfig()
        
        created_transients = []
        created_artifacts = []
        
        # Generate transients with staggered timing
        for i in range(n_transients):
            # Stagger start times
            base_offset = i * 0.5  # 30 min apart
            
            # Vary magnitude (some bright, some faint)
            base_mag = config._rng.uniform(16.0, 20.0)
            
            transient = self.add_transient_randomized(
                start_offset_hours=base_offset,
                peak_magnitude=base_mag,
                config=config
            )
            created_transients.append(transient.id)
        
        # Generate artifacts
        for _ in range(n_artifacts):
            artifact_type = config._rng.choice(list(ArtifactType))
            artifact = self.inject_artifact(artifact_type=artifact_type)
            created_artifacts.append(artifact.id)
        
        scenario = {
            "seed": config.seed,
            "n_transients": n_transients,
            "n_artifacts": n_artifacts,
            "transient_ids": created_transients,
            "artifact_ids": created_artifacts,
            "config": config.to_dict()
        }
        
        logger.info(f"Generated scenario: {n_transients} transients, "
                   f"{n_artifacts} artifacts (seed={config.seed})")
        
        return scenario
    
    def inject_artifact(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        artifact_type: ArtifactType = ArtifactType.COSMIC_RAY,
        brightness_magnitude: float = 16.0,
        duration_seconds: float = 1.0,
        offset_seconds: float = 0.0
    ) -> ArtifactEvent:
        """
        Inject a false positive artifact into the universe.
        
        Args:
            x, y: Position in arcseconds (random if None)
            artifact_type: Type of artifact
            brightness_magnitude: How bright the artifact appears
            duration_seconds: How long the artifact lasts
            offset_seconds: Seconds from current_time when artifact appears
            
        Returns:
            The created ArtifactEvent
        """
        # Random position if not specified
        half_field = self.field_size / 2
        if x is None:
            x = float(np.random.uniform(-half_field, half_field))
        if y is None:
            y = float(np.random.uniform(-half_field, half_field))
        
        artifact_time = self.current_time + timedelta(seconds=offset_seconds)
        
        artifact = ArtifactEvent(
            id=f"ARTIFACT_{len(self.artifacts):03d}",
            x=x,
            y=y,
            artifact_time=artifact_time,
            duration_seconds=duration_seconds,
            brightness_magnitude=brightness_magnitude,
            artifact_type=artifact_type
        )
        
        self.artifacts.append(artifact)
        logger.info(f"Injected {artifact_type.value} artifact at ({x:.2f}, {y:.2f}), "
                   f"mag {brightness_magnitude}, duration {duration_seconds}s")
        
        return artifact
    
    def inject_false_positive_cluster(
        self,
        n_artifacts: int = 3,
        artifact_types: Optional[List[ArtifactType]] = None
    ) -> List[ArtifactEvent]:
        """
        Inject multiple false positive artifacts simultaneously.
        
        Useful for regime-shift stress testing where agent must handle
        multiple false alarms at once.
        
        Args:
            n_artifacts: Number of artifacts to inject
            artifact_types: Types to use (cycles if fewer than n_artifacts)
            
        Returns:
            List of created ArtifactEvents
        """
        if artifact_types is None:
            artifact_types = [ArtifactType.COSMIC_RAY, ArtifactType.HOT_PIXEL]
        
        artifacts = []
        for i in range(n_artifacts):
            artifact_type = artifact_types[i % len(artifact_types)]
            
            # Vary brightness slightly
            mag = np.random.uniform(15.0, 18.0)
            
            # Vary duration based on type
            if artifact_type == ArtifactType.COSMIC_RAY:
                duration = np.random.uniform(0.5, 2.0)
            elif artifact_type == ArtifactType.HOT_PIXEL:
                duration = np.random.uniform(60.0, 300.0)  # Longer for hot pixels
            else:
                duration = np.random.uniform(1.0, 5.0)
            
            artifact = self.inject_artifact(
                artifact_type=artifact_type,
                brightness_magnitude=float(mag),
                duration_seconds=float(duration)
            )
            artifacts.append(artifact)
        
        logger.info(f"Injected cluster of {n_artifacts} false positive artifacts")
        return artifacts
    
    def inject_competing_candidates(
        self,
        count: int = 3,
        magnitude_range: Tuple[float, float] = (18.5, 20.5),
        duration_hours: float = 2.0,
        spacing_hours: float = 0.3
    ) -> List[TransientEvent]:
        """
        Inject multiple weak candidates that compete for follow-up resources.
        
        Creates prioritization pressure by presenting simultaneous faint targets
        that cannot all be followed up within the available budget.
        
        Args:
            count: Number of competing candidates (2-4 recommended)
            magnitude_range: (min, max) for peak brightness (fainter = harder)
            duration_hours: How long each candidate is visible
            spacing_hours: Offset between candidate appearances
            
        Returns:
            List of created TransientEvents
        """
        candidates = []
        event_types = [
            TransientType.NOVA,
            TransientType.SUPERNOVA_II,
            TransientType.VARIABLE_STAR,
            TransientType.SUPERNOVA_IA
        ]
        
        half_field = self.field_size / 2
        
        for i in range(count):
            # Random position ensuring separation
            x = np.random.uniform(-half_field * 0.8, half_field * 0.8)
            y = np.random.uniform(-half_field * 0.8, half_field * 0.8)
            
            # Faint magnitude within range (harder to detect)
            peak_mag = np.random.uniform(magnitude_range[0], magnitude_range[1])
            
            # Stagger start times to create priority pressure
            start_offset = i * spacing_hours
            
            # Cycle through event types
            event_type = event_types[i % len(event_types)]
            
            transient = self.add_transient(
                x=x,
                y=y,
                start_offset_hours=start_offset,
                duration_hours=duration_hours,
                peak_magnitude=peak_mag,
                event_type=event_type
            )
            candidates.append(transient)
        
        logger.info(f"Injected {count} competing candidates "
                   f"(mag {magnitude_range[0]:.1f}-{magnitude_range[1]:.1f})")
        return candidates
    
    def get_candidate_priorities(self) -> List[Dict]:
        """
        Return ranked list of active transient candidates with priority scores.
        
        Priority based on:
        - Current brightness (brighter = higher priority)
        - Time remaining (fading soon = higher urgency)
        - Detection novelty (newer = higher priority)
        
        Returns:
            Sorted list of candidate dicts with priority scores (highest first)
        """
        candidates = []
        
        for transient in self.transients:
            if not transient.is_active(self.current_time):
                continue
            
            mag = transient.get_magnitude_at_time(self.current_time)
            
            # Calculate time until fade (urgency factor)
            time_remaining = (transient.end_time - self.current_time).total_seconds() / 3600
            
            # Priority score: lower magnitude = brighter = higher score
            # Urgency bonus for targets about to fade
            brightness_score = max(0, 25.0 - mag)  # Brighter = higher
            urgency_score = max(0, 5.0 - time_remaining)  # Fading soon = higher
            priority = brightness_score + urgency_score * 2
            
            candidates.append({
                "id": transient.id,
                "type": transient.event_type.value,
                "position": {"x": transient.x, "y": transient.y},
                "current_magnitude": mag,
                "time_remaining_hours": round(time_remaining, 2),
                "priority_score": round(priority, 2)
            })
        
        # Sort by priority (highest first)
        candidates.sort(key=lambda c: c["priority_score"], reverse=True)
        return candidates
    
    def get_resource_state(self) -> Dict:
        """Get current follow-up budget state for agent decision-making."""
        return {
            "followup_budget": self.followup_budget.to_dict(),
            "active_candidates": len(self.get_candidate_priorities())
        }
    
    def step_time(self, hours: float = 0.5) -> datetime:
        """
        Advance the simulation time.
        
        Args:
            hours: Hours to advance (default 0.5 = 30 minutes)
            
        Returns:
            New current_time
        """
        self.current_time += timedelta(hours=hours)
        logger.debug(f"Time advanced to {self.current_time}")
        return self.current_time
    
    def get_state(self) -> UniverseState:
        """
        Get the current state of the universe.
        
        Returns:
            UniverseState with all active sources
        """
        active_transients = [
            t for t in self.transients 
            if t.is_active(self.current_time)
        ]
        
        total_sources = len(self.static_stars) + len(active_transients)
        
        return UniverseState(
            current_time=self.current_time,
            static_stars=self.static_stars,
            active_transients=active_transients,
            total_sources=total_sources
        )
    
    def get_source_list_for_scopesim(self):
        """
        Generate a ScopeSim Source object from the current universe state.

        Uses the same approach as scopesim.source.source_templates.star_field():
        - Creates a Vega spectrum as the reference spectrum
        - Creates a table with x, y, weight (flux), ref (spectrum index), mag
        - Passes both spectra and table to Source constructor

        Returns:
            ScopeSim Source with all visible objects
        """
        from scopesim import Source
        from scopesim.source.source_templates import vega_spectrum
        from astropy.table import Table
        import astropy.units as u
        import numpy as np

        state = self.get_state()

        # Collect all sources
        x_coords = []
        y_coords = []
        magnitudes = []

        # Add static stars
        for star in state.static_stars:
            x_coords.append(star.x)
            y_coords.append(star.y)
            magnitudes.append(star.magnitude)

        # Add active transients
        for transient in state.active_transients:
            x_coords.append(transient.x)
            y_coords.append(transient.y)
            # Get time-dependent magnitude
            mag = transient.get_magnitude_at_time(self.current_time)
            magnitudes.append(mag)

        # Add visible artifacts (false positives)
        visible_artifacts = [a for a in self.artifacts if a.is_visible(self.current_time)]
        for artifact in visible_artifacts:
            x_coords.append(artifact.x)
            y_coords.append(artifact.y)
            mag = artifact.get_magnitude_at_time(self.current_time)
            magnitudes.append(mag)

        num_sources = len(x_coords)

        if num_sources == 0:
            # Return empty source if no objects
            logger.warning("No sources to generate - returning empty source")
            return Source()

        # Create the reference spectrum (Vega spectrum for Vega magnitudes)
        spec = vega_spectrum()

        # Convert to numpy arrays
        x = np.array(x_coords)
        y = np.array(y_coords)
        mags = np.array(magnitudes)

        # Calculate flux weights from magnitudes (same as star_field)
        weights = 10 ** (-0.4 * mags)

        # ref is an index into the spectra list (0 = first spectrum = vega_spectrum)
        ref = np.zeros(num_sources, dtype=int)

        # Create astropy Table with proper columns (matching star_field format)
        tbl = Table(
            data=[x, y, weights, ref, mags],
            names=["x", "y", "weight", "ref", "mag"],
            units=[u.arcsec, u.arcsec, None, None, u.mag]
        )
        tbl.meta["photometric_system"] = "vega"

        # Create ScopeSim source with both spectra and table
        source = Source(spectra=spec, table=tbl)

        logger.info(f"Generated source list: {num_sources} objects at {self.current_time}")
        if len(state.active_transients) > 0:
            transient_mag = magnitudes[-1]
            logger.info(f"DEBUG: Transient magnitude: {transient_mag:.2f}")

        return source
    
    def get_ground_truth(self) -> Dict:
        """
        Get ground truth for validation/scoring.
        
        Returns:
            Dictionary with all active transients and artifacts
        """
        state = self.get_state()
        visible_artifacts = [a for a in self.artifacts if a.is_visible(self.current_time)]
        
        return {
            "time": self.current_time.isoformat(),
            "active_transients": [
                {
                    "id": t.id,
                    "type": t.event_type.value,
                    "position": {"x": t.x, "y": t.y},
                    "magnitude": t.get_magnitude_at_time(self.current_time),
                    "flux": t.get_flux_at_time(self.current_time),
                    "is_artifact": False  # Real transient
                }
                for t in state.active_transients
            ],
            "visible_artifacts": [
                {
                    "id": a.id,
                    "type": a.artifact_type.value,
                    "position": {"x": a.x, "y": a.y},
                    "magnitude": a.get_magnitude_at_time(self.current_time),
                    "duration_seconds": a.duration_seconds,
                    "is_artifact": True  # Should be rejected
                }
                for a in visible_artifacts
            ],
            "total_real_events": len(state.active_transients),
            "total_artifacts": len(visible_artifacts)
        }


# Quick test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Testing UniverseController...\n")
    
    # Create universe
    universe = UniverseController(
        field_size=10.0,
        num_stars=50,
        start_time=datetime(2024, 3, 15, 22, 0, 0),
        random_seed=42
    )
    
    # Add a supernova that peaks in 2 hours
    supernova = universe.add_transient(
        x=2.0,
        y=-1.5,
        start_offset_hours=0.5,  # Starts in 30 minutes
        duration_hours=5.0,      # Lasts 5 hours
        peak_magnitude=17.0,     # Relatively bright
        event_type=TransientType.SUPERNOVA_IA
    )
    
    # Simulate time steps
    print("\nSimulation over 8 hours (30-minute steps):\n")
    print(f"{'Time':<20} {'Active Transients':<20} {'Transient Mag':<15}")
    print("-" * 60)
    
    for step in range(17):  # 8 hours / 0.5 hours = 16 steps
        state = universe.get_state()
        
        if state.active_transients:
            mag = state.active_transients[0].get_magnitude_at_time(universe.current_time)
            print(f"{universe.current_time.strftime('%m/%d %H:%M'):<20} "
                  f"{len(state.active_transients):<20} {mag:<15.2f}")
        else:
            print(f"{universe.current_time.strftime('%m/%d %H:%M'):<20} "
                  f"{len(state.active_transients):<20} {'--':<15}")
        
        universe.step_time(0.5)
    
    print("\n✅ UniverseController test complete!")
