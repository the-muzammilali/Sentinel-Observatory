"""
OODA Loop Orchestrator - Main control loop for Project Sentinel.

Implements the Observe-Orient-Decide-Act cycle for autonomous transient detection:
- OBSERVE: Capture telescope images using ScopeSim
- ORIENT: Process images through differencing pipeline
- DECIDE: Ask Gemini AI to analyze and decide
- ACT: Execute the agent's decision

This module ties together all Phase 1-3 components.
"""

import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum

import numpy as np

# Add parent directory to path for imports when running as script
_script_dir = Path(__file__).parent.parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Local imports
from src.simulation.universe import UniverseController, TransientType, ArtifactType
from src.simulation.telescope import TelescopeCamera, ObservationResult
from src.simulation.weather import WeatherSystem, WeatherConditions
from src.processing.differencer import ImageDifferencer, DiffResult
from src.agent import (
    SentinelAgent,
    ContextManager,
    ContextState,
    AgentDecision,
    WeatherContext,
    create_initial_context
)

# Improvement modules integration
from src.simulation.ground_truth import GroundTruthTracker, TransientType as GTTransientType
from src.agent.memory_manager import MemoryManager, MemoryConfig
from src.agent.decision_log import DecisionLogger


class LoopState(Enum):
    """Current state of the OODA loop."""
    INITIALIZING = "initializing"
    OBSERVING = "observing"
    ORIENTING = "orienting"
    DECIDING = "deciding"
    ACTING = "acting"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class LoopConfig:
    """Configuration for the OODA loop."""
    # Simulation settings
    field_size: float = 10.0  # arcseconds
    num_stars: int = 100
    random_seed: int = 42
    
    # Timing
    step_interval_hours: float = 0.5  # 30 minutes simulated time per iteration
    max_iterations: int = 16  # Standard marathon length
    real_time_delay: float = 2.0  # Seconds between iterations (for API rate limits)
    
    # Transient injection
    auto_inject_transients: bool = True
    num_transients: int = 3
    
    # False positive injection (Improvement #1)
    inject_false_positives: bool = True
    inject_false_positives: bool = True
    num_false_positives: int = 3  # Updated by API based on rate
    
    # Data paths
    state_dir: str = "data/agent_state"
    observation_dir: str = "data/observations"
    
    # Weather
    seeing_mean: float = 1.0
    cloud_mean: float = 0.2
    

    # Memory hygiene (Improvement #8)
    enable_memory_manager: bool = True
    memory_max_candidates: int = 50
    memory_stale_hours: float = 48.0
    
    # Decision logging (Improvement #6)
    enable_decision_logging: bool = True
    
    # Agent settings
    confirm_threshold: float = 0.8
    weather_enabled: bool = True


@dataclass
class IterationResult:
    """Result of a single OODA iteration."""
    iteration: int
    simulated_time: datetime
    weather: WeatherConditions
    decision: AgentDecision
    num_candidates: int
    num_detections: int
    duration_seconds: float
    error: Optional[str] = None


@dataclass
class MarathonResult:
    """Summary of a complete marathon run."""
    start_time: datetime
    end_time: datetime
    total_iterations: int
    total_alerts_triggered: int
    total_candidates_tracked: int
    ground_truth_transients: int
    detection_accuracy: Optional[float] = None
    iterations: List[IterationResult] = field(default_factory=list)


