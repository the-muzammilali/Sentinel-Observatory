"""
Unit tests for decision logging in Project Sentinel.

Tests structured logging for WAIT decisions, actions, and closures.

Run with: python -m pytest tests/test_decision_logging.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime

from src.agent.decision_log import (
    WaitReason, ActionType, DecisionLogEntry, DecisionLogger
)


class TestWaitReason:
    """Tests for WaitReason enum"""
    
    def test_all_reasons_have_values(self):
        """Each reason has a human-readable value"""
        for reason in WaitReason:
            assert len(reason.value) > 0
    
    def test_persistence_reasons_exist(self):
        """Persistence-related reasons are defined"""
        assert hasattr(WaitReason, 'INSUFFICIENT_PERSISTENCE')
        assert hasattr(WaitReason, 'PERSISTENCE_CHECK')
    
    def test_weather_reasons_exist(self):
        """Weather-related reasons are defined"""
        assert hasattr(WaitReason, 'WEATHER_UNCERTAINTY')
    
    def test_closure_reasons_exist(self):
        """Closure reasons are defined"""
        assert hasattr(WaitReason, 'NON_PERSISTENCE')
        assert hasattr(WaitReason, 'FALSE_POSITIVE_CONFIRMED')


class TestActionType:
    """Tests for ActionType enum"""
    
    def test_all_actions_defined(self):
        """All expected actions are defined"""
        assert ActionType.WAIT.value == "wait"
        assert ActionType.OBSERVE.value == "observe_again"
        assert ActionType.SLEW.value == "slew_to"
        assert ActionType.ALERT.value == "trigger_alert"
        assert ActionType.CLOSE_CANDIDATE.value == "close_candidate"


class TestDecisionLogEntry:
    """Tests for DecisionLogEntry dataclass"""
    
    @pytest.fixture
    def sample_entry(self):
        return DecisionLogEntry(
            timestamp="2025-01-01T12:00:00",
            action=ActionType.WAIT,
            reason_type=WaitReason.WEATHER_UNCERTAINTY,
            reason_detail="Clouds obscuring target",
            candidate_id="CAND_01",
            confidence=0.65
        )
    
    def test_to_dict(self, sample_entry):
        """to_dict returns correct structure"""
        d = sample_entry.to_dict()
        
        assert d["timestamp"] == "2025-01-01T12:00:00"
        assert d["action"] == "wait"
        assert d["reason_type"] == "WEATHER_UNCERTAINTY"
        assert d["candidate_id"] == "CAND_01"
        assert d["confidence"] == 0.65
    
    def test_to_human_readable_with_candidate(self, sample_entry):
        """Human readable format includes candidate ID"""
        msg = sample_entry.to_human_readable()
        
        assert "WAIT" in msg
        assert "CAND_01" in msg
        assert "Clouds obscuring target" in msg
    
    def test_to_human_readable_without_candidate(self):
        """Human readable format works without candidate"""
        entry = DecisionLogEntry(
            timestamp="2025-01-01T12:00:00",
            action=ActionType.WAIT,
            reason_type=WaitReason.BUDGET_EXHAUSTED,
            reason_detail="No follow-ups remaining"
        )
        msg = entry.to_human_readable()
        
        assert "WAIT" in msg
        assert "No follow-ups remaining" in msg


class TestDecisionLogger:
    """Tests for DecisionLogger class"""
    
    @pytest.fixture
    def logger(self):
        return DecisionLogger()
    
    def test_initial_state(self, logger):
        """Logger starts empty"""
        assert len(logger.history) == 0
    
    def test_log_wait(self, logger):
        """log_wait creates correct entry"""
        entry = logger.log_wait(
            reason=WaitReason.INSUFFICIENT_PERSISTENCE,
            detail="Candidate needs 3 observations, has 1",
            candidate_id="CAND_02",
            confidence=0.4
        )
        
        assert entry.action == ActionType.WAIT
        assert entry.reason_type == WaitReason.INSUFFICIENT_PERSISTENCE
        assert len(logger.history) == 1
    
    def test_log_wait_weather(self, logger):
        """log_wait with weather conditions"""
        entry = logger.log_wait(
            reason=WaitReason.WEATHER_UNCERTAINTY,
            detail="Seeing 3.5 arcsec",
            weather="POOR"
        )
        
        assert entry.weather_conditions == "POOR"
    
    def test_log_action(self, logger):
        """log_action creates correct entry"""
        entry = logger.log_action(
            action=ActionType.OBSERVE,
            target="CAND_03",
            detail="Re-observing to confirm detection"
        )
        
        assert entry.action == ActionType.OBSERVE
        assert entry.candidate_id == "CAND_03"
    
    def test_log_closure(self, logger):
        """log_closure creates correct entry"""
        entry = logger.log_closure(
            candidate_id="CAND_04",
            reason=WaitReason.NON_PERSISTENCE,
            detail="Candidate not seen in 3 follow-up observations",
            final_confidence=0.2
        )
        
        assert entry.action == ActionType.CLOSE_CANDIDATE
        assert entry.reason_type == WaitReason.NON_PERSISTENCE
    
    def test_history_accumulates(self, logger):
        """Multiple logs accumulate in history"""
        logger.log_wait(WaitReason.WEATHER_UNCERTAINTY, "Cloudy")
        logger.log_wait(WaitReason.PERSISTENCE_CHECK, "Waiting")
        logger.log_action(ActionType.OBSERVE, "CAND_01", "Observing")
        
        assert len(logger.history) == 3
    
    def test_history_size_limit(self, logger):
        """History respects max size"""
        logger.max_history = 10
        
        for i in range(15):
            logger.log_wait(WaitReason.COOLDOWN_PERIOD, f"Wait {i}")
        
        assert len(logger.history) == 10
    
    def test_get_wait_decisions(self, logger):
        """get_wait_decisions filters correctly"""
        logger.log_wait(WaitReason.WEATHER_UNCERTAINTY, "Cloudy")
        logger.log_action(ActionType.OBSERVE, "CAND_01", "Observing")
        logger.log_wait(WaitReason.PERSISTENCE_CHECK, "Waiting")
        
        waits = logger.get_wait_decisions()
        
        assert len(waits) == 2
        assert all(e.action == ActionType.WAIT for e in waits)
    
    def test_get_wait_summary(self, logger):
        """get_wait_summary counts by reason"""
        logger.log_wait(WaitReason.WEATHER_UNCERTAINTY, "Cloudy")
        logger.log_wait(WaitReason.WEATHER_UNCERTAINTY, "Still cloudy")
        logger.log_wait(WaitReason.PERSISTENCE_CHECK, "Waiting")
        
        summary = logger.get_wait_summary()
        
        assert summary["WEATHER_UNCERTAINTY"] == 2
        assert summary["PERSISTENCE_CHECK"] == 1
    
    def test_to_json(self, logger):
        """to_json produces valid JSON"""
        logger.log_wait(WaitReason.BUDGET_EXHAUSTED, "No budget")
        
        json_str = logger.to_json()
        
        assert "BUDGET_EXHAUSTED" in json_str
        assert "No budget" in json_str
    
    def test_clear(self, logger):
        """clear empties history"""
        logger.log_wait(WaitReason.COOLDOWN_PERIOD, "Wait")
        logger.clear()
        
        assert len(logger.history) == 0
    
    def test_get_decision_history_with_limit(self, logger):
        """get_decision_history respects limit"""
        for i in range(10):
            logger.log_wait(WaitReason.COOLDOWN_PERIOD, f"Wait {i}")
        
        history = logger.get_decision_history(limit=5)
        
        assert len(history) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
