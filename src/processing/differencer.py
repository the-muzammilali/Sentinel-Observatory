"""
ImageDifferencer - Detect transients by comparing astronomical images

Pipeline:
1. WCS alignment (astrometric calibration)
2. Align images (sub-pixel registration)
3. Compute difference image
4. Detect candidate regions via sigma clipping
5. Annotate candidates on output images
"""

import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass
import logging

# Image processing libraries
from scipy import ndimage
from skimage import registration, exposure
from skimage.feature import blob_dog

# Astrometric calibration
from .astrometry import AstrometricCalibrator, WCSAlignment

logger = logging.getLogger(__name__)


@dataclass
class CandidateRegion:
    """A detected transient candidate"""
    x: int  # Pixel x-coordinate
    y: int  # Pixel y-coordinate
    significance: float  # How many sigma above background
    flux: float  # Brightness in the difference image
    magnitude: float = 99.0  # Instrumental magnitude (calculated from flux)


@dataclass
class DiffResult:
    """Result of image differencing"""
    difference_image: np.ndarray  # Aligned difference (current - reference)
    annotated_image: np.ndarray  # Reference image with candidate markers
    candidate_regions: List[CandidateRegion]
    shift: Tuple[float, float]  # (dy, dx) alignment shift
    alignment_error: float  # RMS error of alignment


