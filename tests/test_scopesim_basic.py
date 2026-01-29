"""
Basic ScopeSim test - Generate a simple star field image
Phase 1, Day 1: First test to verify ScopeSim works without IRDB downloads
"""

import numpy as np
import matplotlib.pyplot as plt
from astropy.io import fits
from astropy import units as u

print("=" * 60)
print("ScopeSim Basic Test - Generating Star Field")
print("=" * 60)

try:
    import scopesim as sim
    print(f"✅ ScopeSim v{sim.__version__} imported")
except ImportError as e:
    print(f"❌ Failed to import ScopeSim: {e}")
    exit(1)

# Test 1: Create a simple source list
print("\n[1/4] Creating random star field...")
num_stars = 100
np.random.seed(42)  # For reproducibility

# Generate random star positions and magnitudes
x = np.random.uniform(-30, 30, num_stars)  # arcseconds
y = np.random.uniform(-30, 30, num_stars)  # arcseconds
mags = np.random.uniform(15, 20, num_stars)  # magnitudes

# Create ScopeSim source
from scopesim.source import source_templates as st

try:
    # Create a simple star catalog
    source = st.star_field(
        n=num_stars,
        mmin=15,
        mmax=20,
        width=60,  # arcsec
        height=60  # arcsec
    )
    print(f"✅ Created source with {num_stars} stars")
except Exception as e:
    print(f"⚠️  star_field failed: {e}")
    print("Trying alternative method...")
    
    # Fallback: Create source manually
    from scopesim import Source
    from synphot import SourceSpectrum, ConstFlux1D
    
    # Create simple flat spectrum sources
    spec = SourceSpectrum(ConstFlux1D, amplitude=1*u.ABmag)
    source = Source()
    source.add(x=x, y=y, ref=0, weight=10**(-0.4*mags))
    source.add(spectra=[spec])
    print(f"✅ Created manual source with {num_stars} stars")

# Test 2: Try to set up a basic optical system
print("\n[2/4] Setting up optical system...")
print("⚠️  Attempting minimal setup (may download small config files)...")

try:
    # Try the simplest possible setup
    cmds = sim.UserCommands(use_instrument="basic")
    print("✅ Basic instrument loaded")
except Exception as e:
    print(f"❌ Basic instrument failed: {e}")
    print("\n⚠️  ScopeSim requires configuration downloads.")
    print("FALLBACK NEEDED: Will implement synthetic image generator.")
    print("\nFor now, showing source data only:")
    print(f"  - Stars: {num_stars}")
    print(f"  - Position range: ({x.min():.1f}, {y.min():.1f}) to ({x.max():.1f}, {y.max():.1f}) arcsec")
    print(f"  - Magnitude range: {mags.min():.1f} to {mags.max():.1f}")
    
    # Create a simple visualization
    plt.figure(figsize=(8, 8))
    plt.scatter(x, y, s=100*(20-mags), alpha=0.6, c=mags, cmap='viridis_r')
    plt.colorbar(label='Magnitude')
    plt.xlabel('X (arcsec)')
    plt.ylabel('Y (arcsec)')
    plt.title('Star Field (Source Positions)')
    plt.axis('equal')
    plt.grid(True, alpha=0.3)
    plt.savefig('data/reference/test_source_positions.png', dpi=100, bbox_inches='tight')
    print(f"\n✅ Source visualization saved to data/reference/test_source_positions.png")
    exit(0)

# Test 3: Observe
print("\n[3/4] Running observation...")
try:
    cmds.observe(source)
    print("✅ Observation complete")
except Exception as e:
    print(f"❌ Observation failed: {e}")
    exit(1)

# Test 4: Get the image
print("\n[4/4] Extracting image data...")
try:
    hdus = cmds.readout()[0]
    image_data = hdus[0].data
    print(f"✅ Image shape: {image_data.shape}")
    print(f"   Pixel value range: {image_data.min():.2e} to {image_data.max():.2e}")
    
    # Save FITS (relative to project root)
    from pathlib import Path
    project_root = Path(__file__).parent.parent
    output_dir = project_root / "data" / "reference"
    output_dir.mkdir(parents=True, exist_ok=True)

    fits_path = output_dir / 'test_basic.fits'
    hdus.writeto(str(fits_path), overwrite=True)
    print(f"✅ FITS saved to {fits_path}")

    # Save PNG preview
    plt.figure(figsize=(10, 10))
    vmin, vmax = np.percentile(image_data, [1, 99])
    plt.imshow(image_data, cmap='gray', origin='lower', vmin=vmin, vmax=vmax)
    plt.colorbar(label='Counts')
    plt.title('ScopeSim Basic Test Image')
    png_path = output_dir / 'test_basic.png'
    plt.savefig(str(png_path), dpi=100, bbox_inches='tight')
    print(f"✅ PNG preview saved to {png_path}")
    
    print("\n" + "=" * 60)
    print("🎉 SUCCESS! ScopeSim is working correctly.")
    print("=" * 60)
    
except Exception as e:
    print(f"❌ Image extraction failed: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
