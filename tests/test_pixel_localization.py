"""
Pixel-Space Localization Calibration Test

This test validates that the differencer can correctly locate synthetic transients
in PIXEL SPACE, independent of WCS/astrometry issues.

Goal: Confirm detection accuracy before evaluating coordinate mapping.
"""

import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime
import csv
from astropy.io import fits
from scipy.ndimage import gaussian_filter

# Add parent to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.processing.differencer import ImageDifferencer


class SyntheticTransientInjector:
    """Inject artificial point sources into images for testing."""
    
    def __init__(self, image_size=1024, psf_fwhm=2.5):
        """
        Args:
            image_size: Image dimensions (square)
            psf_fwhm: Full-width half-maximum of PSF in pixels
        """
        self.image_size = image_size
        self.psf_fwhm = psf_fwhm
        self.psf_sigma = psf_fwhm / 2.355  # Convert FWHM to sigma
    
    def create_base_image(self, num_stars=50, noise_level=10.0):
        """
        Create a synthetic star field.
        
        Args:
            num_stars: Number of background stars
            noise_level: Gaussian noise standard deviation
            
        Returns:
            2D numpy array
        """
        image = np.random.normal(1000, noise_level, (self.image_size, self.image_size))
        
        # Add random stars
        for _ in range(num_stars):
            x = np.random.randint(50, self.image_size - 50)
            y = np.random.randint(50, self.image_size - 50)
            flux = np.random.uniform(500, 5000)
            image = self._add_point_source(image, x, y, flux)
        
        return image
    
    def _add_point_source(self, image, x, y, flux):
        """Add a Gaussian point source to the image."""
        # Create small stamp around the source
        size = int(self.psf_fwhm * 5)
        y_grid, x_grid = np.ogrid[-size:size+1, -size:size+1]
        
        # Gaussian PSF
        psf = np.exp(-(x_grid**2 + y_grid**2) / (2 * self.psf_sigma**2))
        psf = psf / psf.sum() * flux
        
        # Add to image with bounds checking
        y_min = max(0, y - size)
        y_max = min(self.image_size, y + size + 1)
        x_min = max(0, x - size)
        x_max = min(self.image_size, x + size + 1)
        
        psf_y_min = size - (y - y_min)
        psf_y_max = size + (y_max - y)
        psf_x_min = size - (x - x_min)
        psf_x_max = size + (x_max - x)
        
        image[y_min:y_max, x_min:x_max] += psf[psf_y_min:psf_y_max, psf_x_min:psf_x_max]
        
        return image
    
    def inject_transients(self, image, positions, fluxes):
        """
        Inject transients at specified positions.
        
        Args:
            image: Base image array
            positions: List of (x, y) tuples in pixels
            fluxes: List of flux values for each transient
            
        Returns:
            Modified image with transients
        """
        image_with_transients = image.copy()
        
        for (x, y), flux in zip(positions, fluxes):
            image_with_transients = self._add_point_source(
                image_with_transients, x, y, flux
            )
        
        return image_with_transients


