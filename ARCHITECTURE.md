# Project Sentinel: Architecture & Responsibility Separation

## Overview

Project Sentinel implements a **hybrid AI architecture** where classical algorithms and LLM reasoning work in complementary roles. This document defines the clear separation of responsibilities.

---

## Responsibility Matrix

| Component          | Handles                                 | Does NOT Handle              |
| ------------------ | --------------------------------------- | ---------------------------- |
| **Classical Code** | Detection, Measurement, Thresholds      | Interpretation, Planning     |
| **Gemini LLM**     | Interpretation, Planning, Justification | Pixel math, SNR calculations |

---

## Classical Code Responsibilities

### Image Processing (`telescope.py`)

- ✅ Source detection (SExtractor-like algorithms)
- ✅ Aperture photometry
- ✅ PSF fitting
- ✅ Background subtraction
- ✅ Noise estimation

### Signal Analysis (`universe.py`)

- ✅ Light curve extraction
- ✅ Magnitude calculations
- ✅ SNR thresholding
- ✅ Transient injection/simulation
- ✅ Astrometric calculations

### Weather Modeling (`weather.py`)

- ✅ Seeing calculations
- ✅ Cloud probability
- ✅ Atmospheric extinction
- ✅ Observability scoring

---

## LLM (Gemini) Responsibilities

### Interpretation (`sentinel.py`)

- ✅ Classify transient type (SN Ia, CV, asteroid, etc.)
- ✅ Assess confidence based on evidence
- ✅ Recognize patterns across observations
- ✅ Handle ambiguous cases

### Planning (`sentinel.py`)

- ✅ Prioritize candidates for follow-up
- ✅ Decide observation strategy
- ✅ Balance competing candidates
- ✅ Adapt to weather constraints

### Decision Making (`sentinel.py`)

- ✅ Trigger/defer alerts
- ✅ Justify decisions with reasoning
- ✅ Close false positive candidates
- ✅ Request additional observations

---

## Data Flow

```
┌─────────────────────┐
│   Telescope Image   │
└──────────┬──────────┘
           │
    [Classical Code]
           │ Detections, Magnitudes, SNR
           ▼
┌─────────────────────┐
│  Structured Data    │
│  - Candidates[]     │
│  - Magnitudes       │
│  - Confidence       │
└──────────┬──────────┘
           │
    [Gemini LLM]
           │ Interpretation, Planning
           ▼
┌─────────────────────┐
│  Agent Decision     │
│  - Action           │
│  - Reasoning        │
│  - Updated beliefs  │
└─────────────────────┘
```

---

## Why This Matters

1. **Reliability**: Classical algorithms are deterministic and verified
2. **Auditability**: Numerical results are reproducible
3. **Defensibility**: LLM does what LLMs do best (reasoning)
4. **Realism**: Mirrors actual observatory architectures

---

## Anti-Patterns to Avoid

❌ Asking LLM: "Count pixels above threshold 100"
❌ Asking LLM: "Calculate the FWHM of this stellar profile"
❌ Asking LLM: "Compute the flux ratio between two apertures"
❌ Asking LLM: "Determine if SNR > 5 from raw pixel values"

✅ Tell LLM: "Source detected at mag 18.5 ± 0.2, SNR=15.3"
✅ Ask LLM: "Is this consistent with a supernova light curve?"
