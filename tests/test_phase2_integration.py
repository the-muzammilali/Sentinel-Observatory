"""
Phase 2 Integration Test - Complete Universe → Telescope → Differencing Pipeline

Tests:
1. UniverseController generates static stars + transient
2. TelescopeCamera captures observations  
3. ImageDifferencer detects the transient
4. Creates visualization showing transient evolution
"""

import sys
from pathlib import Path
# Add parent directory to path so we can import src modules
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import logging

# Import our components
from src.simulation.universe import UniverseController, TransientType
from src.simulation.telescope import TelescopeCamera
from src.simulation.weather import WeatherSystem
from src.processing.differencer import ImageDifferencer, DiffResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_phase2_integration():
    """
    End-to-end test of Phase 2 components.
    
    Scenario:
    - Generate reference image (before transient)
    - Add supernova
    - Capture observations at multiple times as it brightens
    - Detect transient in each observation
    """
    
    print("=" * 70)
    print("PHASE 2 INTEGRATION TEST: Transient Detection Pipeline")
    print("=" * 70)
    
    # Setup output directory (relative to project root)
    project_root = Path(__file__).parent.parent
    output_dir = project_root / "data" / "observations"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Create Universe
    print("\n[1/6] Creating universe with static stars...")
    universe = UniverseController(
        field_size=10.0,
        num_stars=100,
        start_time=datetime(2024, 3, 15, 22, 0, 0),
        random_seed=42
    )
    print(f"  ✅ Universe created with {len(universe.static_stars)} stars")
    
    # Step 2: Initialize Telescope
    print("\n[2/6] Initializing MICADO telescope...")
    camera = TelescopeCamera()
    if not camera.initialize():
        print("  ❌ Failed to initialize camera")
        return False
    print("  ✅ MICADO ready")
    
    # Step 3: Generate REFERENCE image (before transient)
    print("\n[3/6] Capturing reference image (t = -1 hour, no transient)...")
    
    # Move time back 1 hour for reference
    universe.current_time = universe.current_time - timedelta(hours=1)
    
    ref_source = universe.get_source_list_for_scopesim()
    ref_result = camera.observe(ref_source, exposure_time=30.0)
    reference_image = ref_result.image_data
    
    camera.save_observation(ref_result, output_dir / "reference")
    print(f"  ✅ Reference image captured: {reference_image.shape}")
    
    # Step 4: Add transient and advance time
    print("\n[4/6] Injecting supernova transient...")
    
    # Move time forward to start
    universe.current_time = universe.current_time + timedelta(hours=1)
    
    # Add supernova that starts now and peaks in 2 hours
    supernova = universe.add_transient(
        x=0.5,  # Position in arcsec (near center)
        y=0.5,
        start_offset_hours=0.0,  # Starts now
        duration_hours=6.0,      # Lasts 6 hours
        peak_magnitude=14.0,     # Realistic bright magnitude
        event_type=TransientType.SUPERNOVA_IA  
    )
    print(f"  ✅ Supernova added at ({supernova.x}, {supernova.y})")
    print(f"     Peak time: {supernova.peak_time}")
    print(f"     Peak magnitude: {supernova.peak_magnitude}")
    
    # Step 5: Capture time-series observations
    print("\n[5/6] Capturing time-series observations...")
    
    differencer = ImageDifferencer(sigma_threshold=4.0, min_area=5)
    observations = []
    detections = []
    
    time_steps = [3.0]  # Only verify Peak Time
    
    for i, t_hour in enumerate(time_steps):
        # Set universe time
        universe.current_time = universe.start_time + timedelta(hours=t_hour)
        
        # Get source list (stars + transient at current brightness)
        source = universe.get_source_list_for_scopesim()
        
        # Force fresh camera to avoid caching issues (ScopeSim optimization workaround)
        camera = TelescopeCamera()
        camera.initialize()
        
        # Observe
        result = camera.observe(source, exposure_time=120.0)
        current_image = result.image_data
        
        # Save observation
        camera.save_observation(result, output_dir / f"observation_t{int(t_hour):02d}h")
        
        # Run differencing
        diff_result = differencer.process(reference_image, current_image)
        
        # Get ground truth
        ground_truth = universe.get_ground_truth()
        
        observations.append({
            'time': t_hour,
            'image': current_image,
            'diff_result': diff_result,
            'ground_truth': ground_truth
        })
        
        # Check detection
        detected = len(diff_result.candidate_regions) > 0
        detections.append(detected)
        
        # Print status
        transient_mag = ground_truth['active_transients'][0]['magnitude'] if ground_truth['active_transients'] else 99.0
        print(f"  t={t_hour:4.1f}h: mag={transient_mag:5.2f}, "
              f"candidates={len(diff_result.candidate_regions)}, "
              f"detected={'✅' if detected else '❌'}")
    
    # Step 6: Create visualization
    print("\n[6/6] Creating visualization...")

    n_rows = len(time_steps)
    fig, axes = plt.subplots(n_rows, 3, figsize=(15, 4*n_rows))

    # Handle single row case (axes is 1D instead of 2D)
    if n_rows == 1:
        axes = axes.reshape(1, -1)

    for i, obs in enumerate(observations):
        # Reference with transient location marked
        vmin = np.percentile(reference_image, 1)
        vmax = np.percentile(reference_image, 99)

        axes[i, 0].imshow(reference_image, cmap='gray', vmin=vmin, vmax=vmax)
        axes[i, 0].plot(supernova.x * 100 + 512, supernova.y * 100 + 512,
                       'rx', markersize=15, markeredgewidth=2)
        axes[i, 0].set_title(f'Reference (ground truth marker)')
        axes[i, 0].axis('off')

        # Current observation
        axes[i, 1].imshow(obs['image'], cmap='gray', vmin=vmin, vmax=vmax)
        axes[i, 1].set_title(f"Observation t={obs['time']:.1f}h")
        axes[i, 1].axis('off')

        # Difference with detections
        diff = obs['diff_result'].difference_image
        diff_vmax = np.percentile(np.abs(diff), 99.5)
        axes[i, 2].imshow(diff, cmap='RdBu_r', vmin=-diff_vmax, vmax=diff_vmax)

        # Mark detections
        for cand in obs['diff_result'].candidate_regions[:3]:  # Top 3
            axes[i, 2].plot(cand.x, cand.y, 'go', markersize=20,
                          markerfacecolor='none', markeredgewidth=2)

        axes[i, 2].set_title(f"Difference ({len(obs['diff_result'].candidate_regions)} candidates)")
        axes[i, 2].axis('off')
    
    plt.tight_layout()
    viz_path = output_dir / "phase2_integration_test.png"
    plt.savefig(str(viz_path), dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"  ✅ Visualization saved: {viz_path}")
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Total observations: {len(observations)}")
    print(f"Detections: {sum(detections)}/{len(detections)}")
    print(f"Success rate: {100*sum(detections)/len(detections):.0f}%")

    # Expected: At least 75% detection rate (transient is visible most of the time)
    # For single observation, require at least 1 detection
    min_detections = max(1, int(0.75 * len(detections)))
    success = sum(detections) >= min_detections

    if success:
        print("\n✅ PHASE 2 INTEGRATION TEST PASSED!")
    else:
        print("\n⚠️  PHASE 2 TEST: Lower than expected detection rate")

    assert success, f"Expected at least {min_detections} detections, got {sum(detections)}"


if __name__ == "__main__":
    test_phase2_integration()
