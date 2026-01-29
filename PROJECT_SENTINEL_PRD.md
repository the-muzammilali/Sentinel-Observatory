# 🔭 Project Sentinel: Technical PRD (Master)

**Version:** 1.1  
**Target:** Google Gemini Hackathon (Marathon Track)  
**Core Mission:** Build an autonomous "Marathon Agent" that manages a high-fidelity robotic observatory simulation (ScopeSim), detecting and classifying transient astronomical events over a continuous simulated night.

---

## 1. System Architecture High-Level

The system operates as a closed **OODA Loop** (Observe, Orient, Decide, Act).

```
┌─────────────────────────────────────────────────────────────────┐
│                        OODA LOOP                                │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ OBSERVE  │───▶│  ORIENT  │───▶│  DECIDE  │───▶│   ACT    │  │
│  │ (Image)  │    │ (Diff)   │    │ (Gemini) │    │ (Action) │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│       ▲                                               │         │
│       └───────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

1. **The Universe (Truth):** A Python logic layer that knows where stars are and if a Supernova is active.
2. **The Telescope (Simulation):** `ScopeSim` generates a raw, noisy FITS/PNG image based on the "Truth" and current "Weather."
3. **Image Preprocessing:** Align and difference current vs reference image to highlight anomalies.
4. **The Agent (Brain):** Gemini 3 receives the processed image + a "Memory Packet" (Thought Signature) from the previous step.
5. **The Action:** The Agent outputs a structured decision: `observe_again`, `slew_target`, `trigger_alert`, or `wait`.
6. **The Time:** Time advances (e.g., +30 minutes), modifying the Universe state.

---

## 2. Technology Stack & Constraints

### 2.1 Core Libraries

| Category             | Libraries                                                       |
| -------------------- | --------------------------------------------------------------- |
| **Simulation**       | `scopesim`, `scopesim_templates`, `astropy`, `numpy`            |
| **Image Processing** | `scipy`, `scikit-image` (alignment, differencing)               |
| **Agent Logic**      | `google-generativeai` (Gemini API), `pydantic` (Structured I/O) |
| **Frontend**         | `streamlit`                                                     |
| **Data Handling**    | `pandas` (Logs), `json` (State)                                 |

### 2.2 The "Lean ScopeSim" Strategy (CRITICAL)

- **Constraint:** We will **NOT** download massive instrument databases (IRDB).
- **Implementation:** We use `scopesim_templates` with **analytical PSFs**.
- **Configuration:**
  - Instrument: `MICADO` (ELT) or `Basic` (Generic).
  - PSF: `analytical` (Gaussian/Moffat).
  - Source: Procedural generation (random coordinates), no external catalog downloads (Gaia/2MASS).

### 2.3 ScopeSim Fallback Strategy (CRITICAL)

> [!CAUTION]
> If ScopeSim fails on Days 1-2 (IRDB errors, dependency issues), immediately switch to the **Synthetic Fallback**.

**Synthetic Fallback Implementation:**

```python
def generate_synthetic_image(sources, seeing, cloud_extinction):
    """Pure numpy backup - no ScopeSim dependency"""
    image = np.zeros((1024, 1024), dtype=np.float32)
    for x, y, flux in sources:
        # Add Gaussian PSF for each star
        psf = gaussian_2d(x, y, sigma=seeing * 2)
        image += flux * psf * (1 - cloud_extinction)
    # Add realistic noise
    image = np.random.poisson(image) + np.random.normal(0, 5, image.shape)
    return image