class OODALoop:
    """
    Main OODA loop orchestrator for Project Sentinel.
    
    Coordinates all components to run an autonomous observation marathon.
    """
    
    def __init__(self, config: Optional[LoopConfig] = None):
        """
        Initialize the OODA loop.
        
        Args:
            config: Loop configuration. Uses defaults if not provided.
        """
        self.config = config or LoopConfig()
        
        # Initialize state
        self.state = LoopState.INITIALIZING
        self.iteration = 0
        self.reference_image: Optional[np.ndarray] = None
        self.marathon_result: Optional[MarathonResult] = None
        
        # Create output directories
        Path(self.config.state_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.observation_dir).mkdir(parents=True, exist_ok=True)
        
        # Components (lazy initialized)
        self._universe: Optional[UniverseController] = None
        self._camera: Optional[TelescopeCamera] = None
        self._weather: Optional[WeatherSystem] = None
        self._differencer: Optional[ImageDifferencer] = None
        self._agent: Optional[SentinelAgent] = None
        self._context_manager: Optional[ContextManager] = None
        self._context: Optional[ContextState] = None
        
        # Improvement modules (lazy initialized)
        self._ground_truth: Optional[GroundTruthTracker] = None
        self._memory_manager: Optional[MemoryManager] = None
        self._decision_logger: Optional[DecisionLogger] = None
        
        logger.info("OODALoop initialized with config:")
        logger.info(f"  - Max iterations: {self.config.max_iterations}")
        logger.info(f"  - Step interval: {self.config.step_interval_hours} hours")
        logger.info(f"  - Auto inject transients: {self.config.auto_inject_transients}")
        logger.info(f"  - Inject false positives: {self.config.inject_false_positives}")
        logger.info(f"  - Memory manager: {self.config.enable_memory_manager}")
        logger.info(f"  - Decision logging: {self.config.enable_decision_logging}")
    
    def initialize(self) -> bool:
        """
        Initialize all components.
        
        Returns:
            True if initialization successful, False otherwise.
        """
        logger.info("=" * 60)
        logger.info("Initializing OODA Loop Components")
        logger.info("=" * 60)
        
        try:
            # 1. Initialize Universe
            logger.info("1. Initializing UniverseController...")
            self._universe = UniverseController(
                field_size=self.config.field_size,
                num_stars=self.config.num_stars,
                random_seed=self.config.random_seed
            )
            logger.info(f"   ✓ Universe created with {self.config.num_stars} stars")
            
            # Inject transients if configured
            if self.config.auto_inject_transients:
                self._inject_transients()
            
            # Inject false positives if configured (Improvement #1)
            if self.config.inject_false_positives:
                self._inject_false_positives()
            
            # 2. Initialize Telescope Camera
            logger.info("2. Initializing TelescopeCamera...")
            self._camera = TelescopeCamera()
            if not self._camera.initialize():
                raise RuntimeError("Failed to initialize telescope camera")
            logger.info("   ✓ MICADO instrument loaded")
            
            # 3. Initialize Weather System
            logger.info("3. Initializing WeatherSystem...")
            self._weather = WeatherSystem(
                seed=self.config.random_seed,
                seeing_mean=self.config.seeing_mean if self.config.weather_enabled else 0.5,  # Ideal seeing if disabled
                cloud_mean=self.config.cloud_mean if self.config.weather_enabled else 0.0     # Clear skies if disabled
            )
            if not self.config.weather_enabled:
                logger.info("   ⚠️ Weather simulation DISABLED (using ideal conditions)")
            logger.info("   ✓ Weather system ready")
            
            # 4. Initialize Image Differencer
            logger.info("4. Initializing ImageDifferencer...")
            self._differencer = ImageDifferencer(
                sigma_threshold=4.0,  # Detection threshold
                min_area=4,
                max_candidates=50
            )
            logger.info("   ✓ Differencer configured")
            
            # 5. Initialize Agent
            logger.info("5. Initializing SentinelAgent...")
            # TODO: Update Agent to accept confirm_threshold if supported, or handle in decision logic
            self._agent = SentinelAgent(
                confirm_threshold=self.config.confirm_threshold,
                temperature=0.2
            )
            if not self._agent.test_connection():
                raise RuntimeError("Failed to connect to Gemini API")
            logger.info("   ✓ Gemini connection verified")
            
            # 6. Initialize Context Manager
            logger.info("6. Initializing ContextManager...")
            self._context_manager = ContextManager(state_dir=self.config.state_dir)
            logger.info("   ✓ Context manager ready")
            
            # 7. Initialize Ground Truth Tracker (Improvement #10)
            logger.info("7. Initializing GroundTruthTracker...")
            self._ground_truth = GroundTruthTracker()
            # Register ALL transients (not just currently active) with ground truth
            for transient in self._universe.transients:
                # Map universe transient type to ground truth transient type
                event_type_str = transient.event_type.value if hasattr(transient.event_type, 'value') else str(transient.event_type)
                if "Ia" in event_type_str:
                    gt_type = GTTransientType.SN_IA
                elif "II" in event_type_str:
                    gt_type = GTTransientType.SN_II
                elif "nova" in event_type_str.lower():
                    gt_type = GTTransientType.NOVA
                else:
                    gt_type = GTTransientType.UNKNOWN

                # Access dataclass attributes directly (x, y in arcseconds)
                gt_ra = transient.x
                gt_dec = transient.y
                self._ground_truth.add_event(
                    event_type=gt_type,
                    ra=gt_ra,
                    dec=gt_dec,
                    appearance_time=transient.start_time.isoformat(),
                    peak_magnitude=transient.peak_magnitude,
                    is_real=True,
                    event_id=transient.id
                )
                # Convert to expected pixel position for debugging
                pixel_scale = self._universe.field_size / 1024.0
                expected_px = int((gt_ra / pixel_scale) + 512)
                expected_py = int((gt_dec / pixel_scale) + 512)
                logger.info(f"      - {transient.id}: sky ({gt_ra:.2f}, {gt_dec:.2f}) arcsec -> expected pixel ({expected_px}, {expected_py})")
            
            # Also register artifacts (false positives) for tracking
            for artifact in getattr(self._universe, 'artifacts', []):
                gt_ra = artifact.x
                gt_dec = artifact.y
                self._ground_truth.add_event(
                    event_type=GTTransientType.UNKNOWN,  # Artifact type
                    ra=gt_ra,
                    dec=gt_dec,
                    appearance_time=artifact.artifact_time.isoformat(),  # artifact_time not start_time
                    peak_magnitude=artifact.brightness_magnitude,  # brightness_magnitude not magnitude
                    is_real=False,  # This is a FALSE POSITIVE source
                    event_id=artifact.id
                )
                pixel_scale = self._universe.field_size / 1024.0
                expected_px = int((gt_ra / pixel_scale) + 512)
                expected_py = int((gt_dec / pixel_scale) + 512)
                logger.info(f"      - {artifact.id} (artifact): sky ({gt_ra:.2f}, {gt_dec:.2f}) arcsec -> expected pixel ({expected_px}, {expected_py})")
            logger.info(f"   ✓ Ground truth tracker ready ({len(self._ground_truth.events)} events)")
            
            # 8. Initialize Memory Manager (Improvement #8)
            if self.config.enable_memory_manager:
                logger.info("8. Initializing MemoryManager...")
                memory_config = MemoryConfig(
                    max_active_candidates=self.config.memory_max_candidates,
                    stale_threshold_hours=self.config.memory_stale_hours
                )
                self._memory_manager = MemoryManager(config=memory_config)
                logger.info("   ✓ Memory manager ready")
            
            # 9. Initialize Decision Logger (Improvement #6)
            if self.config.enable_decision_logging:
                logger.info("9. Initializing DecisionLogger...")
                self._decision_logger = DecisionLogger()
                logger.info("   ✓ Decision logger ready")
            
            # 10. Capture reference image
            logger.info("10. Capturing reference image...")
            self.reference_image = self._capture_reference()
            logger.info(f"   ✓ Reference image captured: {self.reference_image.shape}")
            
            # 11. Initialize context state
            logger.info("11. Initializing context state...")
            weather_conditions = self._weather.get_conditions()
            weather_context = WeatherContext.from_weather_system(
                seeing=weather_conditions.seeing,
                cloud_extinction=weather_conditions.cloud_extinction
            )
            self._context = self._context_manager.initialize_context(
                simulated_time=self._universe.current_time.isoformat(),
                weather=weather_context
            )
            logger.info("   ✓ Context initialized")
            
            # 12. Start observation session for long-context reasoning
            logger.info("12. Starting observation session...")
            self._agent.start_observation_session(self._context)
            logger.info("   ✓ Observation session ready")
            
            self.state = LoopState.PAUSED
            logger.info("")
            logger.info("=" * 60)
            logger.info("✅ All components initialized successfully!")
            logger.info("=" * 60)
            return True
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            self.state = LoopState.ERROR
            import traceback
            traceback.print_exc()
            return False
    
    def _inject_transients(self):
        """Inject random transients into the universe."""
        import random
        random.seed(self.config.random_seed + 100)  # Different seed for transients
        
        logger.info(f"   Injecting {self.config.num_transients} transients...")
        
        for i in range(self.config.num_transients):
            # Random position within field
            x = random.uniform(-self.config.field_size/2 * 0.8, self.config.field_size/2 * 0.8)
            y = random.uniform(-self.config.field_size/2 * 0.8, self.config.field_size/2 * 0.8)
            
            # Random timing - first transient starts immediately, others staggered
            if i == 0:
                start_offset = 0.0  # First transient visible from start
            else:
                start_offset = random.uniform(0.5, 3.0)  # hours from now
            duration = random.uniform(6.0, 12.0)  # hours
            
            # Random brightness
            peak_mag = random.uniform(16.0, 19.0)  # Bright enough to detect
            
            # Random type
            event_type = random.choice([
                TransientType.SUPERNOVA_IA,
                TransientType.SUPERNOVA_II,
                TransientType.NOVA
            ])
            
            self._universe.add_transient(
                x=x, y=y,
                start_offset_hours=start_offset,
                duration_hours=duration,
                peak_magnitude=peak_mag,
                event_type=event_type
            )
            
            logger.info(f"   - Transient {i+1}: {event_type.value} at ({x:.2f}, {y:.2f}), "
                       f"peak mag={peak_mag:.1f}, starts in {start_offset:.1f}h")

    def _inject_false_positives(self):
        """Inject false positive artifacts into the universe."""
        logger.info(f"   Injecting {self.config.num_false_positives} false positive artifacts...")

        # Use universe's built-in false positive cluster injection
        artifacts = self._universe.inject_false_positive_cluster(
            n_artifacts=self.config.num_false_positives
        )

        logger.info(f"   ✓ Injected {len(artifacts)} false positive artifacts")

    def _pixel_to_sky(self, pixel_x: int, pixel_y: int) -> Tuple[float, float]:
        """
        Convert pixel coordinates to sky coordinates (arcseconds).

        The universe uses a coordinate system centered at (0, 0) with
        field_size in arcseconds. The image is 1024x1024 pixels centered
        at pixel (512, 512).

        Args:
            pixel_x: X pixel coordinate (0-1024)
            pixel_y: Y pixel coordinate (0-1024)

        Returns:
            Tuple of (sky_x, sky_y) in arcseconds (same units as universe)
        """
        # Image center corresponds to (0, 0) in sky coordinates
        center_pixel = 512

        # Calculate pixel scale (arcseconds per pixel)
        pixel_scale = self._universe.field_size / 1024.0

        # Convert to sky coordinates
        sky_x = (pixel_x - center_pixel) * pixel_scale
        sky_y = (pixel_y - center_pixel) * pixel_scale

        return sky_x, sky_y

    def _capture_reference(self) -> np.ndarray:
        """Capture reference image (before any transients)."""
        # Get source list (just static stars for reference)
        source = self._universe.get_source_list_for_scopesim()
        
        # Capture observation
        result = self._camera.observe(source)
        
        # Save reference
        ref_path = Path(self.config.observation_dir) / "reference"
        self._camera.save_observation(result, str(ref_path))
        
        return result.image_data
    
    def run_iteration(self) -> IterationResult:
        """
        Run a single OODA iteration.
        
        Returns:
            IterationResult with details of this iteration.
        """
        start_time = time.time()
        self.iteration += 1
        
        logger.info("")
        logger.info(f"{'='*60}")
        logger.info(f"ITERATION {self.iteration}: {self._universe.current_time.strftime('%H:%M:%S')}")
        logger.info(f"{'='*60}")
        
        try:
            # ============ OBSERVE ============
            self.state = LoopState.OBSERVING
            logger.info("📷 OBSERVE: Capturing current observation...")
            
            # Step time forward
            self._universe.step_time(hours=self.config.step_interval_hours)
            weather_conditions = self._weather.step(hours=self.config.step_interval_hours)
            
            # Apply weather to telescope
            self._camera.set_seeing(weather_conditions.seeing)
            self._camera.set_cloud_extinction(weather_conditions.cloud_extinction)
            
            # Capture observation
            source = self._universe.get_source_list_for_scopesim()
            observation = self._camera.observe(source)
            current_image = observation.image_data
            
            logger.info(f"   Weather: seeing={weather_conditions.seeing:.2f}\", "
                       f"clouds={weather_conditions.cloud_extinction:.2f}")
            
            # ============ ORIENT ============
            self.state = LoopState.ORIENTING
            logger.info("🔍 ORIENT: Processing difference image...")
            
            diff_result = self._differencer.process(
                reference=self.reference_image,
                current=current_image
            )
            
            num_detections = len(diff_result.candidate_regions)
            logger.info(f"   Detected {num_detections} candidate regions")
            
            # Debug: Log detected candidate positions vs ground truth
            for cand in diff_result.candidate_regions[:5]:  # First 5
                sky_x, sky_y = self._pixel_to_sky(cand.x, cand.y)
                logger.debug(f"   Differencer candidate: pixel ({cand.x}, {cand.y}) -> sky ({sky_x:.3f}, {sky_y:.3f}) arcsec, sig={cand.significance:.1f}σ")
            
            # Save observation and diff
            obs_path = Path(self.config.observation_dir) / f"iteration_{self.iteration:03d}"
            self._camera.save_observation(observation, str(obs_path))
            
            # ============ DECIDE ============
            self.state = LoopState.DECIDING
            logger.info("🧠 DECIDE: Analyzing with Gemini...")
            
            # Update weather context
            weather_context = WeatherContext.from_weather_system(
                seeing=weather_conditions.seeing,
                cloud_extinction=weather_conditions.cloud_extinction
            )
            # Create updated context with new weather
            self._context = ContextState(
                iteration=self._context.iteration,
                simulated_time=self._context.simulated_time,
                current_focus=self._context.current_focus,
                weather=weather_context,
                candidates=self._context.candidates,
                alerts_triggered=self._context.alerts_triggered,
                last_action_reasoning=self._context.last_action_reasoning,
                total_observations=self._context.total_observations
            )
            
            # Call agent
            decision = self._agent.analyze_images(
                reference=self.reference_image,
                current=current_image,
                diff_annotated=diff_result.annotated_image,
                context=self._context
            )
            
            logger.info(f"   Decision: {decision.action} (confidence: {decision.confidence:.2f})")
            logger.info(f"   Reasoning: {decision.reasoning[:100]}...")

            # Track detections with ground truth (Improvement #10)
            if self._ground_truth and decision.updated_candidates:
                for candidate in decision.updated_candidates:
                    # Convert pixel coordinates to sky coordinates
                    if hasattr(candidate, 'x') and hasattr(candidate, 'y'):
                        sky_x, sky_y = self._pixel_to_sky(candidate.x, candidate.y)

                        matched_event = self._ground_truth.record_detection(
                            candidate_id=candidate.id,
                            ra=sky_x,
                            dec=sky_y,
                            detection_time=self._universe.current_time.isoformat()
                        )
                        if matched_event:
                            logger.debug(f"   Ground truth: Candidate {candidate.id} at ({sky_x:.2f}, {sky_y:.2f}) matched event {matched_event}")

            # ============ ACT ============
            self.state = LoopState.ACTING
            logger.info("⚡ ACT: Executing decision...")
            
            # Update context based on decision
            self._context = self._context_manager.update_context(
                old_context=self._context,
                decision=decision,
                new_weather=weather_context,
                new_simulated_time=self._universe.current_time.isoformat()
            )
            
            # Save context
            self._context_manager.save_context(self._context)

            # Apply memory hygiene if enabled (Improvement #8)
            if self._memory_manager and self._context:
                # Get archived candidates from context (or initialize empty list)
                archived = getattr(self._context, 'archived_candidates', [])

                # Apply hygiene to prune stale candidates and manage memory
                pruned_candidates, updated_archived, mem_stats = self._memory_manager.apply_hygiene(
                    candidates=self._context.candidates,
                    archived=archived,
                    current_time=self._universe.current_time
                )

                # Update context with pruned candidates
                self._context.candidates = pruned_candidates
                # Store archived candidates back (if context supports it)
                if hasattr(self._context, 'archived_candidates'):
                    self._context.archived_candidates = updated_archived

                logger.info(f"   Memory hygiene: {mem_stats.active_candidates} active, "
                           f"{mem_stats.archived_candidates} archived, "
                           f"~{mem_stats.estimated_total_tokens} tokens")

            # Act on decision
            self._execute_action(decision)

            # Calculate duration
            duration = time.time() - start_time
            
            # Log summary
            num_candidates = len(decision.updated_candidates)
            logger.info(f"   ✓ Iteration complete in {duration:.1f}s")
            logger.info(f"   Tracking {num_candidates} candidates")
            
            # Check if alert was triggered
            if decision.action == "trigger_alert":
                logger.info(f"   🚨 ALERT TRIGGERED!")
            
            return IterationResult(
                iteration=self.iteration,
                simulated_time=self._universe.current_time,
                weather=weather_conditions,
                decision=decision,
                num_candidates=num_candidates,
                num_detections=num_detections,
                duration_seconds=duration
            )
            
        except Exception as e:
            logger.error(f"Iteration {self.iteration} failed: {e}")
            import traceback
            traceback.print_exc()
            
            return IterationResult(
                iteration=self.iteration,
                simulated_time=self._universe.current_time,
                weather=self._weather.get_conditions(),
                decision=None,
                num_candidates=0,
                num_detections=0,
                duration_seconds=time.time() - start_time,
                error=str(e)
            )
    
    def _execute_action(self, decision: AgentDecision):
        """
        Execute the agent's decision.

        Args:
            decision: The decision from the agent.
        """
        # Import decision logger types if needed
        from src.agent.decision_log import ActionType, WaitReason

        if decision.action == "observe_again":
            logger.info("   → Will re-observe current field")

            # Log decision (Improvement #6)
            if self._decision_logger:
                self._decision_logger.log_action(
                    action=ActionType.OBSERVE,
                    detail=decision.reasoning,
                    confidence=decision.confidence
                )

        elif decision.action == "slew_to":
            if decision.target_coordinates:
                x, y = decision.target_coordinates
                logger.info(f"   → Slewing to coordinates ({x:.2f}, {y:.2f})")

                # Log decision (Improvement #6)
                if self._decision_logger:
                    self._decision_logger.log_action(
                        action=ActionType.SLEW,
                        target=f"({x:.2f}, {y:.2f})",
                        detail=decision.reasoning,
                        confidence=decision.confidence
                    )

        elif decision.action == "trigger_alert":
            logger.info("   → 🚨 ALERT TRIGGERED!")

            # Track alert with ground truth (Improvement #10)
            if self._ground_truth and decision.updated_candidates:
                candidate = decision.updated_candidates[0]

                # Get coordinates - convert from pixels to sky if needed
                if decision.target_coordinates:
                    # IMPORTANT: target_coordinates from agent are raw pixel values, need conversion
                    pixel_x, pixel_y = decision.target_coordinates
                    sky_x, sky_y = self._pixel_to_sky(int(pixel_x), int(pixel_y))
                    logger.debug(f"   Alert coords from target_coordinates: pixel ({pixel_x}, {pixel_y}) -> sky ({sky_x:.3f}, {sky_y:.3f})")
                elif hasattr(candidate, 'x') and hasattr(candidate, 'y'):
                    # Convert pixel coordinates to sky coordinates
                    sky_x, sky_y = self._pixel_to_sky(candidate.x, candidate.y)
                    logger.debug(f"   Alert coords from candidate: pixel ({candidate.x}, {candidate.y}) -> sky ({sky_x:.3f}, {sky_y:.3f})")
                elif hasattr(candidate, 'ra') and hasattr(candidate, 'dec'):
                    # Already in sky coordinates
                    sky_x, sky_y = candidate.ra, candidate.dec
                    logger.debug(f"   Alert coords already in sky: ({sky_x:.3f}, {sky_y:.3f})")
                else:
                    sky_x, sky_y = None, None
                    logger.warning("   Alert has no usable coordinates!")

                if sky_x is not None and sky_y is not None:
                    # Debug: show pixel->sky conversion
                    if hasattr(candidate, 'x') and hasattr(candidate, 'y'):
                        logger.debug(f"   Pixel ({candidate.x}, {candidate.y}) -> Sky ({sky_x:.3f}, {sky_y:.3f}) arcsec")
                    
                    is_true_positive = self._ground_truth.record_alert(
                        candidate_id=candidate.id,
                        ra=sky_x,
                        dec=sky_y,
                        alert_time=self._universe.current_time.isoformat()
                    )

                    logger.info(f"   Ground truth: {'✓ TRUE POSITIVE' if is_true_positive else '✗ FALSE POSITIVE'} "
                               f"at sky ({sky_x:.2f}, {sky_y:.2f}) arcsec")

            # Log decision (Improvement #6)
            if self._decision_logger:
                self._decision_logger.log_action(
                    action=ActionType.ALERT,
                    detail=decision.reasoning,
                    confidence=decision.confidence
                )

        elif decision.action == "wait":
            logger.info("   → Waiting due to conditions")

            # Log wait decision with reasoning (Improvement #6)
            if self._decision_logger:
                # Determine wait reason from decision reasoning
                wait_reason = WaitReason.CONFIDENCE_TOO_LOW
                if "weather" in decision.reasoning.lower():
                    wait_reason = WaitReason.WEATHER_UNCERTAINTY
                elif "persistence" in decision.reasoning.lower():
                    wait_reason = WaitReason.PERSISTENCE_CHECK

                weather_str = None
                if self._weather:
                    conditions = self._weather.get_conditions()
                    weather_str = f"seeing={conditions.seeing:.2f}\", clouds={conditions.cloud_extinction:.2f}"

                self._decision_logger.log_wait(
                    reason=wait_reason,
                    detail=decision.reasoning,
                    confidence=decision.confidence,
                    weather=weather_str
                )
    
    def run_marathon(self) -> MarathonResult:
        """
        Run a complete observation marathon.
        
        Returns:
            MarathonResult with summary of the marathon.
        """
        logger.info("")
        logger.info("=" * 70)
        logger.info("    PROJECT SENTINEL - MARATHON OBSERVATION RUN    ")
        logger.info("=" * 70)
        logger.info("")
        
        start_time = datetime.now()
        iterations = []
        
        try:
            for i in range(self.config.max_iterations):
                result = self.run_iteration()
                iterations.append(result)
                
                if result.error:
                    logger.warning(f"Iteration {i+1} had error: {result.error}")
                
                # Rate limiting delay
                if i < self.config.max_iterations - 1:
                    time.sleep(self.config.real_time_delay)
            
            end_time = datetime.now()
            
            # Calculate summary statistics
            total_alerts = sum(
                1 if (r.decision and r.decision.action == "trigger_alert") else 0
                for r in iterations
            )
            
            final_candidates = len(self._context.candidates) if self._context else 0
            ground_truth = len(self._universe.get_ground_truth()["active_transients"])
            
            # Calculate detection accuracy
            accuracy = None
            if ground_truth > 0:
                confirmed = sum(
                    1 for c in self._context.candidates 
                    if c.status in ("BRIGHTENING", "ALERTED")
                ) if self._context else 0
                accuracy = confirmed / ground_truth
            
            # Finalize ground truth metrics (Improvement #10)
            if self._ground_truth:
                final_metrics = self._ground_truth.finalize_metrics()
                logger.info("")
                logger.info("=" * 70)
                logger.info("Ground Truth Evaluation Metrics:")
                logger.info(f"  Precision: {final_metrics.precision:.2%}")
                logger.info(f"  Recall: {final_metrics.recall:.2%}")
                logger.info(f"  F1 Score: {final_metrics.f1_score:.2%}")
                logger.info(f"  True Positives: {final_metrics.true_positives}")
                logger.info(f"  False Positives: {final_metrics.false_positives}")
                logger.info(f"  False Negatives: {final_metrics.false_negatives}")
                if final_metrics.mean_latency_hours > 0:
                    logger.info(f"  Mean Alert Latency: {final_metrics.mean_latency_hours:.2f} hours")
                logger.info("=" * 70)

            marathon_result = MarathonResult(
                start_time=start_time,
                end_time=end_time,
                total_iterations=len(iterations),
                total_alerts_triggered=total_alerts,
                total_candidates_tracked=final_candidates,
                ground_truth_transients=ground_truth,
                detection_accuracy=accuracy,
                iterations=iterations
            )

            self.marathon_result = marathon_result
            self._print_marathon_summary(marathon_result)
            
            return marathon_result
            
        except KeyboardInterrupt:
            logger.info("\n⚠️ Marathon interrupted by user")
            self.state = LoopState.STOPPED
            raise
    
    def _print_marathon_summary(self, result: MarathonResult):
        """Print a summary of the marathon run."""
        logger.info("")
        logger.info("=" * 70)
        logger.info("    MARATHON COMPLETE - SUMMARY    ")
        logger.info("=" * 70)
        logger.info("")
        logger.info(f"Duration: {result.end_time - result.start_time}")
        logger.info(f"Total iterations: {result.total_iterations}")
        logger.info(f"Alerts triggered: {result.total_alerts_triggered}")
        logger.info(f"Candidates tracked: {result.total_candidates_tracked}")
        logger.info(f"Ground truth transients: {result.ground_truth_transients}")
        
        if result.detection_accuracy is not None:
            logger.info(f"Detection accuracy: {result.detection_accuracy:.1%}")
        
        # Session summary from context manager
        if self._context_manager:
            summary = self._context_manager.get_session_summary()
            logger.info("")
            logger.info("Session details:")
            for key, value in summary.items():
                logger.info(f"  {key}: {value}")
        
        logger.info("")
        logger.info("=" * 70)
    
    def get_ground_truth(self) -> Dict[str, Any]:
        """Get the ground truth for scoring."""
        if self._universe:
            return self._universe.get_ground_truth()
        return {}
    
    def get_context(self) -> Optional[ContextState]:
        """Get the current context state."""
        return self._context
    
    def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up OODA loop resources...")
        
        # End observation session and get conversation history
        if hasattr(self, '_agent') and self._agent:
            history = self._agent.end_observation_session()
            if history:
                logger.info(f"Observation session ended: {len(history)} observations logged")
        
        self.state = LoopState.STOPPED


