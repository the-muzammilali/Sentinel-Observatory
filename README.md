# 🔭 Project Sentinel

**An autonomous Marathon Agent for astronomical transient detection using ScopeSim and Gemini**

Built for the Google Gemini Hackathon (Marathon Track)

## Overview

Project Sentinel is an AI-powered robotic observatory manager that:

- Simulates realistic telescope observations using ScopeSim
- Detects and classifies transient astronomical events (supernovae, novae)
- Operates autonomously over simulated 8-hour observing nights
- Uses Gemini's long-context capabilities to track events across time

## Quick Start

### 1. Setup Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure API Keys

Create a `.env` file:

```bash
GOOGLE_API_KEY=your_gemini_api_key_here
```

### 3. Run the Simulation

```bash
# Start the Streamlit dashboard
streamlit run src/app.py
```

## Project Structure

```
ScopSim/
├── src/
│   ├── simulation/       # Universe and telescope logic
│   ├── processing/       # Image differencing pipeline
│   ├── agent/           # Gemini agent implementation
│   ├── utils/           # Helper functions
│   └── app.py           # Streamlit dashboard
├── tests/               # Unit tests
├── data/
│   ├── reference/       # Reference images
│   └── observations/    # Current observations
├── logs/                # Agent logs and telemetry
└── config/              # Configuration files
```

## Architecture

The system implements an autonomous OODA Loop:

1. **Observe**: Generate telescope image via ScopeSim
2. **Orient**: Process image differences vs reference
3. **Decide**: Gemini analyzes changes and decides action
4. **Act**: Execute telescope command (slew, expose, alert)

## Development Timeline

- **Phase 1 (Days 1-2)**: ScopeSim foundation
- **Phase 2 (Days 3-5)**: Universe logic (transients, weather)
- **Phase 3 (Days 6-8)**: Gemini agent integration
- **Phase 4 (Days 9-11)**: Dashboard and marathon loop
- **Phase 5 (Day 12)**: Demo and submission

## Features

- ✅ Physics-based astronomical image simulation
- ✅ Dynamic transient event injection
- ✅ Realistic weather modeling (seeing, clouds)
- ✅ AI agent with persistent memory (Thought Signatures)
- ✅ Real-time dashboard with light curves
- ✅ Accuracy tracking vs ground truth

## License

MIT License - Built for educational/hackathon purposes

## Acknowledgments

- ScopeSim by ESO
- Google Gemini API
- Streamlit