```

This preserves ALL other modules (Agent, Dashboard) unchanged.

---

## 3. Time System

| Real Time | Simulated Time | Use Case         |
| --------- | -------------- | ---------------- |
| 1 second  | 30 minutes     | Fast demo mode   |
| 2 seconds | 30 minutes     | Normal operation |
| 5 seconds | 30 minutes     | Slow/debug mode  |

- **Night Duration:** 8 simulated hours = 16-32 real minutes (configurable)
- **Transient Events:** Peak brightness over 2-4 simulated hours
- **Minimum Marathon Length:** 16 iterations (8 hours / 30min steps)

---

## 4. Module Specifications

### 4.1 Module A: The "Universe" (Simulation Engine)

**File:** `src/simulation/universe.py`

#### Class `UniverseController`

- **Responsibility:** Manages the "Truth" of what exists in the sky.
- **Attributes:**
  - `static_stars`: List of 500 fixed stars (RA, Dec, Mag 14–20).
  - `transients`: List of `TransientEvent` objects.
  - `current_time`: Datetime object.
- **Methods:**
  - `step_time(minutes)`: Advances clock.
  - `get_visible_sources()`: Returns list of `{x, y, flux}` for the current time.
  - `get_ground_truth()`: Returns list of active transients (for scoring).

#### Class `TransientEvent`

```python
class TransientEvent(BaseModel):
    id: str
    x: float
    y: float
    start_time: datetime
    peak_time: datetime  # When brightest
    end_time: datetime
    peak_magnitude: float  # e.g., 16.0 (bright)
    base_magnitude: float  # e.g., 22.0 (invisible)
    event_type: Literal["supernova", "nova", "variable_star"]

    def get_current_flux(self, current_time: datetime) -> float:
        """Gaussian light curve centered on peak_time"""
        ...
```

#### Class `TelescopeCamera`

- **Responsibility:** Wraps ScopeSim (or fallback) to generate images.
- **Methods:**
  - `__init__(use_scopesim: bool = True)`: Attempts ScopeSim, falls back if needed.
  - `capture(source_list, weather_conditions) -> Tuple[np.ndarray, dict]`:
    1. Creates source list.
    2. Applies weather effects.
    3. Returns `(image_array, metadata)`.

#### Class `WeatherSystem`

- **Responsibility:** Generates dynamic environmental factors using **Perlin Noise**.
- **Attributes:**
  - `seeing` (0.5" to 2.5"): Affects blur.
  - `cloud_extinction` (0.0 to 1.0): Affects brightness/noise.
- **Constraint:** Weather drifts smoothly; no sudden jumps.

---

### 4.2 Module B: Image Preprocessing Pipeline

**File:** `src/processing/differencer.py`

> [!IMPORTANT]
> This pipeline runs BEFORE sending images to Gemini.

#### Processing Steps:

1. **Align Images:** Sub-pixel registration using `skimage.registration.phase_cross_correlation`.
2. **Create Difference Image:** `diff = abs(current - reference)`
3. **Sigma Clipping:** Flag pixels > 3σ above background as candidates.
4. **Annotate:** Draw circles around candidate regions.
5. **Output:** Both original image + annotated difference image sent to Gemini.

```python
class ImageDifferencer:
    def process(self, reference: np.ndarray, current: np.ndarray) -> DiffResult:
        aligned = self.align_images(reference, current)
        diff = np.abs(current - aligned)
        candidates = self.sigma_clip(diff, sigma=3.0)
        annotated = self.annotate_candidates(current, candidates)
        return DiffResult(
            difference_image=diff,
            annotated_image=annotated,
            candidate_pixels=candidates
        )
```

---

### 4.3 Module C: The "Marathon Agent" (Gemini Integration)

**File:** `src/agent/sentinel.py`

#### The "Thought Signature" (Memory Persistence)

Gemini is stateless. We must pass state manually.

**Input Structure:** `ContextState` (Pydantic Model)

```json
{
  "iteration": 12,
  "simulated_time": "2024-03-15T03:30:00",
  "current_focus": "Field_Sector_4",
  "weather": { "seeing": 1.2, "clouds": 0.15 },
  "candidates": [
    {
      "id": "CAND_01",
      "x": 405,
      "y": 882,
      "history": [
        { "time": "01:00", "magnitude": 19.5, "note": "First detection" },
        { "time": "02:00", "magnitude": 18.2, "note": "Brightening confirmed" }
      ],
      "status": "MONITORING",
      "hypothesis": "Possible Type Ia Supernova"
    }
  ],
  "alerts_triggered": 0,
  "last_action_reasoning": "Detected anomaly, scheduling re-observation."
}
```

#### Output Structure: `AgentDecision` (Pydantic Model)

```python
class AgentDecision(BaseModel):
    action: Literal["observe_again", "slew_to", "trigger_alert", "wait"]
    target_coordinates: Optional[Tuple[float, float]] = None
    reasoning: str  # Explanation for logs/dashboard
    updated_candidates: List[Candidate]
    confidence: float  # 0.0-1.0
    thought_signature_update: str  # Summary for next iteration