def create_loop(config: Optional[LoopConfig] = None) -> OODALoop:
    """
    Factory function to create an OODA loop.
    
    Args:
        config: Optional configuration.
    """
    return OODALoop(config)


def run_quick_test(iterations: int = 3):
    """
    Run a quick test with reduced iterations.
    
    Args:
        iterations: Number of iterations to run.
    """
    config = LoopConfig(
        max_iterations=iterations,
        num_stars=50,  # Fewer stars for speed
        num_transients=2,
        real_time_delay=2.5  # Slightly longer delay for API
    )
    
    loop = create_loop(config)
    
    if not loop.initialize():
        logger.error("Failed to initialize loop")
        return None
    
    try:
        result = loop.run_marathon()
        return result
    except KeyboardInterrupt:
        logger.info("Test interrupted")
        return None
    finally:
        loop.cleanup()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Project Sentinel OODA Loop")
    parser.add_argument("--iterations", "-n", type=int, default=16,
                       help="Number of iterations (default: 16)")
    parser.add_argument("--quick", "-q", action="store_true",
                       help="Quick test mode (3 iterations)")
    parser.add_argument("--stars", "-s", type=int, default=100,
                       help="Number of stars (default: 100)")
    parser.add_argument("--transients", "-t", type=int, default=3,
                       help="Number of transients to inject (default: 3)")
    
    args = parser.parse_args()
    
    if args.quick:
        run_quick_test()
    else:
        config = LoopConfig(
            max_iterations=args.iterations,
            num_stars=args.stars,
            num_transients=args.transients
        )
        loop = create_loop(config)
        
        if loop.initialize():
            try:
                loop.run_marathon()
            except KeyboardInterrupt:
                print("\n⚠️ Interrupted by user")
            finally:
                loop.cleanup()
        else:
            print("❌ Failed to initialize. Check logs for details.")
