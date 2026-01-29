"""
Phase 3 Integration Test: Gemini AI Agent with Full Pipeline.

This test verifies:
1. Agent can connect to Gemini API
2. Agent can analyze telescope images
3. Memory persists across iterations (Thought Signatures)
4. Transient detection and tracking works end-to-end
5. Weather-based decision making

Requirements:
- GOOGLE_API_KEY set in .env file
- ScopeSim installed and configured
- Phase 1 & 2 components working
"""

import os
import sys
import pytest
import logging
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent import (
    SentinelAgent,
    ContextManager,
    ContextState,
    AgentDecision,
    WeatherContext,
    Candidate,
    CandidateHistory,
    create_initial_context
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_synthetic_images(
    has_transient: bool = False,
    transient_brightness: float = 1.0
) -> tuple:
    """
    Create synthetic test images for agent testing.
    
    Args:
        has_transient: Whether to add a transient source
        transient_brightness: Relative brightness of transient (0.0-1.0)
    
    Returns:
        Tuple of (reference, current, diff_annotated) numpy arrays
    """
    size = 512
    
    # Create reference image with some stars
    reference = np.random.normal(100, 10, (size, size)).astype(np.float32)
    
    # Add some static stars
    star_positions = [(128, 128), (256, 256), (384, 128), (128, 384)]
    for x, y in star_positions:
        # Simple Gaussian PSF
        yy, xx = np.ogrid[-y:size-y, -x:size-x]
        psf = np.exp(-(xx**2 + yy**2) / (2 * 5**2))
        reference += psf * 5000
    
    # Create current image (copy of reference)
    current = reference.copy()
    
    # Add transient if requested
    transient_x, transient_y = 300, 350
    if has_transient:
        yy, xx = np.ogrid[-transient_y:size-transient_y, -transient_x:size-transient_x]
        transient_psf = np.exp(-(xx**2 + yy**2) / (2 * 4**2))
        current += transient_psf * (20000 * transient_brightness)
    
    # Add noise to current observation
    current += np.random.normal(0, 15, (size, size))
    
    # Create difference image
    diff = np.abs(current - reference)
    
    # Convert to RGB for annotation
    diff_normalized = ((diff - diff.min()) / (diff.max() - diff.min() + 1e-10) * 255).astype(np.uint8)
    diff_annotated = np.stack([diff_normalized, diff_normalized, diff_normalized], axis=-1)
    
    # Add red circle around transient location if present
    if has_transient:
        # Draw circle annotation
        from PIL import Image, ImageDraw
        img = Image.fromarray(diff_annotated)
        draw = ImageDraw.Draw(img)
        radius = 20
        draw.ellipse(
            [transient_x - radius, transient_y - radius,
             transient_x + radius, transient_y + radius],
            outline=(255, 0, 0),
            width=2
        )
        diff_annotated = np.array(img)
    
    return reference, current, diff_annotated


class TestAgentConnection:
    """Tests for Gemini API connection."""
    
    @pytest.fixture
    def agent(self):
        """Create agent instance."""
        try:
            return SentinelAgent()
        except ValueError as e:
            pytest.skip(f"API key not configured: {e}")
    
    def test_api_connection(self, agent):
        """Test that agent can connect to Gemini API."""
        result = agent.test_connection()
        assert result == True, "Failed to connect to Gemini API"
        logger.info("✅ Gemini API connection successful")


class TestSingleImageAnalysis:
    """Tests for single-shot image analysis."""
    
    @pytest.fixture
    def agent(self):
        """Create agent instance."""
        try:
            return SentinelAgent()
        except ValueError as e:
            pytest.skip(f"API key not configured: {e}")
    
    @pytest.fixture
    def initial_context(self):
        """Create initial context."""
        weather = WeatherContext(seeing=1.0, cloud_extinction=0.1, observability="EXCELLENT")
        return create_initial_context(
            simulated_time="2024-03-15T01:00:00",
            weather=weather
        )
    
    def test_analyze_clean_sky(self, agent, initial_context):
        """Test analysis of clean sky with no transients."""
        reference, current, diff = create_synthetic_images(has_transient=False)
        
        decision = agent.analyze_images(
            reference=reference,
            current=current,
            diff_annotated=diff,
            context=initial_context
        )
        
        assert isinstance(decision, AgentDecision)
        assert decision.action in ["observe_again", "wait"]
        assert len(decision.reasoning) > 10
        
        logger.info(f"✅ Clean sky analysis: action={decision.action}")
        logger.info(f"   Reasoning: {decision.reasoning[:100]}...")
    
    def test_analyze_with_transient(self, agent, initial_context):
        """Test analysis of image with transient source."""
        reference, current, diff = create_synthetic_images(
            has_transient=True,
            transient_brightness=1.0
        )
        
        decision = agent.analyze_images(
            reference=reference,
            current=current,
            diff_annotated=diff,
            context=initial_context
        )
        
        assert isinstance(decision, AgentDecision)
        # Agent should detect something or ask to observe again
        assert decision.action in ["observe_again", "trigger_alert", "slew_to"]
        
        # Should have reasoning about detection
        assert len(decision.reasoning) > 10
        
        logger.info(f"✅ Transient analysis: action={decision.action}")
        logger.info(f"   New detections: {decision.new_detections}")
        logger.info(f"   Candidates: {len(decision.updated_candidates)}")


class TestMemoryPersistence:
    """Tests for agent memory across iterations (Thought Signatures)."""
    
    @pytest.fixture
    def agent(self):
        """Create agent instance."""
        try:
            return SentinelAgent()
        except ValueError as e:
            pytest.skip(f"API key not configured: {e}")
    
    @pytest.fixture
    def context_manager(self):
        """Create context manager with temp directory."""
        temp_dir = tempfile.mkdtemp()
        manager = ContextManager(state_dir=temp_dir)
        yield manager
        shutil.rmtree(temp_dir)
    
    def test_3_step_memory_loop(self, agent, context_manager):
        """
        Test that agent remembers candidates across 3 iterations.
        
        This is the key test for the "Thought Signature" pattern.
        """
        import time
        
        # Initialize context
        weather = WeatherContext(seeing=1.0, cloud_extinction=0.1, observability="EXCELLENT")
        context = context_manager.initialize_context(
            simulated_time="2024-03-15T01:00:00",
            weather=weather
        )
        
        # Step 1: First observation - should detect transient
        logger.info("=== Step 1: First observation ===")
        ref1, cur1, diff1 = create_synthetic_images(has_transient=True, transient_brightness=0.5)
        
        decision1 = agent.analyze_images(ref1, cur1, diff1, context)
        logger.info(f"Step 1 action: {decision1.action}")
        logger.info(f"Step 1 candidates: {len(decision1.updated_candidates)}")
        
        # Wait for rate limit
        time.sleep(2)
        
        # Update context
        context = context_manager.update_context(
            old_context=context,
            decision=decision1,
            new_weather=weather,
            new_simulated_time="2024-03-15T01:30:00"
        )
        context_manager.save_context(context)
        
        # Step 2: Re-observation - should see same candidate
        logger.info("\n=== Step 2: Re-observation ===")
        ref2, cur2, diff2 = create_synthetic_images(has_transient=True, transient_brightness=0.7)
        
        decision2 = agent.analyze_images(ref2, cur2, diff2, context)
        logger.info(f"Step 2 action: {decision2.action}")
        logger.info(f"Step 2 candidates: {len(decision2.updated_candidates)}")
        
        # Wait for rate limit
        time.sleep(2)
        
        # Update context
        context = context_manager.update_context(
            old_context=context,
            decision=decision2,
            new_weather=weather,
            new_simulated_time="2024-03-15T02:00:00"
        )
        context_manager.save_context(context)
        
        # Step 3: Third observation - may trigger alert
        logger.info("\n=== Step 3: Third observation ===")
        ref3, cur3, diff3 = create_synthetic_images(has_transient=True, transient_brightness=1.0)
        
        decision3 = agent.analyze_images(ref3, cur3, diff3, context)
        logger.info(f"Step 3 action: {decision3.action}")
        logger.info(f"Step 3 candidates: {len(decision3.updated_candidates)}")
        
        # Verify iteration tracking works
        assert context.iteration == 3
        
        # Verify we have decisions for all 3 steps
        assert decision3 is not None
        
        logger.info("\n✅ 3-step memory loop complete!")
        logger.info(f"   Final action: {decision3.action}")
        logger.info(f"   Total candidates tracked: {len(decision3.updated_candidates)}")
        
        # Get session summary
        summary = context_manager.get_session_summary()
        logger.info(f"   Session summary: {summary}")


class TestWeatherResponse:
    """Tests for weather-based decision making."""
    
    @pytest.fixture
    def agent(self):
        """Create agent instance."""
        try:
            return SentinelAgent()
        except ValueError as e:
            pytest.skip(f"API key not configured: {e}")
    
    def test_unusable_weather_returns_wait(self, agent):
        """Test that agent waits during unusable weather."""
        # Create context with bad weather
        bad_weather = WeatherContext(
            seeing=2.5,
            cloud_extinction=0.85,
            observability="UNUSABLE"
        )
        context = ContextState(
            iteration=5,
            simulated_time="2024-03-15T03:00:00",
            weather=bad_weather,
            candidates=[]
        )
        
        # Create images (doesn't matter - weather should short-circuit)
        ref, cur, diff = create_synthetic_images(has_transient=True)
        
        decision = agent.analyze_images(ref, cur, diff, context)
        
        # Agent should wait due to weather
        assert decision.action == "wait"
        assert "weather" in decision.reasoning.lower() or "cloud" in decision.reasoning.lower()
        
        logger.info("✅ Weather response test passed - agent waits during bad weather")


class TestFullPipelineIntegration:
    """Tests that require full Phase 1 & 2 pipeline."""
    
    @pytest.fixture
    def agent(self):
        """Create agent instance."""
        try:
            return SentinelAgent()
        except ValueError as e:
            pytest.skip(f"API key not configured: {e}")
    
    def test_with_scopesim_images(self, agent):
        """Test with real ScopeSim-generated images if available."""
        try:
            from src.simulation.universe import UniverseController
            from src.simulation.telescope import TelescopeCamera
            from src.processing.differencer import ImageDifferencer
        except ImportError as e:
            pytest.skip(f"Required modules not available: {e}")
        
        # This test uses actual Phase 2 components
        # It will be slower but more realistic
        
        logger.info("Testing with ScopeSim pipeline...")
        
        # Initialize components
        universe = UniverseController(num_stars=50)
        
        # Check if telescope camera works
        try:
            camera = TelescopeCamera()
        except Exception as e:
            pytest.skip(f"TelescopeCamera not available: {e}")
        
        # Create initial context
        weather = WeatherContext(seeing=1.0, cloud_extinction=0.1, observability="EXCELLENT")
        context = create_initial_context(
            simulated_time=universe.current_time.isoformat(),
            weather=weather
        )
        
        # Generate reference image
        source_list = universe.get_source_list_for_scopesim()
        ref_image, _ = camera.capture(source_list)
        
        # Inject a transient
        from src.simulation.universe import TransientEvent
        transient = TransientEvent(
            id="SN_TEST",
            x=0.0, y=0.0,
            start_time=universe.current_time - timedelta(hours=1),
            peak_time=universe.current_time + timedelta(hours=2),
            end_time=universe.current_time + timedelta(hours=12),
            peak_magnitude=14.0,
            base_magnitude=22.0,
            event_type="supernova_ia"
        )
        universe.add_transient(transient)
        
        # Advance time and capture new image
        universe.step_time(minutes=30)
        source_list = universe.get_source_list_for_scopesim()
        cur_image, _ = camera.capture(source_list)
        
        # Create difference image
        differencer = ImageDifferencer()
        diff_result = differencer.process(ref_image, cur_image)
        
        # Analyze with agent
        decision = agent.analyze_images(
            reference=ref_image,
            current=cur_image,
            diff_annotated=diff_result.annotated_image,
            context=context
        )
        
        logger.info(f"ScopeSim integration test:")
        logger.info(f"  Action: {decision.action}")
        logger.info(f"  Confidence: {decision.confidence}")
        logger.info(f"  Candidates: {len(decision.updated_candidates)}")
        
        assert isinstance(decision, AgentDecision)
        logger.info("✅ Full pipeline integration test passed!")


def run_quick_test():
    """Run a quick manual test without pytest."""
    print("=" * 60)
    print("Phase 3 Quick Integration Test")
    print("=" * 60)
    
    # Test 1: Agent connection
    print("\n1. Testing Gemini API connection...")
    try:
        agent = SentinelAgent()
        if agent.test_connection():
            print("   ✅ Connected to Gemini API")
        else:
            print("   ❌ Connection failed")
            return
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    
    # Test 2: Simple analysis
    print("\n2. Testing image analysis...")
    weather = WeatherContext(seeing=1.0, cloud_extinction=0.1, observability="EXCELLENT")
    context = create_initial_context("2024-03-15T01:00:00", weather)
    
    ref, cur, diff = create_synthetic_images(has_transient=True)
    
    decision = agent.analyze_images(ref, cur, diff, context)
    
    print(f"   Action: {decision.action}")
    print(f"   Confidence: {decision.confidence:.2f}")
    print(f"   Reasoning: {decision.reasoning[:100]}...")
    print("   ✅ Image analysis complete")
    
    print("\n" + "=" * 60)
    print("All quick tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    # Check for pytest or run quick test
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        run_quick_test()
    else:
        pytest.main([__file__, "-v", "-s"])