def run_pixel_localization_test(
    num_transients=8,
    output_dir="outputs/pixel_calibration"
):
    """
    Run pixel-space localization test.
    
    Args:
        num_transients: Number of synthetic transients to inject
        output_dir: Where to save results
    """
    print("=" * 70)
    print("PIXEL-SPACE LOCALIZATION CALIBRATION TEST")
    print("=" * 70)
    print()
    
    # Setup
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create synthetic images
    print("1. Creating synthetic images...")
    injector = SyntheticTransientInjector(image_size=1024, psf_fwhm=2.5)
    
    # Reference image (no transients)
    reference = injector.create_base_image(num_stars=100, noise_level=10.0)
    
    # Generate transient positions (avoid edges)
    margin = 100
    transient_positions = []
    for i in range(num_transients):
        x = np.random.randint(margin, 1024 - margin)
        y = np.random.randint(margin, 1024 - margin)
        transient_positions.append((x, y))
    
    # Generate fluxes (varying brightness)
    transient_fluxes = np.random.uniform(300, 2000, num_transients)
    
    print(f"   Injecting {num_transients} transients at known positions")
    
    # Current image (with transients)
    current = injector.inject_transients(
        reference.copy(),
        transient_positions,
        transient_fluxes
    )
    
    # Save FITS files for inspection
    fits.writeto(
        output_path / f"reference_{timestamp}.fits",
        reference.astype(np.float32),
        overwrite=True
    )
    fits.writeto(
        output_path / f"current_{timestamp}.fits",
        current.astype(np.float32),
        overwrite=True
    )
    
    print("   ✓ Images created and saved")
    print()
    
    # Run differencer
    print("2. Running image differencing...")
    differencer = ImageDifferencer(
        sigma_threshold=3.5,
        min_area=3,
        max_candidates=50
    )
    
    diff_result = differencer.process(reference, current)
    
    print(f"   Detected {len(diff_result.candidate_regions)} candidates")
    print()
    
    # Match detected candidates to injected transients
    print("3. Matching detections to injected transients...")
    print()
    
    results = []
    matched_injected = set()
    
    for candidate in diff_result.candidate_regions:
        det_x, det_y = candidate.x, candidate.y
        
        # Find nearest injected transient
        min_dist = float('inf')
        nearest_idx = None
        
        for idx, (inj_x, inj_y) in enumerate(transient_positions):
            dist = np.sqrt((det_x - inj_x)**2 + (det_y - inj_y)**2)
            if dist < min_dist:
                min_dist = dist
                nearest_idx = idx
        
        # Record result
        if nearest_idx is not None:
            inj_x, inj_y = transient_positions[nearest_idx]
            offset_x = det_x - inj_x
            offset_y = det_y - inj_y
            
            results.append({
                'injected_x': inj_x,
                'injected_y': inj_y,
                'detected_x': det_x,
                'detected_y': det_y,
                'offset_x': offset_x,
                'offset_y': offset_y,
                'distance_pixels': min_dist,
                'flux': transient_fluxes[nearest_idx],
                'significance': candidate.significance
            })
            
            matched_injected.add(nearest_idx)
            
            status = "✓ MATCH" if min_dist < 5 else "✗ OFFSET"
            print(f"   {status}: Injected ({inj_x}, {inj_y}) → "
                  f"Detected ({det_x}, {det_y}) | "
                  f"Offset: ({offset_x:+.1f}, {offset_y:+.1f}) px | "
                  f"Distance: {min_dist:.2f} px")
    
    # Check for missed transients
    missed = set(range(num_transients)) - matched_injected
    if missed:
        print()
        print(f"   ⚠ MISSED {len(missed)} transients:")
        for idx in missed:
            x, y = transient_positions[idx]
            print(f"      Transient at ({x}, {y}) - flux {transient_fluxes[idx]:.0f}")
    
    print()
    
    # Save results to CSV
    csv_file = output_path / f"pixel_offsets_{timestamp}.csv"
    with open(csv_file, 'w', newline='') as f:
        if results:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
    
    print(f"4. Results saved to: {csv_file}")
    print()
    
    # Create visualization
    print("5. Creating debug visualization...")
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 16))
    
    # Reference image
    axes[0, 0].imshow(reference, cmap='gray', vmin=900, vmax=1200)
    axes[0, 0].set_title('Reference Image', fontsize=14)
    axes[0, 0].axis('off')
    
    # Current image
    axes[0, 1].imshow(current, cmap='gray', vmin=900, vmax=1200)
    axes[0, 1].set_title('Current Image (with transients)', fontsize=14)
    axes[0, 1].axis('off')
    
    # Difference image
    diff_image = diff_result.annotated_image if hasattr(diff_result, 'annotated_image') else current - reference
    axes[1, 0].imshow(diff_image, cmap='gray')
    axes[1, 0].set_title('Difference Image', fontsize=14)
    axes[1, 0].axis('off')
    
    # Overlay: Injected vs Detected
    axes[1, 1].imshow(diff_image, cmap='gray', alpha=0.7)
    
    # Plot injected positions (green circles)
    for x, y in transient_positions:
        circle = plt.Circle((x, y), 10, color='green', fill=False, linewidth=2, label='Injected')
        axes[1, 1].add_patch(circle)
    
    # Plot detected positions (red X)
    for candidate in diff_result.candidate_regions:
        axes[1, 1].plot(candidate.x, candidate.y, 'rx', markersize=15, markeredgewidth=3, label='Detected')
    
    axes[1, 1].set_title('Overlay: Green=Injected, Red=Detected', fontsize=14)
    axes[1, 1].axis('off')
    
    # Remove duplicate labels
    handles, labels = axes[1, 1].get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    axes[1, 1].legend(by_label.values(), by_label.keys(), loc='upper right')
    
    plt.tight_layout()
    
    viz_file = output_path / f"pixel_calibration_{timestamp}.png"
    plt.savefig(viz_file, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"   ✓ Visualization saved to: {viz_file}")
    print()
    
    # Summary statistics
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    if results:
        offsets_x = [r['offset_x'] for r in results]
        offsets_y = [r['offset_y'] for r in results]
        distances = [r['distance_pixels'] for r in results]
        
        print(f"Transients injected: {num_transients}")
        print(f"Transients detected: {len(results)}")
        print(f"Detection rate: {len(results)/num_transients*100:.1f}%")
        print()
        print(f"Mean offset X: {np.mean(offsets_x):+.2f} ± {np.std(offsets_x):.2f} pixels")
        print(f"Mean offset Y: {np.mean(offsets_y):+.2f} ± {np.std(offsets_y):.2f} pixels")
        print(f"Mean distance: {np.mean(distances):.2f} ± {np.std(distances):.2f} pixels")
        print()
        
        # Interpretation
        if abs(np.mean(offsets_x)) > 1 or abs(np.mean(offsets_y)) > 1:
            print("⚠ SYSTEMATIC OFFSET DETECTED")
            print("   → This suggests a coordinate mapping (WCS) issue")
            print("   → Detections are correct in pixel space but shifted in sky coordinates")
        else:
            print("✓ NO SYSTEMATIC OFFSET")
            print("   → Pixel-space detection is accurate")
            print("   → Any sky-coordinate errors are likely from WCS transformation")
    else:
        print("❌ NO DETECTIONS - Check detection thresholds")
    
    print("=" * 70)
    print()
    print(f"All outputs saved to: {output_path}")
    print()


if __name__ == "__main__":
    run_pixel_localization_test(
        num_transients=8,
        output_dir="outputs/pixel_calibration"
    )