class ImageDifferencer:
    """
    Align and difference astronomical images to detect transients.
    
    Uses phase correlation for sub-pixel alignment and sigma clipping
    for candidate detection.
    """
    
    def __init__(
        self,
        sigma_threshold: float = 3.0,  # Detection threshold (sigma)
        min_area: int = 4,  # Minimum area in pixels for a detection
        max_candidates: int = 50,  # Maximum candidates to return
        enable_wcs_alignment: bool = True,  # Enable astrometric calibration
        field_size_arcsec: float = 10.0,  # Field of view
        pixel_scale_arcsec: float = 0.004  # Pixel scale (MICADO)
    ):
        """
        Initialize the differencer.
        
        Args:
            sigma_threshold: Detection threshold in standard deviations
            min_area: Minimum contiguous pixels for a real detection
            max_candidates: Maximum number of candidates to report
            enable_wcs_alignment: Enable WCS-based astrometric alignment
            field_size_arcsec: Field of view in arcseconds
            pixel_scale_arcsec: Pixel scale in arcsec/pixel
        """
        self.sigma_threshold = sigma_threshold
        self.min_area = min_area
        self.max_candidates = max_candidates
        self.enable_wcs_alignment = enable_wcs_alignment
        
        # Initialize astrometric calibrator
        if enable_wcs_alignment:
            self.astrometry = AstrometricCalibrator(
                field_size_arcsec=field_size_arcsec,
                pixel_scale_arcsec=pixel_scale_arcsec,
                image_size=1024  # Will be updated from actual image
            )
            logger.info(f"ImageDifferencer initialized with WCS alignment "
                       f"(sigma={sigma_threshold}, min_area={min_area})")
        else:
            self.astrometry = None
            logger.info(f"ImageDifferencer initialized WITHOUT WCS alignment "
                       f"(sigma={sigma_threshold}, min_area={min_area})")

    
    def align_images(
        self,
        reference: np.ndarray,
        current: np.ndarray
    ) -> Tuple[np.ndarray, Tuple[float, float], float]:
        """
        Align current image to reference using phase correlation.
        
        Args:
            reference: Reference image (2D array)
            current: Current image to align (2D array)
            
        Returns:
            Tuple of (aligned_image, shift, error)
            - aligned_image: Shifted current image
            - shift: (dy, dx) shift in pixels
            - error: RMS alignment error
        """
        # Use phase cross-correlation for sub-pixel precision
        shift, error, _ = registration.phase_cross_correlation(
            reference,
            current,
            upsample_factor=100  # Increased from 10 for better sub-pixel alignment
        )
        
        # Apply shift to current image
        aligned = ndimage.shift(current, shift[:2], mode='constant', cval=0)
        
        logger.debug(f"Aligned images: shift={shift}, error={error:.4f}")
        
        return aligned, shift[:2], float(error)
    
    def sigma_clip_detection(
        self,
        diff_image: np.ndarray
    ) -> List[CandidateRegion]:
        """
        Detect outlier regions in difference image using sigma clipping.

        Args:
            diff_image: Difference image (current - reference)

        Returns:
            List of CandidateRegion objects
        """
        candidates = []

        # Calculate background statistics (robust to outliers)
        # Use median absolute deviation (MAD)
        median = np.median(diff_image)
        mad = np.median(np.abs(diff_image - median))
        sigma = mad * 1.4826  # Convert MAD to standard deviation

        # If MAD-based sigma is zero (common when images are very similar),
        # fall back to using standard deviation of the central region
        # or the overall standard deviation
        if sigma < 1e-10:
            # Try using standard deviation instead
            sigma = np.std(diff_image)
            logger.debug(f"MAD-based sigma was zero, using std: {sigma:.2f}")

            if sigma < 1e-10:
                logger.warning("Difference image has near-zero variance")
                return []
        
        # Create significance map (in units of sigma)
        significance = (diff_image - median) / sigma
        
        # Find pixels above threshold
        mask = significance > self.sigma_threshold
        
        # Label connected regions
        labeled, num_features = ndimage.label(mask)
        
        # Extract candidate regions
        for region_id in range(1, num_features + 1):
            region_mask = labeled == region_id
            region_size = np.sum(region_mask)
            
            # Filter by minimum area
            if region_size < self.min_area:
                continue
            
            # Get region properties
            y_coords, x_coords = np.where(region_mask)
            centroid_y = int(np.mean(y_coords))
            centroid_x = int(np.mean(x_coords))
            
            # Calculate peak significance in this region
            peak_significance = float(np.max(significance[region_mask]))
            
            # Calculate total flux in region
            flux = float(np.sum(diff_image[region_mask]))
            
            # Convert flux to instrumental magnitude
            # Magnitude = -2.5 * log10(flux) + zero_point
            ZERO_POINT = 25.0  # Typical for astronomical imaging
            if flux > 0:
                magnitude = -2.5 * np.log10(flux) + ZERO_POINT
            else:
                magnitude = 99.0  # Non-detection value
            
            candidates.append(CandidateRegion(
                x=centroid_x,
                y=centroid_y,
                significance=peak_significance,
                flux=flux,
                magnitude=magnitude
            ))
        
        # Sort by significance (highest first)
        candidates.sort(key=lambda c: c.significance, reverse=True)
        
        # Limit to max candidates
        candidates = candidates[:self.max_candidates]
        
        logger.info(f"Detected {len(candidates)} candidate regions "
                   f"(threshold={self.sigma_threshold}σ)")
        
        return candidates
    
    def annotate_image(
        self,
        image: np.ndarray,
        candidates: List[CandidateRegion],
        reference: bool = True
    ) -> np.ndarray:
        """
        Draw markers on image showing candidate locations.
        
        Args:
            image: Base image to annotate
            candidates: List of candidates to mark
            reference: If True, use reference image style
            
        Returns:
            RGB image with annotations
        """
        # Normalize image to 0-255 for display
        img_norm = exposure.rescale_intensity(
            image,
            in_range=(np.percentile(image, 1), np.percentile(image, 99.5)),
            out_range=(0, 255)
        ).astype(np.uint8)
        
        # Convert to RGB
        annotated = np.stack([img_norm] * 3, axis=-1)
        
        # Draw circles around candidates
        for candidate in candidates:
            # Draw circle (simple implementation - just mark pixels)
            radius = max(10, int(5 * np.log10(candidate.significance + 1)))
            
            # Draw circle outline (approximate)
            for angle in np.linspace(0, 2*np.pi, 30):
                dx = int(radius * np.cos(angle))
                dy = int(radius * np.sin(angle))
                y = candidate.y + dy
                x = candidate.x + dx
                
                # Check bounds
                if 0 <= y < annotated.shape[0] and 0 <= x < annotated.shape[1]:
                    # Red circle for candidates
                    annotated[y, x] = [255, 0, 0]
            
            # Draw crosshair at center
            for offset in range(-5, 6):
                # Horizontal
                if 0 <= candidate.x + offset < annotated.shape[1]:
                    annotated[candidate.y, candidate.x + offset] = [0, 255, 0]
                # Vertical
                if 0 <= candidate.y + offset < annotated.shape[0]:
                    annotated[candidate.y + offset, candidate.x] = [0, 255, 0]
        
        return annotated
    
    def process(
        self,
        reference: np.ndarray,
        current: np.ndarray
    ) -> DiffResult:
        """
        Full differencing pipeline: WCS align, pixel align, subtract, detect.
        
        Args:
            reference: Reference image (clean baseline)
            current: Current observation
            
        Returns:
            DiffResult with difference image, annotations, and candidates
        """
        logger.info("Processing image pair...")
        
        # Step 0: WCS-based astrometric alignment (if enabled)
        if self.enable_wcs_alignment and self.astrometry is not None:
            logger.info("Applying WCS-based astrometric alignment...")
            
            # Update image size from actual data
            self.astrometry.image_size = reference.shape[0]
            
            # Perform WCS alignment
            wcs_result = self.astrometry.align_images(reference, current)
            
            logger.info(f"WCS alignment quality: {wcs_result.alignment_quality:.1%}")
            
            # Use aligned image for subsequent processing
            current_to_process = wcs_result.aligned_image
        else:
            current_to_process = current
        
        # Step 1: Sub-pixel alignment (phase correlation)
        aligned, shift, error = self.align_images(reference, current_to_process)
        
        # Step 2: Compute difference
        diff = aligned - reference
        
        # Step 3: Detect candidates
        candidates = self.sigma_clip_detection(diff)
        
        # Step 4: Create annotated image
        annotated = self.annotate_image(current, candidates)
        
        logger.info(f"Processing complete: {len(candidates)} candidates detected")
        
        return DiffResult(
            difference_image=diff,
            annotated_image=annotated,
            candidate_regions=candidates,
            shift=shift,
            alignment_error=error
        )


