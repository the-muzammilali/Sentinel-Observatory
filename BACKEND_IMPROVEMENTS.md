# Sentinel Backend – Improvement Checklist

This document consolidates all high-leverage backend improvements discussed so far.
These are **quality, robustness, and credibility upgrades** — not feature creep.

The goal is to strengthen:

- long-horizon reasoning
- decision-making under uncertainty
- justification for using an agent (Gemini)
- judge-facing defensibility

---

## 1. Introduce Ambiguity (Highest Priority)

**Objective:**  
Move from “clear detection” to **judgment under uncertainty**.

**Improvements**

- Inject false positives:
  - single-frame brightness spikes
  - short-lived brightenings
  - moving artifacts (satellite / cosmic-ray analogs)
- Ensure some candidates:
  - appear real initially
  - get downgraded or closed later

**Why**

- Demonstrates that detection ≠ decision
- Forces self-correction
- Justifies the reasoning agent beyond math

---

## 2. Weather–Signal Confounding

**Objective:**  
Make signal interpretation ambiguous rather than clean.

**Improvements**

- Couple weather to:
  - PSF blur
  - background noise
  - uniform dimming
- Create cases where:
  - signal fades due to weather, not physics
  - agent must choose between WAIT vs RE-OBSERVE

**Why**

- Matches real observatory conditions
- Classical pipelines struggle here
- Highlights Gemini’s policy reasoning

---

## 3. Multiple Competing Candidates

**Objective:**  
Force prioritization and resource allocation.

**Improvements**

- Inject 2–4 weak candidates simultaneously
- Add soft follow-up limits (implicit resource constraint)
- Require agent to:
  - prioritize candidates
  - defer some
  - abandon low-value ones

**Why**

- Introduces policy stress
- Demonstrates trade-off reasoning
- Makes long-horizon planning visible

---

## 4. Universe Randomization (Controlled, Not Chaotic)

**Objective:**  
Avoid a scripted universe while preserving reproducibility.

**Improvements**

- Randomize (within bounded ranges):
  - transient start time
  - peak brightness
  - duration
  - weather severity
- Support deterministic seeds for demos

**Why**

- Prevents “hardcoded schedule” criticism
- Shows agent robustness
- Maintains repeatable experiments

---

## 5. Explicit Confidence Dynamics

**Objective:**  
Make belief evolution observable and non-monotonic.

**Improvements**

- Track:
  - confidence increase rate
  - confidence decay
- Allow confidence regression
- Prevent permanent confidence ratcheting

**Why**

- Models scientific skepticism
- Avoids runaway alert bias
- Enables policy analysis

---

## 6. Explicit “Inaction Is a Decision” Logging

**Objective:**  
Surface restraint as intelligent behavior.

**Improvements**

- Log decisions such as:
  - “WAIT due to insufficient persistence”
  - “WAIT due to weather uncertainty”
  - “CANDIDATE CLOSED due to non-persistence”
- Treat WAIT as a first-class action

**Why**

- Judges misinterpret silence as simplicity
- Makes discipline and caution visible
- Strengthens agent narrative

---

## 7. Regime-Shift Stress Testing (Instead of Long Runtime)

**Objective:**  
Test policy stability, not system uptime.

**Improvements**
Create structured stress scenarios:

- quiet baseline (no events)
- false-positive clusters
- delayed real transient
- post-alert decay phase

**Why**

- Reveals policy drift
- Validates long-horizon reasoning
- Stronger than “ran for days”

---

## 8. Memory Hygiene & Decay

**Objective:**  
Prepare for multi-day or month-scale reasoning without context poisoning.

**Improvements**

- Summarize or prune old candidates
- Expire stale hypotheses
- Prevent historical bias accumulation

**Why**

- Avoids long-term reasoning distortion
- Shows readiness for extended operation
- Demonstrates mature agent design

---

## 9. Maintain Clear Separation of Responsibilities

**Objective:**  
Keep architecture defensible and realistic.

**Ensure**

- Classical code handles:
  - image processing
  - math
  - thresholds
- Gemini handles:
  - interpretation
  - planning
  - escalation
  - justification

**Why**

- Prevents “LLM doing pixel math” criticism
- Aligns with real observatory systems
- Keeps reasoning clean and auditable

---

## 10. Ground Truth Transparency (Optional but Powerful)

**Objective:**  
Enable honest evaluation without cheating.

**Improvements**

- Maintain hidden ground truth
- Compute:
  - true positives
  - false positives
  - alert latency
- Optional demo toggle to reveal truth

**Why**

- Builds trust
- Shows scientific integrity
- Judges appreciate measurable outcomes

---

## 11. Scripted Regime Marathon (Demo Strategy)

**Objective:**  
Replace raw multi-day stress tests with a structured, compressed marathon that demonstrates all agent capabilities in a reproducible, narratable format.

**Why Not Raw Long Runtime:**

- API costs and rate limits for multi-day runs
- Judges won't watch hours of footage
- Chaotic randomness makes debugging harder
- Long quiet periods dilute interesting decisions

**Implementation:**

Design a 30-60 minute real-time marathon with deliberate regime phases:

```
┌─────────────────────────────────────────────────────────────────┐
│                    MARATHON SCENARIO TIMELINE                    │
├─────────────────────────────────────────────────────────────────┤
│  Phase 1: QUIET (2h sim)                                        │
│  └─ No events. Agent should correctly WAIT.                     │
│                                                                  │
│  Phase 2: FALSE POSITIVE CLUSTER (2h sim)                       │
│  └─ 3 artifacts: cosmic ray, hot pixel, satellite streak        │
│  └─ Agent should detect → investigate → REJECT                  │
│                                                                  │
│  Phase 3: WEATHER DEGRADATION (1h sim)                          │
│  └─ Clouds 50-80%, seeing 2.0" → Agent WAITS                    │
│  └─ Real transient starts during bad weather                    │
│                                                                  │
│  Phase 4: WEATHER CLEARS + DELAYED TRANSIENT (2h sim)           │
│  └─ Agent re-observes, detects rising SN Type Ia                │
│  └─ Must persist tracking across iterations                     │
│                                                                  │
│  Phase 5: COMPETING CANDIDATES (2h sim)                         │
│  └─ 2 weak candidates + 1 real transient                        │
│  └─ Agent must prioritize, defer low-value                      │
│                                                                  │
│  Phase 6: CONFIRMATION + ALERT (1h sim)                         │
│  └─ Transient confirmed, agent triggers alert                   │
│  └─ Victory lap with light curve plot                           │
└─────────────────────────────────────────────────────────────────┘
```

**Code Structure:**

```python
class MarathonScenario:
    """Pre-scripted regime with bounded randomness"""

    regimes = [
        QuietRegime(duration_hours=2),
        FalsePositiveCluster(n_artifacts=3),
        WeatherDegradation(clouds_range=(0.5, 0.8)),
        RecoveryPhase(transient_rises=True),
        CompetingCandidates(n_weak=2, n_real=1),
        ConfirmationPhase(alert_expected=True)
    ]
```

**Why This Wins:**

- Demonstrates ALL capabilities in condensed form
- Reproducible (same seed = same demo)
- Measurable (TP/FP/Alert Latency scoring)
- Narratable for demo videos
- Shows self-correction behavior

---

## Final Principle

The goal is **not** to make Sentinel:

- smarter
- more complex
- more realistic

The goal is to make it:

> **more responsible under uncertainty**.
