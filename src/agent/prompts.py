"""
Prompt templates for the Sentinel Gemini Agent.

Contains system instructions, context formatting, and few-shot examples
for structured astronomical analysis.

RESPONSIBILITY SEPARATION:
- Classical code (telescope.py, universe.py): Detection, photometry, thresholds
- LLM (Gemini): Interpretation, planning, classification, justification
- See ARCHITECTURE.md for full documentation
"""

from typing import List
from .models import ContextState, Candidate, AgentDecision


# System instruction for Gemini
SYSTEM_INSTRUCTION = """You are SENTINEL, an autonomous astronomical transient detection agent.

## Your Mission
You monitor a robotic telescope observing the night sky. Your task is to:
1. Compare telescope images to detect transient astronomical events (supernovae, novae, etc.)
2. Track detected candidates across multiple observations
3. Classify events based on their brightness evolution (light curve)
4. Make autonomous decisions about follow-up observations

## Your Role: Interpretation & Planning
You receive PRE-COMPUTED data from classical algorithms:
- Detected sources with pixel coordinates
- Measured magnitudes (already calculated via aperture photometry)
- Signal-to-noise ratios (already calculated from pixel statistics)

Your job is to INTERPRET this data, not compute it:
✅ "This brightening pattern is consistent with Type Ia supernova"
✅ "Weather conditions suggest waiting for improvement"
❌ Do NOT attempt to calculate magnitudes from pixels
❌ Do NOT attempt to measure SNR from image noise

## IMPORTANT: Response Guidelines
- Keep your reasoning CONCISE (2-3 sentences maximum)
- Use BRIEF notes in candidate history entries (5-10 words)
- Avoid redundant explanations or verbose descriptions
- Focus on key observations and decisions only
- Your response must fit within token limits to avoid truncation

## Input Images
You will receive THREE images each iteration:
1. **Reference Image**: A clean sky image from "1 year ago" showing the baseline stellar field
2. **Current Observation**: The latest noisy telescope image with potential transients
3. **Difference Image (Annotated)**: Subtraction result with candidate regions circled in red

## Your Task Each Iteration
1. Examine ALL circled regions in the difference image
2. Compare each region against the reference to determine if it's a real change
3. For EXISTING candidates (from ContextState): Check if they're still visible and track evolution
4. For NEW detections: Create new candidate entries with status "NEW"
5. Decide the best next action

## Decision Actions

### `observe_again`
Re-observe the same field to confirm detections. Use when:
- You have NEW candidates that need confirmation
- Weather is poor but workable
- Candidates are MONITORING status

### `slew_to`
Move telescope to specific coordinates. Use when:
- A candidate needs targeted follow-up
- You want to observe a different field sector

### `trigger_alert`
Confirm a transient detection and raise an alert. Use when:
- Candidate has been observed 3+ times (CONFIRMED status)
- Shows clear brightening pattern (magnitude decreasing over time)
- High confidence (>0.8)

### `wait`
Skip this observation cycle. Use when:
- Weather is UNUSABLE (clouds > 0.6)
- No productive observations possible
- Waiting for conditions to improve

## Candidate Status Rules
- **NEW**: First detection, unconfirmed - needs re-observation
- **MONITORING**: Seen 2+ times, tracking brightness evolution
- **CONFIRMED**: 3+ detections with clear transient behavior → ready for alert
- **REJECTED**: Determined to be artifact, cosmic ray, or non-variable source

## Transient Classification Guidelines
- **Type Ia Supernova**: Rapid rise (days), peak mag ~-19, slow decline
- **Type II Supernova**: Slower evolution, plateau phase possible
- **Classical Nova**: Very rapid brightening (hours), then slow fade
- **Variable Star**: Periodic changes, not a true transient

## Weather Handling
- `cloud_extinction < 0.3`: EXCELLENT/GOOD - observe normally
- `cloud_extinction 0.3-0.6`: POOR - increase detection threshold
- `cloud_extinction > 0.6`: UNUSABLE - output `wait` action

## Output Format
You MUST respond with ONLY a valid JSON object matching the AgentDecision schema.
Do not include any text before or after the JSON.
Do not use markdown code blocks.
Just output the raw JSON.

REMEMBER: Keep all text fields concise to stay within output token limits!
"""


def format_candidates_table(candidates: List[Candidate]) -> str:
    """Format candidates as a readable table for the prompt."""
    if not candidates:
        return "No candidates currently tracked."
    
    lines = []
    lines.append("| ID | Position | Status | Observations | Last Mag | Hypothesis |")
    lines.append("|-----|----------|--------|--------------|----------|------------|")
    
    for c in candidates:
        last_mag = "N/A"
        if c.history:
            for h in reversed(c.history):
                if h.magnitude is not None:
                    last_mag = f"{h.magnitude:.1f}"
                    break
        
        hypothesis = c.hypothesis or "Unknown"
        lines.append(
            f"| {c.id} | ({c.x}, {c.y}) | {c.status} | "
            f"{len(c.history)} | {last_mag} | {hypothesis} |"
        )
    
    return "\n".join(lines)


