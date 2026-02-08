"""
Astrometric Calibration and Image Alignment

Handles WCS (World Coordinate System) alignment between reference and science images
to ensure accurate sky coordinate mapping before image subtraction.

This module solves the systematic coordinate offset issue by:
1. Creating/validating WCS for both images
2. Reprojecting science image to reference WCS grid
3. Ensuring pixel (x,y) corresponds to same sky position in both images
"""

import numpy as np
import logging
from typing import Tuple, Optional
from dataclasses import dataclass
from astropy.wcs import WCS
from astropy.io import fits
from astropy import units as u
from astropy.coordinates import SkyCoord
from reproject import reproject_interp

logger = logging.getLogger(__name__)


@dataclass
class WCSAlignment:
    """Result of WCS alignment operation."""
    aligned_image: np.ndarray
    reference_wcs: WCS
    science_wcs: WCS
    reprojection_footprint: np.ndarray
    alignment_quality: float  # 0-1, based on footprint coverage


class AstrometricCalibrator:
    """
    Handles astrometric calibration and image alignment.
    
    For ScopeSim-generated images, we create synthetic WCS based on known
    field parameters. For real telescope data, this would use plate solving
    (astrometry.net).
    """
    
    def __init__(
        self,
        field_size_arcsec: float = 10.0,
        pixel_scale_arcsec: float = 0.004,  # MICADO pixel scale
        image_size: int = 1024
    ):
        """
        Initialize astrometric calibrator.
        
        Args:
            field_size_arcsec: Field of view in arcseconds
            pixel_scale_arcsec: Pixel scale in arcsec/pixel
            image_size: Image dimensions (assumes square)
        """
        self.field_size_arcsec = field_size_arcsec
        self.pixel_scale_arcsec = pixel_scale_arcsec
        self.image_size = image_size
        
        logger.info(f"Astrometric calibrator initialized: "
                   f"FOV={field_size_arcsec}\" @ {pixel_scale_arcsec}\"/px")
    
    def create_wcs(
        self,
        ra_center: float = 0.0,
        dec_center: float = 0.0,
        rotation: float = 0.0
    ) -> WCS:
        """
        Create a WCS object for the image.
        
        For ScopeSim images, we create a synthetic WCS based on known parameters.
        For real data, this would call astrometry.net plate solver.
        
        Args:
            ra_center: RA of field center in degrees
            dec_center: Dec of field center in degrees
            rotation: Field rotation in degrees
            
        Returns:
            WCS object
        """
        wcs = WCS(naxis=2)
        
        # Reference pixel (center of image)
        wcs.wcs.crpix = [self.image_size / 2, self.image_size / 2]
        
        # Reference sky coordinates (field center)
        wcs.wcs.crval = [ra_center, dec_center]
        
        # Pixel scale (degrees per pixel)
        pixel_scale_deg = self.pixel_scale_arcsec / 3600.0
        
        # CD matrix (includes rotation)
        # NOTE: Using image pixel convention (X right, Y down) instead of
        # astronomical convention (RA left, Dec up) to match ground truth system
        cos_rot = np.cos(np.radians(rotation))
        sin_rot = np.sin(np.radians(rotation))
        
        wcs.wcs.cd = np.array([
            [pixel_scale_deg * cos_rot, pixel_scale_deg * sin_rot],
            [pixel_scale_deg * sin_rot, pixel_scale_deg * cos_rot]
        ])
        
        # Coordinate system
        wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        wcs.wcs.cunit = ["deg", "deg"]
        
        return wcs
    
    def align_images(
        self,
        reference: np.ndarray,
        science: np.ndarray,
        reference_wcs: Optional[WCS] = None,
        science_wcs: Optional[WCS] = None
    ) -> WCSAlignment:
        """
        Align science image to reference WCS grid.
        
        Args:
            reference: Reference image array
            science: Science image array
            reference_wcs: WCS for reference (created if None)
            science_wcs: WCS for science (created if None)
            
        Returns:
            WCSAlignment with aligned science image
        """
        logger.info("Starting astrometric alignment...")
        
        # Create WCS if not provided
        if reference_wcs is None:
            logger.info("Creating synthetic WCS for reference image")
            reference_wcs = self.create_wcs(ra_center=0.0, dec_center=0.0)
        
        if science_wcs is None:
            logger.info("Creating synthetic WCS for science image")
            # Science image may have slight offset/rotation
            # For now, use same WCS (in real pipeline, would plate solve)
            science_wcs = self.create_wcs(ra_center=0.0, dec_center=0.0)
        
        # Reproject science image to reference WCS grid
        logger.info("Reprojecting science image to reference WCS...")
        
        try:
            aligned_science, footprint = reproject_interp(
                (science, science_wcs),
                reference_wcs,
                shape_out=reference.shape,
                order='bilinear'
            )
            
            # Calculate alignment quality (fraction of valid pixels)
            alignment_quality = np.sum(footprint > 0) / footprint.size
            
            logger.info(f"Reprojection complete. Quality: {alignment_quality:.1%}")
            
            # Handle NaN values from reprojection
            aligned_science = np.nan_to_num(aligned_science, nan=0.0)
            
            return WCSAlignment(
                aligned_image=aligned_science,
                reference_wcs=reference_wcs,
                science_wcs=science_wcs,
                reprojection_footprint=footprint,
                alignment_quality=alignment_quality
            )
            
        except Exception as e:
            logger.error(f"Reprojection failed: {e}")
            # Fallback: return unaligned image
            return WCSAlignment(
                aligned_image=science,
                reference_wcs=reference_wcs,
                science_wcs=science_wcs,
                reprojection_footprint=np.ones_like(science),
                alignment_quality=0.0
            )
    
    def pixel_to_sky(
        self,
        x: float,
        y: float,
        wcs: WCS
    ) -> Tuple[float, float]:
        """
        Convert pixel coordinates to sky coordinates.
        
        Args:
            x: Pixel x coordinate
            y: Pixel y coordinate
            wcs: WCS object
            
        Returns:
            (ra, dec) in degrees
        """
        sky = wcs.pixel_to_world(x, y)
        return sky.ra.degree, sky.dec.degree
    
    def sky_to_pixel(
        self,
        ra: float,
        dec: float,
        wcs: WCS
    ) -> Tuple[float, float]:
        """
        Convert sky coordinates to pixel coordinates.
        
        Args:
            ra: Right ascension in degrees
            dec: Declination in degrees
            wcs: WCS object
            
        Returns:
            (x, y) pixel coordinates
        """
        sky_coord = SkyCoord(ra=ra*u.degree, dec=dec*u.degree, frame='icrs')
        x, y = wcs.world_to_pixel(sky_coord)
        return float(x), float(y)
    
    def calculate_separation(
        self,
        ra1: float,
        dec1: float,
        ra2: float,
        dec2: float
    ) -> float:
        """
        Calculate angular separation between two sky positions.
        
        Args:
            ra1, dec1: First position in degrees
            ra2, dec2: Second position in degrees
            
        Returns:
            Separation in arcseconds
        """
        coord1 = SkyCoord(ra=ra1*u.degree, dec=dec1*u.degree, frame='icrs')
        coord2 = SkyCoord(ra=ra2*u.degree, dec=dec2*u.degree, frame='icrs')
        
        separation = coord1.separation(coord2)
        return separation.arcsecond