# Testing function
def test_differencer():
    """Test ImageDifferencer with synthetic data"""
    import matplotlib.pyplot as plt
    
    print("Testing ImageDifferencer...")
    print("=" * 60)
    
    # Create synthetic reference image (static stars)
    np.random.seed(42)
    size = 512
    reference = np.random.normal(100, 10, (size, size))  # Background noise
    
    # Add static stars
    num_stars = 20
    for _ in range(num_stars):
        x = np.random.randint(50, size-50)
        y = np.random.randint(50, size-50)
        brightness = np.random.uniform(500, 2000)
        
        # Add Gaussian star
        yy, xx = np.ogrid[:size, :size]
        star_psf = brightness * np.exp(-((xx - x)**2 + (yy - y)**2) / (2 * 3**2))
        reference += star_psf
    
    # Create current image (same stars + one transient)
    current = reference.copy()
    
    # Add transient at known location
    transient_x, transient_y = 256, 300
    transient_brightness = 1500
    yy, xx = np.ogrid[:size, :size]
    transient = transient_brightness * np.exp(
        -((xx - transient_x)**2 + (yy - transient_y)**2) / (2 * 5**2)
    )
    current += transient
    
    # Add slight shift to make it realistic
    current = ndimage.shift(current, (2, 1), mode='constant')
    
    # Process with differencer
    differencer = ImageDifferencer(sigma_threshold=5.0, min_area=10)
    result = differencer.process(reference, current)
    
    # Print results
    print(f"\nAlignment:")
    print(f"  Shift: {result.shift}")
    print(f"  Error: {result.alignment_error:.4f}")
    
    print(f"\nDetected {len(result.candidate_regions)} candidates:")
    for i, cand in enumerate(result.candidate_regions[:5], 1):
        print(f"  {i}. Position: ({cand.x}, {cand.y}), "
              f"Significance: {cand.significance:.1f}σ, "
              f"Flux: {cand.flux:.0f}")
    
    # Check if we detected the transient
    detected_transient = False
    for cand in result.candidate_regions:
        distance = np.sqrt((cand.x - transient_x)**2 + (cand.y - transient_y)**2)
        if distance < 20:  # Within 20 pixels
            detected_transient = True
            print(f"\n✅ Transient detected! Distance from truth: {distance:.1f} pixels")
            break
    
    if not detected_transient:
        print(f"\n❌ Transient NOT detected (expected at {transient_x}, {transient_y})")
    
    # Create visualization
    fig, axes = plt.subplots(2, 2, figsize=(12, 12))
    
    vmin = np.percentile(reference, 1)
    vmax = np.percentile(reference, 99)
    
    axes[0, 0].imshow(reference, cmap='gray', vmin=vmin, vmax=vmax)
    axes[0, 0].set_title('Reference Image')
    axes[0, 0].plot(transient_x, transient_y, 'rx', markersize=15, markeredgewidth=2)
    
    axes[0, 1].imshow(current, cmap='gray', vmin=vmin, vmax=vmax)
    axes[0, 1].set_title('Current Observation')
    axes[0, 1].plot(transient_x, transient_y, 'rx', markersize=15, markeredgewidth=2)
    
    diff_vmax = np.percentile(np.abs(result.difference_image), 99.5)
    axes[1, 0].imshow(result.difference_image, cmap='RdBu_r', vmin=-diff_vmax, vmax=diff_vmax)
    axes[1, 0].set_title('Difference Image')
    
    axes[1, 1].imshow(result.annotated_image)
    axes[1, 1].set_title(f'Detections ({len(result.candidate_regions)} candidates)')
    
    plt.tight_layout()
    output_path = 'data/reference/differencer_test.png'
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\n✅ Visualization saved to {output_path}")
    plt.close()
    
    print("\n✅ ImageDifferencer test complete!")
    return detected_transient


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_differencer()
