"""
TelescopeCamera - Wrapper class for ScopeSim telescope simulation

This class provides a clean interface for generating telescope observations
using ScopeSim with the MICADO instrument on the ELT.
"""

import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    """Configuration for the telescope camera"""
    instrument: str = "MICADO"
    filter_name: str = "Ks"
    exposure_time: float = 60.0  # seconds
    ndit: int = 1  # number of integrations
    image_size: int = 1024  # pixels (will be determined by detector)


@dataclass
class ObservationResult:
    """Result of a telescope observation"""
    image_data: np.ndarray
    header: Dict[str, Any]
    metadata: Dict[str, Any]


class TelescopeCamera:
    """
    Wrapper class for ScopeSim telescope simulation.
    
    Provides a clean interface for:
    - Loading the optical train (once)
    - Generating observations from source lists
    - Modifying telescope parameters (seeing, exposure, etc.)
    """
    
    def __init__(self, config: Optional[CameraConfig] = None):
        """
        Initialize the telescope camera.
        
        Args:
            config: Camera configuration. Uses defaults if not provided.
        """
        self.config = config or CameraConfig()
        self._optical_train = None
        self._initialized = False
        
        # Store current observation parameters
        self._seeing = 0.8  # arcseconds
        self._cloud_extinction = 0.0  # 0.0 = clear, 1.0 = completely obscured
        
        logger.info(f"TelescopeCamera created with instrument: {self.config.instrument}")
    
    def initialize(self) -> bool:
        """
        Initialize the optical train (loads MICADO).
        This is separate from __init__ to allow lazy loading.
        
        Returns:
            True if initialization successful, False otherwise.
        """
        if self._initialized:
            return True
        
        try:
            import scopesim as sim
            
            logger.info(f"Loading {self.config.instrument} optical train...")
            self._optical_train = sim.OpticalTrain(self.config.instrument)
            self._initialized = True
            logger.info(f"✅ {self.config.instrument} optical train ready")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize optical train: {e}")
            return False
    
    def set_seeing(self, seeing: float) -> None:
        """
        Set atmospheric seeing.
        
        Args:
            seeing: Seeing in arcseconds (typical range: 0.5 to 2.5)
        """
        self._seeing = np.clip(seeing, 0.3, 3.0)
        logger.debug(f"Seeing set to {self._seeing}\"")
    
    def set_cloud_extinction(self, extinction: float) -> None:
        """
        Set cloud extinction (affects overall brightness).
        
        Args:
            extinction: Extinction factor (0.0 = clear, 1.0 = completely blocked)
        """
        self._cloud_extinction = np.clip(extinction, 0.0, 1.0)
        logger.debug(f"Cloud extinction set to {self._cloud_extinction}")
    
    def observe(self, source, exposure_time: Optional[float] = None) -> ObservationResult:
        """
        Generate an observation of the given source.
        
        Args:
            source: ScopeSim Source object (from source_templates)
            exposure_time: Override exposure time for this observation
            
        Returns:
            ObservationResult containing image data, header, and metadata
        """
        if not self._initialized:
            if not self.initialize():
                raise RuntimeError("Failed to initialize optical train")
        
        # Set exposure time
        exp_time = exposure_time or self.config.exposure_time
        
        # Run observation
        logger.info(f"Observing with {exp_time}s exposure...")
        # Randomize seed for realistic readout noise every time
        import time
        np.random.seed(int(time.time() * 1000) % 2**32)
        
        hdu_list = self._optical_train.observe(source, run_this_duration=exp_time)
        # Readout detector
        result = self._optical_train.readout(hdu_list=hdu_list)
        
        # Extract image data from the HDU list
        image_data = None
        header = {}
        
        for hdulist in result:
            for hdu in hdulist:
                if hasattr(hdu, 'data') and hdu.data is not None:
                    if len(hdu.data.shape) == 2:
                        image_data = hdu.data.copy()
                        header = dict(hdu.header) if hasattr(hdu, 'header') else {}
                        break
            if image_data is not None:
                break
        
        if image_data is None:
            raise RuntimeError("No image data found in readout")
        
        # Apply cloud extinction (simple flux reduction)
        if self._cloud_extinction > 0:
            # Reduce signal and add extra noise
            transmission = 1.0 - self._cloud_extinction
            background = image_data.mean()
            signal = image_data - background
            image_data = background + (signal * transmission)
            # Add extra sky noise from clouds
            cloud_noise = np.random.normal(0, 50 * self._cloud_extinction, image_data.shape)
            image_data = image_data + cloud_noise
        
        # Create metadata
        metadata = {
            "exposure_time": exp_time,
            "seeing": self._seeing,
            "cloud_extinction": self._cloud_extinction,
            "shape": image_data.shape,
            "min_value": float(image_data.min()),
            "max_value": float(image_data.max()),
            "mean_value": float(image_data.mean()),
        }
        
        logger.info(f"✅ Observation complete: {image_data.shape}")
        
        return ObservationResult(
            image_data=image_data,
            header=header,
            metadata=metadata
        )
    
    def save_observation(
        self, 
        result: ObservationResult, 
        path: str,
        save_png: bool = True
    ) -> Tuple[str, Optional[str]]:
        """
        Save observation to FITS file and optionally PNG.
        
        Args:
            result: ObservationResult to save
            path: Base path for output (without extension)
            save_png: Whether to also save a PNG preview
            
        Returns:
            Tuple of (fits_path, png_path or None)
        """
        from astropy.io import fits
        import matplotlib.pyplot as plt
        
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save FITS
        fits_path = str(path.with_suffix('.fits'))
        hdu = fits.PrimaryHDU(result.image_data)
        hdu.writeto(fits_path, overwrite=True)
        logger.info(f"Saved FITS: {fits_path}")
        
        png_path = None
        if save_png:
            png_path = str(path.with_suffix('.png'))
            plt.figure(figsize=(10, 10))
            vmin = np.percentile(result.image_data, 1)
            vmax = np.percentile(result.image_data, 99.5)
            plt.imshow(result.image_data, cmap='gray', origin='lower', 
                      vmin=vmin, vmax=vmax)
            plt.colorbar(label='Counts (ADU)')
            plt.title(f"Exposure: {result.metadata['exposure_time']}s | "
                     f"Seeing: {result.metadata['seeing']}\"")
            plt.savefig(png_path, dpi=150, bbox_inches='tight')
            plt.close()
            logger.info(f"Saved PNG: {png_path}")
        
        return fits_path, png_path


