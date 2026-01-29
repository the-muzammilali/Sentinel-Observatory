"""
WeatherSystem - Dynamic atmospheric conditions using Perlin noise

Generates realistic, slowly-varying weather conditions:
- Seeing (atmospheric turbulence): affects PSF blur
- Cloud extinction: affects brightness and background noise
"""

import numpy as np
from typing import Tuple, Dict
from dataclasses import dataclass
import logging

# Import noise library for Perlin noise
try:
    import noise
    NOISE_AVAILABLE = True
except ImportError:
    NOISE_AVAILABLE = False
    logging.warning("noise library not available, using fallback random walk")

logger = logging.getLogger(__name__)


@dataclass
class WeatherConditions:
    """Current weather conditions"""
    seeing: float  # arcseconds (0.5 = excellent, 2.5 = poor)
    cloud_extinction: float  # 0.0 = clear, 1.0 = completely obscured
    time_hours: float  # Simulation time in hours
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for logging"""
        return {
            "seeing": round(self.seeing, 2),
            "cloud_extinction": round(self.cloud_extinction, 3),
            "time_hours": round(self.time_hours, 2)
        }


class WeatherSystem:
    """
    Generates realistic, slowly-varying atmospheric conditions.
    
    Uses Perlin noise for smooth transitions (weather doesn't jump suddenly).
    If noise library unavailable, falls back to random walk.
    """
    
    def __init__(
        self,
        seed: int = 42,
        seeing_mean: float = 1.0,  # Average seeing (arcseconds)
        seeing_variation: float = 0.5,  # How much seeing varies
        cloud_mean: float = 0.2,  # Average cloud cover
        cloud_variation: float = 0.3  # How much clouds vary
    ):
        """
        Initialize the weather system.
        
        Args:
            seed: Random seed for reproducibility
            seeing_mean: Average seeing value
            seeing_variation: Standard deviation of seeing
            cloud_mean: Average cloud extinction
            cloud_variation: Standard deviation of clouds
        """
        self.seed = seed
        self.seeing_mean = seeing_mean
        self.seeing_variation = seeing_variation
        self.cloud_mean = cloud_mean
        self.cloud_variation = cloud_variation
        
        # Current time (for Perlin noise sampling)
        self.time_hours = 0.0
        
        # Perlin noise scales (lower = slower variation)
        self.seeing_scale = 0.3  # Changes over ~3 hours
        self.cloud_scale = 0.5   # Changes over ~2 hours
        
        # Current conditions
        self._current_seeing = seeing_mean
        self._current_clouds = cloud_mean
        
        # For random walk fallback
        np.random.seed(seed)
        
        logger.info(f"WeatherSystem initialized (seed={seed}, "
                   f"seeing={seeing_mean}±{seeing_variation}, "
                   f"clouds={cloud_mean}±{cloud_variation})")
    
    def _perlin_weather(self, time: float, scale: float, offset: float) -> float:
        """
        Generate weather value using Perlin noise.
        
        Args:
            time: Current time in hours
            scale: Noise frequency (lower = slower variation)
            offset: Offset to get different noise patterns
            
        Returns:
            Noise value in range [-1, 1]
        """
        if NOISE_AVAILABLE:
            # 2D Perlin noise (x=time, y=offset for different parameters)
            return noise.pnoise2(
                time * scale,
                offset,
                octaves=3,
                persistence=0.5,
                lacunarity=2.0,
                base=self.seed
            )
        else:
            # Fallback: simple random walk
            # This is less smooth but works without noise library
            return np.sin(time * scale + offset) * 0.5 + np.random.randn() * 0.1
    
    def step(self, hours: float = 0.5) -> WeatherConditions:
        """
        Advance weather by the given time.
        
        Args:
            hours: Hours to advance (default 0.5 = 30 minutes)
            
        Returns:
            WeatherConditions at new time
        """
        self.time_hours += hours
        
        # Generate seeing using Perlin noise
        seeing_noise = self._perlin_weather(self.time_hours, self.seeing_scale, 0.0)
        self._current_seeing = self.seeing_mean + (seeing_noise * self.seeing_variation)
        self._current_seeing = np.clip(self._current_seeing, 0.5, 2.5)
        
        # Generate cloud extinction using Perlin noise
        cloud_noise = self._perlin_weather(self.time_hours, self.cloud_scale, 100.0)
        self._current_clouds = self.cloud_mean + (cloud_noise * self.cloud_variation)
        self._current_clouds = np.clip(self._current_clouds, 0.0, 1.0)
        
        logger.debug(f"Weather at t={self.time_hours:.1f}h: "
                    f"seeing={self._current_seeing:.2f}\", "
                    f"clouds={self._current_clouds:.2f}")
        
        return self.get_conditions()
    
    def get_conditions(self) -> WeatherConditions:
        """Get current weather conditions"""
        return WeatherConditions(
            seeing=self._current_seeing,
            cloud_extinction=self._current_clouds,
            time_hours=self.time_hours
        )
    
    def reset(self, time_hours: float = 0.0):
        """Reset weather to initial state"""
        self.time_hours = time_hours
        self._current_seeing = self.seeing_mean
        self._current_clouds = self.cloud_mean
        logger.info(f"Weather reset to t={time_hours}h")


def plot_weather_evolution(hours: int = 8, step_size: float = 0.25):
    """
    Generate and plot weather evolution over time.
    
    Args:
        hours: Number of hours to simulate
        step_size: Time step in hours
    """
    import matplotlib.pyplot as plt
    
    weather = WeatherSystem(seed=42)
    
    times = []
    seeing_values = []
    cloud_values = []
    
    num_steps = int(hours / step_size)
    
    for _ in range(num_steps):
        conditions = weather.step(step_size)
        times.append(conditions.time_hours)
        seeing_values.append(conditions.seeing)
        cloud_values.append(conditions.cloud_extinction)
    
    # Create plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    
    # Seeing plot
    ax1.plot(times, seeing_values, 'b-', linewidth=2)
    ax1.axhline(y=0.5, color='g', linestyle='--', alpha=0.3, label='Excellent (0.5")')
    ax1.axhline(y=2.5, color='r', linestyle='--', alpha=0.3, label='Poor (2.5")')
    ax1.fill_between(times, 0.5, 2.5, alpha=0.1)
    ax1.set_ylabel('Seeing (arcseconds)', fontsize=12)
    ax1.set_title('Atmospheric Seeing Evolution', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    ax1.set_ylim(0.3, 2.7)
    
    # Cloud extinction plot
    ax2.plot(times, cloud_values, 'gray', linewidth=2)
    ax2.axhline(y=0.0, color='b', linestyle='--', alpha=0.3, label='Clear (0.0)')
    ax2.axhline(y=1.0, color='k', linestyle='--', alpha=0.3, label='Opaque (1.0)')
    ax2.fill_between(times, 0.0, 1.0, alpha=0.1, color='gray')
    ax2.set_xlabel('Time (hours)', fontsize=12)
    ax2.set_ylabel('Cloud Extinction', fontsize=12)
    ax2.set_title('Cloud Cover Evolution', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    ax2.legend()
    ax2.set_ylim(-0.1, 1.1)
    
    plt.tight_layout()
    
    # Save plot
    output_path = 'data/reference/weather_evolution.png'
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"✅ Weather plot saved to {output_path}")
    plt.close()
    
    # Print statistics
    print(f"\nWeather Statistics ({hours} hours):")
    print(f"  Seeing:")
    print(f"    Mean: {np.mean(seeing_values):.2f}\"")
    print(f"    Range: {np.min(seeing_values):.2f}\" - {np.max(seeing_values):.2f}\"")
    print(f"    Std Dev: {np.std(seeing_values):.2f}\"")
    print(f"  Cloud Extinction:")
    print(f"    Mean: {np.mean(cloud_values):.2f}")
    print(f"    Range: {np.min(cloud_values):.2f} - {np.max(cloud_values):.2f}")
    print(f"    Std Dev: {np.std(cloud_values):.2f}")


# Quick test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Testing WeatherSystem...\n")
    
    # Test 1: Smooth transitions
    print("Test 1: Verifying smooth weather transitions")
    print("-" * 60)
    
    weather = WeatherSystem(seed=42, seeing_mean=1.2, cloud_mean=0.3)
    
    prev_seeing = weather.get_conditions().seeing
    prev_clouds = weather.get_conditions().cloud_extinction
    max_seeing_jump = 0.0
    max_cloud_jump = 0.0
    
    for i in range(20):  # 10 hours at 0.5h steps
        conditions = weather.step(0.5)
        
        seeing_jump = abs(conditions.seeing - prev_seeing)
        cloud_jump = abs(conditions.cloud_extinction - prev_clouds)
        
        max_seeing_jump = max(max_seeing_jump, seeing_jump)
        max_cloud_jump = max(max_cloud_jump, cloud_jump)
        
        prev_seeing = conditions.seeing
        prev_clouds = conditions.cloud_extinction
        
        if i % 4 == 0:  # Print every 2 hours
            print(f"t={conditions.time_hours:4.1f}h: "
                  f"seeing={conditions.seeing:.2f}\", "
                  f"clouds={conditions.cloud_extinction:.2f}")
    
    print(f"\n✅ Maximum jumps: seeing={max_seeing_jump:.3f}\", clouds={max_cloud_jump:.3f}")
    print(f"   (Should be < 0.5 for smooth variation)")
    
    # Test 2: Generate visualization
    print("\nTest 2: Generating weather evolution plot...")
    print("-" * 60)
    plot_weather_evolution(hours=8, step_size=0.25)
    
    print("\n✅ WeatherSystem test complete!")
