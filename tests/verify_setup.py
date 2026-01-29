"""
Quick verification script to test ScopeSim installation
"""
import sys
print("Testing imports...")

try:
    import scopesim
    print(f"✅ ScopeSim v{scopesim.__version__}")
except ImportError as e:
    print(f"❌ ScopeSim import failed: {e}")
    sys.exit(1)

try:
    import scopesim_templates
    print(f"✅ ScopeSim Templates")
except ImportError as e:
    print(f"❌ ScopeSim Templates import failed: {e}")
    sys.exit(1)

try:
    import google.generativeai as genai
    print(f"✅ Google Generative AI")
except ImportError as e:
    print(f"❌ Google Generative AI import failed: {e}")
    sys.exit(1)

try:
    import streamlit as st
    print(f"✅ Streamlit v{st.__version__}")
except ImportError as e:
    print(f"❌ Streamlit import failed: {e}")
    sys.exit(1)

try:
    import astropy
    import numpy
    import scipy
    from skimage import registration
    print(f"✅ Scientific libraries (astropy, numpy, scipy, scikit-image)")
except ImportError as e:
    print(f"❌ Scientific library import failed: {e}")
    sys.exit(1)

print("\n🎉 All imports successful! Environment is ready.")