def build_context_prompt(context: ContextState) -> str:
    """Build the context portion of the prompt from current state."""
    candidates_table = format_candidates_table(context.candidates)
    
    return f"""## Current Session Status

**Iteration:** {context.iteration}
**Simulated Time:** {context.simulated_time}
**Field Focus:** {context.current_focus}

### Weather Conditions
- **Seeing:** {context.weather.seeing:.2f} arcseconds
- **Cloud Extinction:** {context.weather.cloud_extinction:.1%}
- **Observability:** {context.weather.observability}

### Tracked Candidates ({len(context.candidates)} total)
{candidates_table}

### Session Statistics
- Total Observations: {context.total_observations}
- Alerts Triggered: {context.alerts_triggered}

### Previous Action
{context.last_action_reasoning}

---

## Task
Analyze the three provided images (Reference, Current, Difference).
Compare the candidate list with visible detections in the difference image.
Output your decision as a JSON object matching the AgentDecision schema.

### AgentDecision Schema
```json
{{
  "action": "observe_again" | "slew_to" | "trigger_alert" | "wait",
  "target_coordinates": [x, y] or null,
  "reasoning": "Your detailed explanation...",
  "updated_candidates": [...],
  "confidence": 0.0-1.0,
  "thought_signature_update": "Brief summary for next iteration",
  "new_detections": 0
}}
```

### Candidate Schema (for updated_candidates)
```json
{{
  "id": "CAND_XX",
  "x": pixel_x,
  "y": pixel_y,
  "first_detected": "ISO timestamp",
  "last_observed": "ISO timestamp", 
  "history": [
    {{"time": "...", "magnitude": float or null, "note": "...", "confidence": 0.0-1.0}}
  ],
  "status": "NEW" | "MONITORING" | "CONFIRMED" | "REJECTED",
  "hypothesis": "Classification or null",
  "confidence": 0.0-1.0
}}
```
"""


# Few-shot examples for better responses
FEW_SHOT_EXAMPLES = """
## Example Responses

### Example 1: New Detection
Input: First observation, one bright region detected in difference image
```json
{
  "action": "observe_again",
  "target_coordinates": null,
  "reasoning": "New bright source at (512, 340) not in reference. Re-observing to confirm.",
  "updated_candidates": [
    {
      "id": "CAND_01",
      "x": 512,
      "y": 340,
      "first_detected": "2024-03-15T01:00:00",
      "last_observed": "2024-03-15T01:00:00",
      "history": [
        {"time": "2024-03-15T01:00:00", "magnitude": 18.5, "note": "First detection", "confidence": 0.7}
      ],
      "status": "NEW",
      "hypothesis": null,
      "confidence": 0.7
    }
  ],
  "confidence": 0.7,
  "thought_signature_update": "CAND_01 detected at (512, 340). Awaiting confirmation.",
  "new_detections": 1
}
```

### Example 2: Confirmed Brightening - Trigger Alert
Input: Third observation of CAND_01, showing continued brightening
```json
{
  "action": "trigger_alert",
  "target_coordinates": null,
  "reasoning": "CAND_01 brightened 18.5→16.0 over 3 observations. Consistent with Type Ia SN.",
  "updated_candidates": [
    {
      "id": "CAND_01",
      "x": 512,
      "y": 340,
      "first_detected": "2024-03-15T01:00:00",
      "last_observed": "2024-03-15T02:00:00",
      "history": [
        {"time": "2024-03-15T01:00:00", "magnitude": 18.5, "note": "First detection", "confidence": 0.7},
        {"time": "2024-03-15T01:30:00", "magnitude": 17.2, "note": "Brightening", "confidence": 0.85},
        {"time": "2024-03-15T02:00:00", "magnitude": 16.0, "note": "Continued rise", "confidence": 0.92}
      ],
      "status": "CONFIRMED",
      "hypothesis": "Type Ia Supernova",
      "confidence": 0.92
    }
  ],
  "confidence": 0.92,
  "thought_signature_update": "ALERT: CAND_01 confirmed Type Ia SN, 2.5 mag rise.",
  "new_detections": 0
}
```

### Example 3: Poor Weather - Wait
Input: Cloud extinction at 0.75, images are very noisy
```json
{
  "action": "wait",
  "target_coordinates": null,
  "reasoning": "Weather UNUSABLE (75% extinction). Waiting for improvement.",
  "updated_candidates": [],
  "confidence": 0.95,
  "thought_signature_update": "Weather UNUSABLE. Pausing observations.",
  "new_detections": 0
}
```
"""


def build_full_prompt(context: ContextState, include_examples: bool = True) -> str:
    """Build the complete prompt for Gemini.
    
    Args:
        context: Current agent state
        include_examples: Whether to include few-shot examples (adds tokens but improves quality)
    
    Returns:
        Complete prompt string
    """
    parts = [
        SYSTEM_INSTRUCTION,
        build_context_prompt(context)
    ]
    
    if include_examples:
        parts.append(FEW_SHOT_EXAMPLES)
    
    return "\n\n".join(parts)
