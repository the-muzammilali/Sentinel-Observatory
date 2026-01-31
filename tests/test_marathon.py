"""
Unit tests for marathon orchestrator.

Tests phase transitions, ground truth integration, and scoring.

Run with: python -m pytest tests/test_marathon.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime, timedelta

from src.simulation.marathon import (
    MarathonPhase, PhaseConfig, MarathonResult, MarathonOrchestrator,
    STANDARD_MARATHON, create_standard_marathon, create_quick_demo
)


class TestMarathonPhase:
    """Tests for MarathonPhase enum"""
    
    def test_all_phases_exist(self):
        """All expected phases exist"""
        assert MarathonPhase.QUIET.value == "quiet"
        assert MarathonPhase.FALSE_POSITIVE_CLUSTER.value == "false_positive_cluster"
        assert MarathonPhase.CONFIRMATION.value == "confirmation"
        assert MarathonPhase.COMPLETE.value == "complete"


class TestPhaseConfig:
    """Tests for PhaseConfig dataclass"""
    
    def test_default_values(self):
        """Default values are reasonable"""
        config = PhaseConfig(
            phase_type=MarathonPhase.QUIET,
            duration_hours=2.0
        )
        
        assert config.cloud_range == (0.0, 0.2)
        assert config.inject_transients == 0
    
    def test_to_dict(self):
        """to_dict returns complete structure"""
        config = PhaseConfig(
            phase_type=MarathonPhase.CONFIRMATION,
            duration_hours=1.0,
            expected_action="alert"
        )
        
        d = config.to_dict()
        assert d["phase_type"] == "confirmation"
        assert d["expected_action"] == "alert"


class TestStandardMarathon:
    """Tests for STANDARD_MARATHON config"""
    
    def test_has_six_phases(self):
        """Standard marathon has 6 phases"""
        assert len(STANDARD_MARATHON) == 6
    
    def test_correct_order(self):
        """Phases are in correct order"""
        types = [p.phase_type for p in STANDARD_MARATHON]
        
        assert types[0] == MarathonPhase.QUIET
        assert types[1] == MarathonPhase.FALSE_POSITIVE_CLUSTER
        assert types[2] == MarathonPhase.WEATHER_DEGRADATION
        assert types[3] == MarathonPhase.WEATHER_RECOVERY
        assert types[4] == MarathonPhase.COMPETING_CANDIDATES
        assert types[5] == MarathonPhase.CONFIRMATION
    
    def test_total_duration(self):
        """Total duration is 10 hours"""
        total = sum(p.duration_hours for p in STANDARD_MARATHON)
        assert total == 10.0


class TestMarathonOrchestrator:
    """Tests for MarathonOrchestrator"""
    
    @pytest.fixture
    def orchestrator(self):
        return create_standard_marathon(seed=42)
    
    @pytest.fixture
    def quick_orchestrator(self):
        return create_quick_demo(seed=42)
    
    def test_creation(self, orchestrator):
        """Orchestrator can be created"""
        assert orchestrator is not None
        assert len(orchestrator.phases) == 6
    
    def test_start(self, orchestrator):
        """Marathon can be started"""
        start_time = datetime(2025, 1, 1, 0, 0, 0)
        orchestrator.start(start_time)
        
        assert orchestrator.marathon_start_time == start_time
        assert orchestrator.iteration_count == 0
        assert not orchestrator.is_complete
    
    def test_current_phase(self, orchestrator):
        """Current phase is accessible"""
        orchestrator.start()
        
        phase = orchestrator.current_phase
        assert phase.phase_type == MarathonPhase.QUIET
    
    def test_tick_returns_state(self, orchestrator):
        """Tick returns current state"""
        orchestrator.start()
        state = orchestrator.tick(datetime.now())
        
        assert "phase" in state
        assert "cloud_range" in state
        assert "iteration" in state
    
    def test_phase_transition(self, orchestrator):
        """Phases transition correctly"""
        start = datetime(2025, 1, 1, 0, 0, 0)
        orchestrator.start(start)
        
        # First phase is QUIET (2 hours)
        assert orchestrator.current_phase.phase_type == MarathonPhase.QUIET
        
        # After 2 hours, should transition
        after_phase1 = start + timedelta(hours=2, minutes=1)
        orchestrator.tick(after_phase1)
        
        assert orchestrator.current_phase.phase_type == MarathonPhase.FALSE_POSITIVE_CLUSTER
    
    def test_marathon_completion(self, quick_orchestrator):
        """Marathon completes after all phases"""
        start = datetime(2025, 1, 1, 0, 0, 0)
        quick_orchestrator.start(start)
        
        # Quick demo has 3 phases - need to tick through each
        # Phase 1: 0.5h, Phase 2: 1.0h, Phase 3: 0.5h = 2.0h total
        for hours in [0.6, 1.6, 2.5]:
            t = start + timedelta(hours=hours)
            quick_orchestrator.tick(t)
        
        assert quick_orchestrator.is_complete
    
    def test_record_action(self, orchestrator):
        """Actions can be recorded"""
        orchestrator.start()
        orchestrator.record_action(
            action="wait",
            time=datetime.now()
        )
        
        result = orchestrator.finalize()
        assert len(result.events_log) > 1  # Start + action
    
    def test_finalize(self, orchestrator):
        """Finalize returns complete result"""
        orchestrator.start()
        orchestrator.tick(datetime.now())
        
        result = orchestrator.finalize()
        
        assert isinstance(result, MarathonResult)
        assert result.total_iterations >= 1
    
    def test_scoring(self, orchestrator):
        """Score calculation works"""
        orchestrator.start()
        
        # Import TransientType for proper enum usage
        from src.simulation.ground_truth import TransientType
        
        # Add a ground truth event
        orchestrator.ground_truth.add_event(
            event_type=TransientType.SN_IA,
            ra=180.0, dec=45.0,
            appearance_time="2025-01-01T00:00:00"
        )
        
        # Record an alert on it
        orchestrator.record_action(
            action="trigger_alert",
            candidate_id="CAND_01",
            ra=180.0, dec=45.0,
            time=datetime(2025, 1, 1, 1, 0, 0)
        )
        
        result = orchestrator.finalize()
        
        # Should have positive score from TP
        assert result.score > 0
    
    def test_get_status(self, orchestrator):
        """Status is accessible"""
        orchestrator.start()
        status = orchestrator.get_status()
        
        assert "phase" in status
        assert "is_complete" in status
        assert status["phase"] == "quiet"
    
    def test_get_progress(self, orchestrator):
        """Progress tracking works"""
        orchestrator.start()
        
        progress = orchestrator.get_progress()
        assert progress == 0.0
        
        # Advance to second phase
        orchestrator.current_phase_idx = 3
        progress = orchestrator.get_progress()
        assert progress == 50.0


class TestMarathonResult:
    """Tests for MarathonResult dataclass"""
    
    def test_to_dict(self):
        """to_dict returns complete structure"""
        result = MarathonResult(
            total_iterations=100,
            total_duration_hours=10.0,
            phases_completed=6,
            current_phase="complete",
            score=85.5
        )
        
        d = result.to_dict()
        assert d["total_iterations"] == 100
        assert d["score"] == 85.5


class TestConvenienceFunctions:
    """Tests for convenience functions"""
    
    def test_create_standard_marathon(self):
        """Standard marathon creation works"""
        marathon = create_standard_marathon()
        assert len(marathon.phases) == 6
    
    def test_create_quick_demo(self):
        """Quick demo creation works"""
        demo = create_quick_demo()
        assert len(demo.phases) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
