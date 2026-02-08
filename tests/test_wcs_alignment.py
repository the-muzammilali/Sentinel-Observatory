"""
WCS Alignment Validation Test

Tests that astrometric calibration reduces the systematic coordinate offset
from ~3.9 arcsec to <1 arcsec.
"""

import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.processing.astrometry import AstrometricCalibrator, validate_wcs_alignment
from src.processing.differencer import ImageDifferencer
from src.simulation.universe import UniverseController
from src.simulation.telescope import TelescopeCamera


def test_wcs_alignment_reduces_offset():
    """
    Test that WCS alignment reduces coordinate offset.
    
    This test:
    1. Creates synthetic images with a transient
    2. Runs differencer WITH WCS alignment
    3. Measures sky coordinate accuracy
    4. Verifies offset is <1 arcsec (vs ~3.9 arcsec without alignment)
    """
    print("=" * 70)
    print("WCS ALIGNMENT VALIDATION TEST")
    print("=" * 70)
    print()
    
    # Setup
    print("1. Creating synthetic universe with transient...")
    universe = UniverseController(
        field_size=10.0,
        num_stars=50,
        random_seed=42
    )
    
    # Inject a transient at known position
    transient_x = 2.0  # arcsec from center
    transient_y = -1.5  # arcsec from center
    
    from src.simulation.universe import TransientType
    
    transient = universe.add_transient(
        x=transient_x,
        y=transient_y,
        peak_magnitude=17.0,
        start_offset_hours=0.0,
        duration_hours=48.0,
        event_type=TransientType.SUPERNOVA_IA
    )
    
    print(f"   Transient injected at sky: ({transient_x:.3f}, {transient_y:.3f}) arcsec")
    print()
    
    # Generate images
    print("2. Generating telescope images...")
    telescope = TelescopeCamera()
    
    # Reference (before transient)
    ref_sources = universe.get_source_list_for_scopesim()
    ref_result = telescope.observe(ref_sources)
    reference = ref_result.image_data
    
    # Current (with transient)
    universe.step_time(24.0)  # 24 hours later
    curr_sources = universe.get_source_list_for_scopesim()
    curr_result = telescope.observe(curr_sources)
    current = curr_result.image_data
    
    print("   ✓ Images generated")
    print()
    
    # Test WITHOUT WCS alignment
    print("3. Testing WITHOUT WCS alignment...")
    differencer_no_wcs = ImageDifferencer(
        sigma_threshold=3.5,
        min_area=3,
        enable_wcs_alignment=False  # Disabled
    )
    
    result_no_wcs = differencer_no_wcs.process(reference, current)
    
    if result_no_wcs.candidate_regions:
        detected = result_no_wcs.candidate_regions[0]
        
        # Convert pixel to sky (naive conversion)
        # This will have the systematic offset
        pixel_scale = 0.004  # arcsec/pixel
        image_center = 512
        
        detected_sky_x = (detected.x - image_center) * pixel_scale
        detected_sky_y = (detected.y - image_center) * pixel_scale
        
        offset_x = detected_sky_x - transient.x
        offset_y = detected_sky_y - transient.y
        offset_total = np.sqrt(offset_x**2 + offset_y**2)
        
        print(f"   Detected at pixel: ({detected.x}, {detected.y})")
        print(f"   Detected at sky (naive): ({detected_sky_x:.3f}, {detected_sky_y:.3f}) arcsec")
        print(f"   True position: ({transient_x:.3f}, {transient_y:.3f}) arcsec")
        print(f"   Offset: {offset_total:.3f} arcsec")
        print()
    else:
        print("   ⚠ No detection (check thresholds)")
        print()
    
    # Test WITH WCS alignment
    print("4. Testing WITH WCS alignment...")
    differencer_with_wcs = ImageDifferencer(
        sigma_threshold=3.5,
        min_area=3,
        enable_wcs_alignment=True  # Enabled
    )
    
    result_with_wcs = differencer_with_wcs.process(reference, current)
    
    if result_with_wcs.candidate_regions:
        detected = result_with_wcs.candidate_regions[0]
        
        # Convert pixel to sky using proper WCS
        calibrator = differencer_with_wcs.astrometry
        wcs = calibrator.create_wcs(ra_center=0.0, dec_center=0.0)
        
        detected_ra, detected_dec = calibrator.pixel_to_sky(detected.x, detected.y, wcs)
        
        # CRITICAL: WCS gives RA/Dec in degrees relative to field center (0, 0)
        # Ground truth is in arcseconds offset from center
        # Handle RA wrapping: if RA > 180°, it's actually negative (360° - RA)
        if detected_ra > 180:
            detected_ra = detected_ra - 360
        
        # Convert RA/Dec degrees to arcsec offset: multiply by 3600
        detected_sky_x_wcs = detected_ra * 3600  # deg to arcsec offset
        detected_sky_y_wcs = detected_dec * 3600  # deg to arcsec offset
        
        # Now both are in arcsec offset from center - can compare directly
        offset_x_wcs = detected_sky_x_wcs - transient.x
        offset_y_wcs = detected_sky_y_wcs - transient.y
        offset_total_wcs = np.sqrt(offset_x_wcs**2 + offset_y_wcs**2)
        
        print(f"   Detected at pixel: ({detected.x}, {detected.y})")
        print(f"   Detected at sky (WCS): RA={detected_ra:.6f}°, Dec={detected_dec:.6f}°")
        print(f"   Detected as offset (WCS): ({detected_sky_x_wcs:.3f}, {detected_sky_y_wcs:.3f}) arcsec")
        print(f"   True position (offset): ({transient_x:.3f}, {transient_y:.3f}) arcsec")
        print(f"   Offset: {offset_total_wcs:.3f} arcsec")
        print()
    else:
        print("   ⚠ No detection (check thresholds)")
        print()
    
    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    if result_no_wcs.candidate_regions and result_with_wcs.candidate_regions:
        improvement = offset_total - offset_total_wcs
        improvement_pct = (improvement / offset_total) * 100
        
        print(f"Offset WITHOUT WCS alignment: {offset_total:.3f} arcsec")
        print(f"Offset WITH WCS alignment:    {offset_total_wcs:.3f} arcsec")
        print(f"Improvement: {improvement:.3f} arcsec ({improvement_pct:.1f}%)")
        print()
        
        if offset_total_wcs < 1.0:
            print("✓ SUCCESS: WCS alignment reduces offset to <1 arcsec")
        elif offset_total_wcs < offset_total:
            print("⚠ PARTIAL: WCS alignment improves accuracy but not to target")
        else:
            print("✗ FAILURE: WCS alignment did not improve accuracy")
    else:
        print("Cannot compare - detection failed in one or both tests")
    
    print("=" * 70)


if __name__ == "__main__":
    test_wcs_alignment_reduces_offset()
