#!/usr/bin/env python3
"""
Quick AI Marathon Demo - Tests all backend features with live Gemini.

Runs a quick 3-phase marathon demonstrating:
1. Quiet period (agent waits)
2. Transient detection (agent observes and tracks)
3. Confirmation (agent alerts)

Usage:
    python scripts/quick_marathon_demo.py
    
Environment:
    GOOGLE_API_KEY or GOOGLE_API_KEYS must be set
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
import random
import numpy as np

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from src.agent.sentinel import create_agent, SentinelAgent
from src.agent.models import ContextState, WeatherContext, Candidate
from src.agent.context_manager import ContextManager
from src.agent.decision_log import DecisionLogger, WaitReason
from src.agent.confidence import ConfidenceTracker
from src.agent.memory_manager import MemoryManager

from src.simulation.marathon import (
    MarathonOrchestrator, MarathonPhase, PhaseConfig,
    create_quick_demo, create_standard_marathon
)
from src.simulation.ground_truth import GroundTruthTracker, TransientType
from src.simulation.universe import TransientEvent  # Only import what exists

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Suppress noisy loggers
logging.getLogger('PIL').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)


class QuickMarathonRunner:
    """
    Runs a quick marathon demo with real Gemini API.
    
    Demonstrates all backend features in a compressed timeframe.
    """
    
    def __init__(
        self,
        seed: int = 42,
        use_mock_images: bool = True,  # Use synthetic images vs ScopeSim
        max_iterations: int = 10
    ):
        self.seed = seed
        self.use_mock_images = use_mock_images
        self.max_iterations = max_iterations
        
        random.seed(seed)
        np.random.seed(seed)
        
        # Components
        self.agent: Optional[SentinelAgent] = None
        self.orchestrator: Optional[MarathonOrchestrator] = None
        self.context_manager = ContextManager()
        self.decision_logger = DecisionLogger()
        self.confidence_tracker = ConfidenceTracker()
        self.memory_manager = MemoryManager()
        
        # Simulation state
        self.current_time = datetime(2025, 1, 1, 20, 0, 0)  # Start at 8 PM
        self.iteration = 0
        
    def initialize(self) -> bool:
        """Initialize all components."""
        logger.info("=" * 60)
        logger.info("🚀 SENTINEL OBSERVATORY - QUICK MARATHON DEMO")
        logger.info("=" * 60)
        
        # Check API key
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_API_KEYS")
        if not api_key:
            logger.error("❌ No API key found. Set GOOGLE_API_KEY or GOOGLE_API_KEYS")
            return False
        
        # Initialize agent
        logger.info("🤖 Initializing Sentinel Agent...")
        try:
            self.agent = create_agent()
            if not self.agent.test_connection():
                logger.error("❌ Gemini API connection failed")
                return False
            logger.info("✅ Gemini API connected")
        except Exception as e:
            logger.error(f"❌ Agent initialization failed: {e}")
            return False
        
        # Initialize marathon
        logger.info("🏃 Initializing Quick Demo Marathon...")
        self.orchestrator = create_quick_demo(seed=self.seed)
        self.orchestrator.start(self.current_time)
        logger.info(f"✅ Marathon ready with {len(self.orchestrator.phases)} phases")
        
        return True
    
    def run(self) -> dict:
        """Run the marathon demo."""
        if not self.initialize():
            return {"success": False, "error": "Initialization failed"}
        
        results = {
            "success": True,
            "iterations": [],
            "actions": [],
            "phases_completed": 0
        }
        
        logger.info("\n" + "=" * 60)
        logger.info("🎬 MARATHON STARTING")
        logger.info("=" * 60)
        
        while not self.orchestrator.is_complete and self.iteration < self.max_iterations:
            self.iteration += 1
            
            try:
                iteration_result = self._run_iteration()
                results["iterations"].append(iteration_result)
                results["actions"].append(iteration_result.get("action", "unknown"))
                
            except Exception as e:
                logger.error(f"❌ Iteration {self.iteration} failed: {e}")
                results["iterations"].append({
                    "iteration": self.iteration,
                    "error": str(e)
                })
            
            # Advance time
            self.current_time += timedelta(minutes=30)
        
        # Finalize
        marathon_result = self.orchestrator.finalize()
        results["phases_completed"] = marathon_result.phases_completed
        results["score"] = marathon_result.score
        results["metrics"] = marathon_result.metrics.to_dict()
        
        self._print_summary(results)
        
        return results
    
    def _run_iteration(self) -> dict:
        """Run a single iteration."""
        # Get marathon state
        state = self.orchestrator.tick(self.current_time)
        phase = state["phase"]
        
        logger.info(f"\n{'='*40}")
        logger.info(f"📍 Iteration {self.iteration} | Phase: {phase.upper()}")
        logger.info(f"🕐 Simulated Time: {self.current_time.strftime('%Y-%m-%d %H:%M')}")
        logger.info(f"📖 {state.get('narration', '')}")
        logger.info("=" * 40)
        
        # Generate images (mock for quick demo)
        reference, current, diff = self._generate_mock_images(state)
        
        # Build context
        context = self._build_context(state)
        
        # Call agent
        logger.info("🧠 Calling Gemini for analysis...")
        decision = self.agent.analyze_images(
            reference=reference,
            current=current,
            diff_annotated=diff,
            context=context
        )
        
        action = decision.action
        logger.info(f"🎯 Decision: {action}")
        logger.info(f"💭 Reasoning: {decision.reasoning[:100]}...")
        
        # Log the decision
        if action == "wait":
            self.decision_logger.log_wait(
                reason=WaitReason.WEATHER_TOO_BAD if state["phase"] == "weather_degradation" else WaitReason.NO_CANDIDATES,
                context_summary={"phase": phase}
            )
        
        # Record action in marathon
        self.orchestrator.record_action(
            action=action,
            time=self.current_time
        )
        
        return {
            "iteration": self.iteration,
            "phase": phase,
            "action": action,
            "reasoning": decision.reasoning[:200],
            "candidates_count": len(decision.updated_candidates)
        }
    
    def _generate_mock_images(self, state: dict) -> tuple:
        """Generate mock images for quick demo."""
        # Create simple synthetic images
        size = 256
        reference = np.random.normal(100, 10, (size, size)).astype(np.uint8)
        
        # Add transient if in appropriate phase
        current = reference.copy()
        if state["phase"] in ["weather_recovery", "confirmation"]:
            # Add bright spot (simulated transient)
            y, x = size // 2, size // 2
            for dy in range(-3, 4):
                for dx in range(-3, 4):
                    if dy*dy + dx*dx <= 9:
                        current[y+dy, x+dx] = min(255, current[y+dy, x+dx] + 100)
        
        # Generate diff
        diff = np.abs(current.astype(np.int16) - reference.astype(np.int16)).astype(np.uint8)
        
        return reference, current, diff
    
    def _build_context(self, state: dict) -> ContextState:
        """Build context state from marathon state."""
        # Weather based on phase
        clouds = state["cloud_range"][0] if "cloud_range" in state else 0.1
        seeing = 1.2
        
        # Use the actual WeatherContext fields
        weather = WeatherContext.from_weather_system(
            seeing=seeing,
            cloud_extinction=clouds
        )
        
        return ContextState(
            iteration=self.iteration,
            simulated_time=self.current_time.isoformat(),
            weather=weather,
            candidates=[]
        )
    
    def _print_summary(self, results: dict):
        """Print final summary."""
        logger.info("\n" + "=" * 60)
        logger.info("🏁 MARATHON COMPLETE")
        logger.info("=" * 60)
        
        logger.info(f"📊 Total Iterations: {len(results['iterations'])}")
        logger.info(f"✅ Phases Completed: {results.get('phases_completed', 0)}")
        logger.info(f"🎯 Score: {results.get('score', 0):.1f}")
        
        # Action breakdown
        actions = results.get('actions', [])
        action_counts = {}
        for a in actions:
            action_counts[a] = action_counts.get(a, 0) + 1
        
        logger.info("\n📈 Action Breakdown:")
        for action, count in sorted(action_counts.items()):
            logger.info(f"   {action}: {count}")
        
        metrics = results.get('metrics', {})
        if metrics:
            logger.info("\n📉 Metrics:")
            logger.info(f"   Precision: {metrics.get('precision', 0):.2f}")
            logger.info(f"   Recall: {metrics.get('recall', 0):.2f}")
            logger.info(f"   F1 Score: {metrics.get('f1_score', 0):.2f}")
        
        logger.info("\n" + "=" * 60)


def main():
    """Run quick marathon demo."""
    runner = QuickMarathonRunner(
        seed=42,
        use_mock_images=True,
        max_iterations=6  # 2 iterations per phase
    )
    
    results = runner.run()
    
    # Save results
    output_path = Path(__file__).parent.parent / "outputs" / "marathon_demo_results.json"
    output_path.parent.mkdir(exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    logger.info(f"\n📁 Results saved to: {output_path}")
    
    return 0 if results["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
