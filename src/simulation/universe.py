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


class UniverseController:
    """
    Controls the "ground truth" of the universe.
    
    Responsibilities:
    - Maintain static star field
    - Manage transient events
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
        
        # Set random seed for reproducibility
        if random_seed is not None:
            np.random.seed(random_seed)
        
        # Generate static star field
        self.static_stars: List[Star] = self._generate_stars(num_stars)
        
        # Transient events (will be added later)
        self.transients: List[TransientEvent] = []
        
        logger.info(f"Universe initialized with {num_stars} stars at {self.current_time}")
    
    def _generate_stars(self, num_stars: int) -> List[Star]:
        """Generate random static stars"""
        stars = []
        
        # Random positions across the field
        half_field = self.field_size / 2
        x_positions = np.random.uniform(-half_field, half_field, num_stars)
        y_positions = np.random.uniform(-half_field, half_field, num_stars)
        
        # Realistic magnitude distribution (more faint stars than bright)
        # Power law distribution: N(m) ∝ 10^(0.6*m)
        magnitudes = np.random.power(2.0, num_stars) * 6 + 14  # Range ~14-20
        
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
            Dictionary with all active transients and their properties
        """
        state = self.get_state()
        return {
            "time": self.current_time.isoformat(),
            "active_transients": [
                {
                    "id": t.id,
                    "type": t.event_type.value,
                    "position": {"x": t.x, "y": t.y},
                    "magnitude": t.get_magnitude_at_time(self.current_time),
                    "flux": t.get_flux_at_time(self.current_time)
                }
                for t in state.active_transients
            ]
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
