"""
Unit tests for confidence dynamics in Project Sentinel.

Tests decay, boost, regression, and trend analysis.

Run with: python -m pytest tests/test_confidence_dynamics.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime, timedelta

from src.agent.confidence import ConfidenceDynamics, ConfidenceTracker
from src.agent.models import Candidate, CandidateHistory


class TestConfidenceDynamics:
    """Tests for ConfidenceDynamics class"""
    
    @pytest.fixture
    def dynamics(self):
        return ConfidenceDynamics()
    
    def test_default_values(self, dynamics):
        """Check sensible defaults"""
        assert dynamics.decay_rate_per_hour == 0.05
        assert dynamics.max_confidence == 0.95
        assert dynamics.min_confidence == 0.05
    
    def test_decay_reduces_confidence(self, dynamics):
        """Decay should reduce confidence over time"""
        new_conf, reason = dynamics.apply_decay(0.8, hours_elapsed=1.0)
        assert new_conf < 0.8
        assert "decay" in reason
    
    def test_decay_respects_minimum(self, dynamics):
        """Decay should not go below minimum"""
        new_conf, _ = dynamics.apply_decay(0.1, hours_elapsed=100.0)
        assert new_conf >= dynamics.min_confidence
    
    def test_no_decay_with_zero_time(self, dynamics):
        """No decay when no time has passed"""
        new_conf, reason = dynamics.apply_decay(0.8, hours_elapsed=0)
        assert new_conf == 0.8
        assert reason == "no_decay"
    
    def test_boost_increases_confidence(self, dynamics):
        """Boost should increase confidence"""
        new_conf, reason = dynamics.apply_boost(0.5, signal_strength=1.0)
        assert new_conf > 0.5
        assert "boost" in reason
    
    def test_boost_respects_maximum(self, dynamics):
        """Boost should not exceed maximum"""
        new_conf, _ = dynamics.apply_boost(0.94, signal_strength=1.0)
        assert new_conf <= dynamics.max_confidence
    
    def test_boost_diminishes_near_max(self, dynamics):
        """Boost effect should be smaller near maximum"""
        boost_low, _ = dynamics.apply_boost(0.3, signal_strength=1.0)
        boost_high, _ = dynamics.apply_boost(0.8, signal_strength=1.0)
        
        delta_low = boost_low - 0.3
        delta_high = boost_high - 0.8
        
        assert delta_low > delta_high  # More headroom = bigger boost
    
    def test_regression_reduces_confidence(self, dynamics):
        """Regression should reduce confidence"""
        new_conf, reason = dynamics.apply_regression(0.7, conflict_weight=1.0)
        assert new_conf < 0.7
        assert "regression" in reason
    
    def test_regression_respects_minimum(self, dynamics):
        """Regression should not go below minimum"""
        new_conf, _ = dynamics.apply_regression(0.1, conflict_weight=1.0)
        assert new_conf >= dynamics.min_confidence
    
    def test_clamp_within_bounds(self, dynamics):
        """Clamp should keep values in valid range"""
        assert dynamics.clamp(1.5) == dynamics.max_confidence
        assert dynamics.clamp(-0.5) == dynamics.min_confidence
        assert dynamics.clamp(0.5) == 0.5


class TestConfidenceTracker:
    """Tests for ConfidenceTracker class"""
    
    @pytest.fixture
    def tracker(self):
        return ConfidenceTracker(initial_confidence=0.5)
    
    def test_initial_state(self, tracker):
        """Tracker starts with correct initial state"""
        assert tracker.current_confidence == 0.5
        assert len(tracker.history) == 1
        assert tracker.history[0][2] == "initial"
    
    def test_confirming_update(self, tracker):
        """Confirming observation boosts confidence"""
        now = datetime.now()
        tracker.last_update_time = now - timedelta(hours=0.1)
        
        new_conf = tracker.update(now, "confirming", signal_strength=1.0)
        assert new_conf > 0.5
    
    def test_conflicting_update(self, tracker):
        """Conflicting observation reduces confidence"""
        now = datetime.now()
        tracker.last_update_time = now - timedelta(hours=0.1)
        
        new_conf = tracker.update(now, "conflicting")
        assert new_conf < 0.5
    
    def test_null_update(self, tracker):
        """Null observation mildly reduces confidence"""
        now = datetime.now()
        tracker.last_update_time = now - timedelta(hours=0.1)
        
        new_conf = tracker.update(now, "null")
        assert new_conf < 0.5
    
    def test_trend_rising(self, tracker):
        """Trend detects rising confidence"""
        tracker.history = [
            ("t1", 0.3, "init"),
            ("t2", 0.5, "boost"),
            ("t3", 0.7, "boost")
        ]
        assert tracker.get_trend() == "rising"
    
    def test_trend_falling(self, tracker):
        """Trend detects falling confidence"""
        tracker.history = [
            ("t1", 0.8, "init"),
            ("t2", 0.6, "decay"),
            ("t3", 0.4, "regression")
        ]
        assert tracker.get_trend() == "falling"
    
    def test_to_dict(self, tracker):
        """to_dict returns correct structure"""
        d = tracker.to_dict()
        assert "current" in d
        assert "trend" in d
        assert d["current"] == 0.5


class TestCandidateConfidence:
    """Tests for Candidate confidence methods"""
    
    @pytest.fixture
    def candidate(self):
        return Candidate(
            id="CAND_01",
            x=100,
            y=100,
            first_detected="2025-01-01T12:00:00",
            last_observed="2025-01-01T12:00:00",
            confidence=0.6
        )
    
    def test_apply_time_decay(self, candidate):
        """apply_time_decay reduces confidence"""
        candidate.last_confidence_update = "2025-01-01T12:00:00"
        
        # 2 hours later
        new_conf = candidate.apply_time_decay("2025-01-01T14:00:00")
        
        assert new_conf < 0.6
        assert len(candidate.confidence_history) == 1
    
    def test_decay_records_history(self, candidate):
        """Decay records entry in history"""
        candidate.last_confidence_update = "2025-01-01T12:00:00"
        candidate.apply_time_decay("2025-01-01T14:00:00")
        
        assert len(candidate.confidence_history) >= 1
        assert "decay" in candidate.confidence_history[-1][2]
    
    def test_update_confidence_positive(self, candidate):
        """update_confidence can increase confidence"""
        new_conf = candidate.update_confidence(
            delta=0.2, 
            reason="confirming_detection",
            current_time="2025-01-01T13:00:00"
        )
        
        assert new_conf == 0.8
    
    def test_update_confidence_negative(self, candidate):
        """update_confidence can decrease confidence"""
        new_conf = candidate.update_confidence(
            delta=-0.3,
            reason="null_detection",
            current_time="2025-01-01T13:00:00"
        )
        
        assert new_conf == 0.3
    
    def test_update_confidence_clamps_max(self, candidate):
        """update_confidence respects maximum"""
        new_conf = candidate.update_confidence(
            delta=0.5,
            reason="strong_signal",
            current_time="2025-01-01T13:00:00"
        )
        
        assert new_conf <= 0.95
    
    def test_update_confidence_clamps_min(self, candidate):
        """update_confidence respects minimum"""
        candidate.confidence = 0.1
        new_conf = candidate.update_confidence(
            delta=-0.2,
            reason="regression",
            current_time="2025-01-01T13:00:00"
        )
        
        assert new_conf >= 0.05
    
    def test_get_confidence_trend_stable(self, candidate):
        """Trend is stable without history"""
        assert candidate.get_confidence_trend() == "stable"
    
    def test_get_confidence_trend_rising(self, candidate):
        """Trend detects rising pattern"""
        candidate.confidence_history = [
            ("t1", 0.3, "init"),
            ("t2", 0.5, "boost"),
            ("t3", 0.7, "boost")
        ]
        assert candidate.get_confidence_trend() == "rising"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