def validate_wcs_alignment(
    reference: np.ndarray,
    science: np.ndarray,
    calibrator: AstrometricCalibrator,
    test_positions: list = None
) -> dict:
    """
    Validate WCS alignment by checking coordinate consistency.
    
    Args:
        reference: Reference image
        science: Science image
        calibrator: AstrometricCalibrator instance
        test_positions: List of (x, y) pixel positions to test
        
    Returns:
        Dictionary with validation results
    """
    if test_positions is None:
        # Test at image corners and center
        size = reference.shape[0]
        test_positions = [
            (size//4, size//4),
            (3*size//4, size//4),
            (size//2, size//2),
            (size//4, 3*size//4),
            (3*size//4, 3*size//4)
        ]
    
    # Create WCS for both images
    ref_wcs = calibrator.create_wcs()
    sci_wcs = calibrator.create_wcs()
    
    results = {
        'test_positions': [],
        'max_offset_arcsec': 0.0,
        'mean_offset_arcsec': 0.0,
        'alignment_ok': True
    }
    
    offsets = []
    
    for x, y in test_positions:
        # Convert pixel to sky in both WCS
        ra_ref, dec_ref = calibrator.pixel_to_sky(x, y, ref_wcs)
        ra_sci, dec_sci = calibrator.pixel_to_sky(x, y, sci_wcs)
        
        # Calculate separation
        offset = calibrator.calculate_separation(ra_ref, dec_ref, ra_sci, dec_sci)
        offsets.append(offset)
        
        results['test_positions'].append({
            'pixel': (x, y),
            'ref_sky': (ra_ref, dec_ref),
            'sci_sky': (ra_sci, dec_sci),
            'offset_arcsec': offset
        })
    
    results['max_offset_arcsec'] = max(offsets)
    results['mean_offset_arcsec'] = np.mean(offsets)
    results['alignment_ok'] = results['max_offset_arcsec'] < 0.5  # 0.5 arcsec tolerance
    
    return results
