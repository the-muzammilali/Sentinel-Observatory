# 🔭 Project Sentinel

<div align="center">

**An Autonomous AI Observatory Agent for Transient Astronomical Event Detection**

*Built for the Google DeepMind Gemini 3 Hackathon - Marathon Track*

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Gemini API](https://img.shields.io/badge/Gemini-3.0%20Flash-orange.svg)](https://ai.google.dev/)
[![ScopeSim](https://img.shields.io/badge/ScopeSim-MICADO-green.svg)](https://scopesim.readthedocs.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[Features](#-key-features) • [Architecture](#-architecture) • [Quick Start](#-quick-start) • [Demo](#-demo--testing) • [Documentation](#-documentation)

</div>

---

## 🌟 Overview

**Project Sentinel** is an autonomous AI agent that operates a simulated robotic observatory, detecting and classifying transient astronomical events (supernovae, novae) over continuous multi-hour observing sessions. It demonstrates **long-context reasoning**, **decision-making under uncertainty**, and **autonomous planning** using Google's Gemini 3.0 API.

### Why This Matters

Traditional astronomical pipelines use rigid, rule-based systems that struggle with:
- **Ambiguous detections** (cosmic rays, hot pixels, satellite streaks)
- **Weather-signal confounding** (is it dimming or just clouds?)
- **Resource allocation** (which of 5 candidates deserves follow-up?)
- **Multi-hour memory** (tracking candidates across dozens of observations)

**Sentinel solves this** by combining:
- **Classical algorithms** for image processing and detection
- **Gemini AI** for interpretation, planning, and justification
- **Physics-based simulation** (ScopeSim/MICADO) for realistic telescope images

---

## 🎯 Key Features

### ✅ **Fully Implemented**

#### **1. Autonomous OODA Loop**
- **Observe**: Generate realistic telescope images via ScopeSim (ESO's MICADO instrument)
- **Orient**: Image differencing pipeline with alignment and artifact detection
- **Decide**: Gemini analyzes images and makes strategic decisions
- **Act**: Execute telescope commands (observe, slew, alert, wait)

#### **2. Hybrid AI Architecture**
- **Classical Code**: Image processing, photometry, SNR calculations
- **Gemini Agent**: Interpretation, planning, hypothesis generation
- Clear separation of responsibilities (see [ARCHITECTURE.md](ARCHITECTURE.md))

#### **3. Long-Context Memory ("Thought Signatures")**
- Persistent candidate tracking across 8+ hour sessions
- Structured state management with Pydantic models
- Memory hygiene with automatic candidate archival

#### **4. Decision-Making Under Uncertainty**
- **False positive injection**: Cosmic rays, hot pixels, satellite streaks
- **Weather coupling**: Seeing degradation, cloud cover, extinction
- **Competing candidates**: Prioritization with resource constraints
- **Confidence dynamics**: Non-monotonic belief updates

#### **5. Ground Truth Validation**
- Hidden "answer key" for objective evaluation
- Precision, Recall, F1 Score tracking
- Alert latency measurement
- **Current Performance**: 100% Precision, 100% Recall (integration tests)

#### **6. Robust Backend Improvements** *(Recently Implemented)*
- ✅ **False Positive Injection** (#1) - Ambiguity testing
- ✅ **Decision Logger** (#6) - Explicit reasoning capture
- ✅ **Memory Manager** (#8) - Token budget control
- ✅ **Ground Truth Tracker** (#10) - Accuracy validation

---

## 🏗️ Architecture

### OODA Loop Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    AUTONOMOUS OODA CYCLE                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐      ┌─────┐ │
│  │ OBSERVE  │ ───> │  ORIENT  │ ───> │  DECIDE  │ ───> │ ACT │ │
│  └──────────┘      └──────────┘      └──────────┘      └─────┘ │
│       │                  │                  │              │     │
│   ScopeSim          Differencer         Gemini        Execute   │
│   Telescope         Alignment           Agent         Command   │
│   Simulation        Detection           Vision                  │
│                                                                  │
│  ◄────────────────── Time Advances (+30 min) ──────────────────┤
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Handles | Technology |
|-----------|---------|------------|
| **Universe Controller** | Ground truth, transient events, time evolution | Python, NumPy |
| **Telescope Camera** | Realistic image generation with noise/PSF | ScopeSim, MICADO |
| **Weather System** | Atmospheric conditions (seeing, clouds) | Custom simulation |
| **Image Differencer** | Alignment, subtraction, candidate detection | OpenCV, SciPy |
| **Gemini Agent** | Interpretation, planning, decision-making | Gemini 3.0 Flash |
| **Memory Manager** | Candidate lifecycle, token budget control | Pydantic, JSON |
| **Ground Truth** | Hidden validation, accuracy metrics | Custom tracker |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- Google Gemini API key ([Get one here](https://ai.google.dev/))
- 4GB+ RAM (for ScopeSim instrument packages)

### 1. Clone & Setup

```bash
# Clone repository
git clone https://github.com/yourusername/sentinel-observatory.git
cd sentinel-observatory

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure API Keys

Create a `.env` file in the project root:

```bash
GOOGLE_API_KEY=your_gemini_api_key_here
# Optional: Add multiple keys for rotation
GOOGLE_API_KEY_2=your_second_key
GOOGLE_API_KEY_3=your_third_key
```

### 3. Download ScopeSim Instrument Packages

```bash
# Packages are included in inst_pkgs/ directory
# If missing, download from: https://scopesim.readthedocs.io/
```

### 4. Run Integration Test

```bash
# Test all OODA loop integrations
python test_integration.py
```

Expected output:
```
✅ Marathon completed successfully!
  - Precision: 100.00%
  - Recall: 100.00%
  - F1 Score: 100.00%
```

---

## 📊 Demo & Testing

### Run Full OODA Loop Marathon

```bash
# 3-iteration demo with all improvements enabled
python test_integration.py
```

This runs a compressed marathon demonstrating:
- False positive rejection (cosmic rays, hot pixels)
- Multi-observation candidate tracking
- Weather-aware decision making
- Memory management and token budgeting
- Ground truth validation

### Run Unit Tests

```bash
# All tests
pytest tests/ -v

# Specific test suites
pytest tests/test_ground_truth.py -v
pytest tests/test_memory_manager.py -v
pytest tests/test_decision_logging.py -v
```

### Manual OODA Loop Execution

```python
from src.ooda_loop import OODALoop, OODAConfig

# Configure marathon
config = OODAConfig(
    max_iterations=10,
    step_interval_hours=0.5,
    auto_inject_transients=True,
    num_transients=2,
    inject_false_positives=True,
    num_false_positives=3,
    enable_memory_manager=True,
    enable_decision_logging=True,
    enable_ground_truth=True
)

# Run autonomous loop
loop = OODALoop(config)
loop.run_marathon()
```

---

## 📁 Project Structure

```
sentinel-observatory/
├── README.md                      # This file
├── PROJECT_SENTINEL_PRD.md        # Product requirements document
├── PROJECT_STATUS.md              # Implementation status
├── BACKEND_IMPROVEMENTS.md        # Improvement checklist
├── ARCHITECTURE.md                # Responsibility separation
├── requirements.txt               # Python dependencies
│
├── src/
│   ├── ooda_loop.py              # Main orchestrator (OODA loop)
│   ├── agent/                    # Gemini AI agent
│   │   ├── sentinel.py           # SentinelAgent class
│   │   ├── models.py             # Pydantic data models
│   │   ├── prompts.py            # System instructions
│   │   ├── context_manager.py    # State persistence
│   │   ├── memory_manager.py     # Candidate lifecycle
│   │   └── decision_log.py       # Decision logging
│   ├── simulation/               # Universe & telescope
│   │   ├── universe.py           # Ground truth controller
│   │   ├── telescope.py          # ScopeSim wrapper
│   │   ├── weather.py            # Atmospheric conditions
│   │   └── ground_truth.py       # Validation tracker
│   ├── processing/               # Image processing
│   │   └── differencer.py        # Image differencing
│   └── utils/                    # Helper functions
│
├── tests/                        # Unit & integration tests
│   ├── test_ground_truth.py
│   ├── test_memory_manager.py
│   ├── test_decision_logging.py
│   ├── test_phase3_integration.py
│   └── ...
│
├── test_integration.py           # Full OODA integration test
├── inst_pkgs/                    # ScopeSim instrument packages
│   ├── MICADO/                   # MICADO instrument
│   ├── ELT/                      # ELT telescope
│   └── Armazones/                # Observatory site
│
├── data/                         # Runtime data
│   ├── observations/             # Telescope images
│   ├── reference/                # Reference images
│   └── agent_state/              # Persistent state
│
└── logs/                         # Application logs
```

---

## 🎓 Technical Highlights

### 1. **Hybrid AI Architecture**

**Classical Code Handles:**
- Image alignment and differencing
- Source detection and photometry
- SNR calculations and thresholding
- Weather modeling

**Gemini Agent Handles:**
- Transient classification (SN Ia vs II vs Nova)
- Hypothesis generation and testing
- Multi-candidate prioritization
- Weather-aware planning
- Alert triggering with justification

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed responsibility matrix.

### 2. **Long-Context Memory Management**

```python
# Thought Signature structure
{
  "iteration": 12,
  "simulated_time": "2026-02-01T03:30:00",
  "candidates": [
    {
      "id": "CAND_01",
      "history": [
        {"time": "01:00", "magnitude": 19.5, "note": "First detection"},
        {"time": "02:00", "magnitude": 18.2, "note": "Brightening confirmed"}
      ],
      "status": "MONITORING",
      "hypothesis": "Type Ia Supernova",
      "confidence": 0.85
    }
  ],
  "last_action_reasoning": "Detected anomaly, scheduling re-observation."
}
```

### 3. **Ground Truth Validation**

The system maintains a hidden "answer key" that the agent never sees:

```python
# Ground truth metrics (from test_integration.py)
Precision: 100.00%  # No false alarms
Recall: 100.00%     # All real transients detected
F1 Score: 100.00%   # Perfect balance
Mean Alert Latency: 1.50 hours  # Fast response
```

### 4. **Coordinate System Handling**

- **Universe**: Arcseconds, centered at (0, 0)
- **Telescope**: 1024×1024 pixels
- **Conversion**: Automatic pixel-to-sky transformation
- **Matching**: 36 arcsecond radius for ground truth validation

---

## 🔧 Backend Improvements (Implemented)

Based on [BACKEND_IMPROVEMENTS.md](BACKEND_IMPROVEMENTS.md), we've implemented:

### ✅ **#1: False Positive Injection**
- Cosmic rays (single-frame spikes)
- Hot pixels (persistent artifacts)
- Satellite streaks (moving objects)
- **Impact**: Forces agent to distinguish real vs artifact

### ✅ **#6: Decision Logging**
- Explicit logging of all actions (OBSERVE, SLEW, ALERT, WAIT)
- Captures reasoning and confidence for each decision
- **Impact**: Makes "inaction as a decision" visible to judges

### ✅ **#8: Memory Manager**
- Candidate lifecycle management (NEW → MONITORING → CONFIRMED)
- Automatic archival of stale candidates
- Token budget tracking (~400 tokens/iteration)
- **Impact**: Prevents context poisoning in long marathons

### ✅ **#10: Ground Truth Tracker**
- Hidden validation system
- Precision/Recall/F1 metrics
- Alert latency measurement
- **Impact**: Objective, measurable performance evaluation

---

## 📈 Development Status

| Phase | Status | Completion |
|-------|--------|------------|
| **Phase 1: ScopeSim Foundation** | ✅ Complete | 100% |
| **Phase 2: Universe & Detection** | ✅ Complete | 100% |
| **Phase 3: Gemini AI Agent** | ✅ Complete | 100% |
| **Phase 4: OODA Loop & Integrations** | ✅ Complete | 100% |
| **Phase 5: Dashboard (Streamlit)** | 🔄 In Progress | 60% |
| **Phase 6: Documentation & Demo** | 🔄 In Progress | 80% |

### Recent Achievements (Latest Commit)
- ✅ All 4 OODA loop integrations complete
- ✅ Coordinate system fix (pixel-to-sky conversion)
- ✅ Ground truth matching working (100% accuracy)
- ✅ Comprehensive integration test passing

---

## 🎬 Demo Video & Submission

*Coming soon for Gemini Hackathon submission*

**Planned Demo Structure:**
1. System overview and architecture
2. Live OODA loop execution
3. False positive rejection demonstration
4. Multi-candidate prioritization
5. Ground truth metrics reveal
6. Light curve visualization

---

## 📚 Documentation

- **[PROJECT_SENTINEL_PRD.md](PROJECT_SENTINEL_PRD.md)** - Complete product requirements
- **[PROJECT_STATUS.md](PROJECT_STATUS.md)** - Detailed implementation status
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Hybrid AI architecture design
- **[BACKEND_IMPROVEMENTS.md](BACKEND_IMPROVEMENTS.md)** - Quality improvements checklist

---

## 🤝 Contributing

This project was built for the Google DeepMind Gemini 3 Hackathon and will be fully open-sourced after submission.

**Post-Hackathon Roadmap:**
- [ ] Complete Streamlit dashboard
- [ ] Add more transient types (AGN, TDE, GRB)
- [ ] Multi-field observation support
- [ ] Real telescope integration (via ASCOM)
- [ ] Community contributions welcome!

---

## 📄 License

MIT License - See [LICENSE](LICENSE) for details

Built for educational and research purposes. Free to use, modify, and distribute.

---

## 🙏 Acknowledgments

### Technologies
- **[Google Gemini API](https://ai.google.dev/)** - Long-context AI reasoning
- **[ScopeSim](https://scopesim.readthedocs.io/)** - Physics-based telescope simulation (ESO)
- **[MICADO](https://www.eso.org/sci/facilities/eelt/instrumentation/micado.html)** - ELT instrument model
- **[Astropy](https://www.astropy.org/)** - Astronomical data structures
- **[OpenCV](https://opencv.org/)** - Image processing
- **[Pydantic](https://pydantic.dev/)** - Data validation

### Inspiration
- Real-world astronomical survey pipelines (ZTF, LSST, Pan-STARRS)
- Autonomous robotic observatories
- AI-assisted scientific discovery

---

## 📧 Contact

**Project Maintainer**: Muzammil Ali
**Hackathon**: Google DeepMind Gemini 3 Marathon Track
**Year**: 2026

---

<div align="center">

**⭐ If you find this project interesting, please star the repository! ⭐**

*Built with ❤️ for the advancement of AI-assisted astronomy*

</div>