```

#### The Prompt Strategy

**Input to Gemini:**

1. `Reference_Image.png` (Clean sky from "1 year ago").
2. `Current_Observation.png` (Noisy, current image).
3. `Difference_Annotated.png` (Highlighted anomalies).
4. `ContextState` (JSON from previous step).

**System Instruction:**

```
You are an autonomous astronomical agent monitoring a telescope.
Compare the Reference and Current images using the Difference image as a guide.
Check EVERY candidate in the ContextState - has it changed?
Detect NEW anomalies not in the candidate list.
Output a structured AgentDecision with your action and reasoning.
If weather clouds > 0.8, output action="wait" with reasoning about weather.
```

#### Agent Error Handling

```python
class AgentResilience:
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0  # seconds

    def call_gemini_with_retry(self, prompt, images) -> AgentDecision:
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.model.generate_content(...)
                return AgentDecision.model_validate_json(response.text)
            except ValidationError:
                # Malformed JSON - retry with lower temperature
                self.temperature = max(0.1, self.temperature - 0.2)
            except TimeoutError:
                self.log("Agent offline - skipping step")
                return self.default_wait_action()
            time.sleep(self.RETRY_DELAY)
```

---

### 4.4 Module D: The Dashboard

**File:** `src/app.py`

**Framework:** Streamlit

#### Layout (Priority Order):

```
┌─────────────────────────────────────────────────────────────┐
│  SIDEBAR          │  MAIN CONTENT                           │
│  ─────────────    │  ───────────────────────────────────    │
│  ▶ Start/Stop     │  ┌─────────────┐  ┌─────────────────┐   │
│  ⏱ Speed Ctrl     │  │ TELESCOPE   │  │ AGENT LOG       │   │
│  📊 Stats         │  │ VIEW        │  │ (Scrollable)    │   │
│                   │  │             │  │                 │   │
│  WEATHER          │  │ [Live PNG]  │  │ "Detected..."   │   │
│  ─────────        │  │             │  │ "Brightening.." │   │
│  Seeing: 1.2"     │  └─────────────┘  └─────────────────┘   │
│  Clouds: 15%      │                                         │
│  [Mini Graph]     │  ┌─────────────────────────────────────┐│
│                   │  │ DETECTION TIMELINE                  ││
│  SCORE            │  │ ○──●──●──○──○  (Candidates/Time)   ││
│  ─────────        │  └─────────────────────────────────────┘│
│  TP: 3            │  ┌─────────────────────────────────────┐│
│  FP: 1            │  │ LIGHT CURVE (Active Candidate)      ││
│  Accuracy: 75%    │  │ [Dynamic Plot]                      ││
│                   │  └─────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

#### Key Elements:

1. **Current Observation** - Live telescope image with overlays
2. **Agent Thought Log** - Chat-style scrollable reasoning
3. **Detection Timeline** - Horizontal bar showing all candidates over time
4. **Weather Widget** - Real-time seeing/clouds with mini-graph
5. **Light Curve Plot** - For any selected candidate (judges LOVE this)
6. **Accuracy Score** - TP/FP/Accuracy vs ground truth

---

## 5. Development Phases (12 Days)

### Phase 1: The Foundation (Days 1-2)

**Goal:** Generate a noisy, realistic image using ScopeSim OR fallback.

