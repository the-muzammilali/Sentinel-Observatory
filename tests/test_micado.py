"""
Test ScopeSim with MICADO instrument - fixed readout logic
"""

import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

print("=" * 60)
print("ScopeSim MICADO Test - Full Image Generation")
print("=" * 60)

import scopesim as sim
from scopesim.source import source_templates as st

# Step 1: Create a star field source
print("\n[1/4] Creating star field source...")
np.random.seed(42)

source = st.star_field(
    n=50,       # Number of stars
    mmin=16,    # Minimum magnitude (bright)
    mmax=22,    # Maximum magnitude (faint)
    width=10,   # Field width in arcsec
    height=10   # Field height in arcsec
)
print(f"✅ Created star field with 50 stars (mag 16-22)")

# Step 2: Set up MICADO optical train
print("\n[2/4] Setting up MICADO optical train...")
micado = sim.OpticalTrain("MICADO")
print(f"✅ MICADO optical train loaded")

# Step 3: Observe the source
print("\n[3/4] Observing source (this may take a moment)...")
micado.observe(source)
print("✅ Observation complete")

# Step 4: Readout and save
print("\n[4/4] Reading out detector and saving image...")

# Readout the detector - returns a list of HDUList
result = micado.readout()
print(f"   Readout returned {len(result)} HDUList(s)")

# Debug: Inspect the result structure
for i, hdulist in enumerate(result):
    print(f"   HDUList[{i}]: {len(hdulist)} HDUs")
    for j, hdu in enumerate(hdulist):
        if hasattr(hdu, 'data') and hdu.data is not None:
            print(f"     HDU[{j}]: {type(hdu).__name__}, shape={hdu.data.shape}")
        else:
            print(f"     HDU[{j}]: {type(hdu).__name__}, data=None")

# Find the actual image data
image_data = None
for hdulist in result:
    for hdu in hdulist:
        if hasattr(hdu, 'data') and hdu.data is not None:
            if len(hdu.data.shape) == 2:  # 2D image
                image_data = hdu.data
                print(f"\n✅ Found image data: shape={image_data.shape}")
                break
    if image_data is not None:
        break

if image_data is None:
    print("❌ No image data found in readout!")
    exit(1)

print(f"   Pixel value range: {image_data.min():.2f} to {image_data.max():.2f}")

# Create output directory (relative to project root)
project_root = Path(__file__).parent.parent
output_dir = project_root / "data" / "reference"
output_dir.mkdir(parents=True, exist_ok=True)

# Save FITS
fits_path = output_dir / "micado_test.fits"
result[0].writeto(str(fits_path), overwrite=True)
print(f"✅ FITS saved to {fits_path}")

# Save PNG preview with proper scaling
plt.figure(figsize=(12, 10))

# Use log stretch for better visualization
vmin = np.percentile(image_data, 1)
vmax = np.percentile(image_data, 99.5)

plt.imshow(image_data, cmap='gray', origin='lower', vmin=vmin, vmax=vmax)
plt.colorbar(label='Counts (ADU)')
plt.title('MICADO Simulated Star Field (50 stars, mag 16-22)')
plt.xlabel('X (pixels)')
plt.ylabel('Y (pixels)')

png_path = output_dir / "micado_test.png"
plt.savefig(str(png_path), dpi=150, bbox_inches='tight')
plt.close()
print(f"✅ PNG saved to {png_path}")

# Print success summary
print("\n" + "=" * 60)
print("🎉 SUCCESS! MICADO image generation complete!")
print("=" * 60)
print(f"\nGenerated files:")
print(f"  - FITS: {fits_path}")
print(f"  - PNG:  {png_path}")
print(f"\nImage statistics:")
print(f"  - Shape: {image_data.shape}")
print(f"  - Min:   {image_data.min():.2f}")
print(f"  - Max:   {image_data.max():.2f}")
print(f"  - Mean:  {image_data.mean():.2f}")
print(f"  - Std:   {image_data.std():.2f}")