def create_star_field(
    n_stars: int = 50,
    mag_min: float = 16,
    mag_max: float = 22,
    width: float = 10,  # arcsec
    height: float = 10  # arcsec
):
    """
    Helper function to create a random star field.
    
    Args:
        n_stars: Number of stars to generate
        mag_min: Minimum (brightest) magnitude
        mag_max: Maximum (faintest) magnitude
        width: Field width in arcseconds
        height: Field height in arcseconds
        
    Returns:
        ScopeSim Source object
    """
    from scopesim.source import source_templates as st
    
    return st.star_field(
        n=n_stars,
        mmin=mag_min,
        mmax=mag_max,
        width=width,
        height=height
    )


# Quick test when run directly
if __name__ == "__main__":
    print("Testing TelescopeCamera...")
    
    # Create camera
    camera = TelescopeCamera()
    
    # Initialize (loads MICADO)
    if not camera.initialize():
        print("Failed to initialize camera!")
        exit(1)
    
    # Create a star field
    source = create_star_field(n_stars=30)
    
    # Observe
    result = camera.observe(source)
    
    # Save
    fits_path, png_path = camera.save_observation(
        result, 
        "data/reference/camera_test"
    )
    
    print(f"\n✅ Test complete!")
    print(f"   FITS: {fits_path}")
    print(f"   PNG:  {png_path}")
    print(f"   Image shape: {result.image_data.shape}")