**Day 1:**

- [ ] Install `scopesim`, `scopesim_templates`
- [ ] Test MICADO template with analytical PSF
- [ ] Generate ONE static FITS/PNG image
- [ ] **CHECKPOINT:** If IRDB errors occur, implement synthetic fallback

**Day 2:**

- [ ] Finalize `TelescopeCamera` class (ScopeSim or synthetic)
- [ ] Generate 10 test images with varying parameters
- [ ] Verify image quality is "realistic enough"

### Phase 2: The Universe Logic (Days 3-5)

**Goal:** Make the sky dynamic with transients and weather.

**Day 3:**

- [ ] Implement `UniverseController` with static star field
- [ ] Implement `TransientEvent` with Gaussian light curve

**Day 4:**

- [ ] Implement `WeatherSystem` with Perlin noise
- [ ] Create GIF of 10-step simulation (visual validation)

**Day 5:**

- [ ] Implement `ImageDifferencer` pipeline
- [ ] Test difference detection on synthetic transient

### Phase 3: The Brain (Days 6-8)

**Goal:** Connect Gemini to the images with structured I/O.

**Day 6:**

- [ ] Define `ContextState` and `AgentDecision` Pydantic models
- [ ] Basic Gemini vision test: "What's in this image?"

**Day 7:**

- [ ] Implement full `SentinelAgent` class
- [ ] Test: "Compare Image A vs Image B" with real difference

**Day 8:**

- [ ] Implement thought signature persistence
- [ ] Test 3-step loop with memory retention
- [ ] Add error handling/retry logic

### Phase 4: The Loop & UI (Days 9-11)

**Goal:** Run the marathon with a beautiful dashboard.

**Day 9:**

- [ ] Build Streamlit skeleton with layout
- [ ] Connect live image display

**Day 10:**

- [ ] Add Agent log panel
- [ ] Add weather widget and light curve plot
- [ ] Add accuracy scoring vs ground truth

**Day 11:**

- [ ] Test full 16+ iteration marathon
- [ ] Edge case testing: bad weather, agent timeout
- [ ] Performance optimization

### Phase 5: Documentation & Demo (Day 12)

**Goal:** Vibe Engineering.

- [ ] Record screen showing Agent "remembering" across steps
- [ ] Export final "Discovery Report" as HTML artifact
- [ ] Polish README and submission materials
- [ ] Submit to Devpost

---

## 6. Winning Criteria (Checklist)

- [ ] **Scientific Validity:** Does the image look like real data (noise, blur)?
- [ ] **Long Context:** Does the Agent verify a detection across at least 3 simulated time steps?
- [ ] **Thought Signatures:** Is the code explicitly saving and reloading state between iterations?
- [ ] **Resilience:** If weather goes bad (clouds > 0.8), does the Agent say "Waiting for weather to clear"?
- [ ] **Alert Accuracy:** Does the Agent correctly identify injected transients vs false positives? (Show TP/FP score)
- [ ] **Marathon Length:** Does the system run for at least 16 simulated steps autonomously?
- [ ] **Visuals:** Does the Streamlit dashboard look like a Sci-Fi operations center?
- [ ] **Artifacts:** Can the Agent generate a "Light Curve Plot" or "Discovery Report" as an output artifact?

---

## 7. Risk Mitigation

| Risk                   | Probability | Impact   | Mitigation                           |
| ---------------------- | ----------- | -------- | ------------------------------------ |
| ScopeSim IRDB failures | HIGH        | CRITICAL | Synthetic fallback ready by Day 2    |
| Gemini rate limiting   | MEDIUM      | HIGH     | 2-second delays, retry logic         |
| Image alignment errors | LOW         | MEDIUM   | Fallback to pixel-level comparison   |
| Dashboard performance  | LOW         | LOW      | Limit to 5 FPS refresh               |
| Transient undetectable | MEDIUM      | MEDIUM   | Tune magnitude ranges during testing |
