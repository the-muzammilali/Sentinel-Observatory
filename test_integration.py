#!/usr/bin/env python3
"""
Integration test for all OODA loop improvements.

Tests:
1. False Positive Injection (#1)
2. Memory Manager (#8)
3. Ground Truth Tracker (#10)
4. Decision Logger (#6)
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.ooda_loop import OODALoop, LoopConfig
import logging

# Configure logging to see all details
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_integration():
    """Run a quick integration test with all improvements enabled."""
    
    logger.info("=" * 80)
    logger.info("INTEGRATION TEST - All OODA Loop Improvements")
    logger.info("=" * 80)
    logger.info("")
    
    # Create config with all improvements enabled
    config = LoopConfig(
        max_iterations=3,  # Quick test
        num_stars=50,  # Fewer stars for speed
        num_transients=2,  # Real transients
        num_false_positives=2,  # False positives (Improvement #1)
        inject_false_positives=True,  # Enable false positive injection
        enable_memory_manager=True,  # Enable memory hygiene (Improvement #8)
        enable_decision_logging=True,  # Enable decision logging (Improvement #6)
        real_time_delay=1.0,  # Shorter delay for testing
        random_seed=42
    )
    
    logger.info("Configuration:")
    logger.info(f"  - Iterations: {config.max_iterations}")
    logger.info(f"  - Transients: {config.num_transients}")
    logger.info(f"  - False Positives: {config.num_false_positives}")
    logger.info(f"  - Memory Manager: {config.enable_memory_manager}")
    logger.info(f"  - Decision Logger: {config.enable_decision_logging}")
    logger.info("")
    
    # Create and initialize loop
    loop = OODALoop(config)
    
    logger.info("Initializing OODA loop...")
    if not loop.initialize():
        logger.error("❌ Initialization failed!")
        return False
    
    logger.info("✅ Initialization successful!")
    logger.info("")
    
    # Verify all modules are initialized
    checks = {
        "Universe": loop._universe is not None,
        "Camera": loop._camera is not None,
        "Weather": loop._weather is not None,
        "Differencer": loop._differencer is not None,
        "Agent": loop._agent is not None,
        "Context Manager": loop._context_manager is not None,
        "Ground Truth Tracker": loop._ground_truth is not None,
        "Memory Manager": loop._memory_manager is not None,
        "Decision Logger": loop._decision_logger is not None,
    }
    
    logger.info("Module Initialization Check:")
    all_ok = True
    for module, status in checks.items():
        status_str = "✅" if status else "❌"
        logger.info(f"  {status_str} {module}: {'OK' if status else 'FAILED'}")
        if not status:
            all_ok = False
    logger.info("")
    
    if not all_ok:
        logger.error("❌ Some modules failed to initialize!")
        return False
    
    # Run the marathon
    try:
        logger.info("Running marathon...")
        result = loop.run_marathon()
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("INTEGRATION TEST RESULTS")
        logger.info("=" * 80)
        logger.info(f"✅ Marathon completed successfully!")
        logger.info(f"  - Total iterations: {result.total_iterations}")
        logger.info(f"  - Alerts triggered: {result.total_alerts_triggered}")
        logger.info(f"  - Candidates tracked: {result.total_candidates_tracked}")
        logger.info(f"  - Ground truth transients: {result.ground_truth_transients}")
        
        # Check ground truth metrics
        if loop._ground_truth:
            metrics = loop._ground_truth.get_metrics()
            logger.info("")
            logger.info("Ground Truth Metrics:")
            logger.info(f"  - Precision: {metrics.precision:.2%}")
            logger.info(f"  - Recall: {metrics.recall:.2%}")
            logger.info(f"  - F1 Score: {metrics.f1_score:.2%}")
        
        # Check memory manager stats
        if loop._memory_manager:
            mem_stats = loop._memory_manager.get_memory_stats()
            logger.info("")
            logger.info("Memory Manager Stats:")
            logger.info(f"  - Active candidates: {mem_stats.active_candidates}")
            logger.info(f"  - Archived candidates: {mem_stats.archived_candidates}")
            logger.info(f"  - Estimated tokens: {mem_stats.estimated_total_tokens}")
        
        # Check decision logger
        if loop._decision_logger:
            history_count = len(loop._decision_logger.history)
            logger.info("")
            logger.info("Decision Logger Stats:")
            logger.info(f"  - Total decisions logged: {history_count}")
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("✅ ALL INTEGRATION TESTS PASSED!")
        logger.info("=" * 80)
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Marathon failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        loop.cleanup()


if __name__ == "__main__":
    success = test_integration()
    sys.exit(0 if success else 1)

