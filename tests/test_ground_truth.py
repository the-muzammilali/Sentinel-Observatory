"""
Unit tests for ground truth tracking and evaluation metrics.

Tests event tracking, TP/FP counting, latency calculation, and reveal mode.

Run with: python -m pytest tests/test_ground_truth.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime, timedelta

from src.simulation.ground_truth import (
    TransientType, GroundTruthEvent, EvaluationMetrics, GroundTruthTracker
)


class TestTransientType:
    """Tests for TransientType enum"""
    
    def test_all_types_exist(self):
        """All expected transient types exist"""
        assert TransientType.SN_IA.value == "SN_Ia"
        assert TransientType.SN_II.value == "SN_II"
        assert TransientType.CV.value == "CV"
        assert TransientType.NOVA.value == "nova"


class TestGroundTruthEvent:
    """Tests for GroundTruthEvent dataclass"""
    
    @pytest.fixture
    def sample_event(self):
        return GroundTruthEvent(
            id="GT_001",
            event_type=TransientType.SN_IA,
            ra=180.0,
            dec=45.0,
            appearance_time="2025-01-01T00:00:00",
            peak_magnitude=16.0
        )
    
    def test_to_dict(self, sample_event):
        """to_dict returns complete structure"""
        d = sample_event.to_dict()
        
        assert d["id"] == "GT_001"
        assert d["event_type"] == "SN_Ia"
        assert d["ra"] == 180.0
        assert d["is_real_transient"] is True
    
    def test_default_values(self, sample_event):
        """Default values are reasonable"""
        assert sample_event.detected_by_agent is False
        assert sample_event.alert_triggered is False
        assert sample_event.is_real_transient is True


class TestEvaluationMetrics:
    """Tests for EvaluationMetrics"""
    
    def test_precision_calculation(self):
        """Precision is calculated correctly"""
        metrics = EvaluationMetrics(
            true_positives=8,
            false_positives=2
        )
        assert metrics.precision == 0.8
    
    def test_recall_calculation(self):
        """Recall is calculated correctly"""
        metrics = EvaluationMetrics(
            true_positives=6,
            false_negatives=4
        )
        assert metrics.recall == 0.6
    
    def test_f1_score_calculation(self):
        """F1 score is harmonic mean"""
        metrics = EvaluationMetrics(
            true_positives=8,
            false_positives=2,
            false_negatives=2
        )
        # Precision = 0.8, Recall = 0.8
        # F1 = 2 * 0.8 * 0.8 / 1.6 = 0.8
        assert round(metrics.f1_score, 2) == 0.8
    
    def test_perfect_precision(self):
        """Perfect precision when no false positives"""
        metrics = EvaluationMetrics(true_positives=10)
        assert metrics.precision == 1.0
    
    def test_zero_division_handling(self):
        """Handles zero division gracefully"""
        metrics = EvaluationMetrics()
        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.f1_score == 1.0
    
    def test_mean_latency(self):
        """Mean latency is calculated correctly"""
        metrics = EvaluationMetrics(
            total_detections=4,
            total_latency_hours=8.0
        )
        assert metrics.mean_latency_hours == 2.0
    
    def test_to_dict(self):
        """to_dict includes all metrics"""
        metrics = EvaluationMetrics(
            true_positives=5,
            false_positives=1,
            false_negatives=1
        )
        d = metrics.to_dict()
        
        assert "precision" in d
        assert "recall" in d
        assert "f1_score" in d


class TestGroundTruthTracker:
    """Tests for GroundTruthTracker"""
    
    @pytest.fixture
    def tracker(self):
        return GroundTruthTracker()
    
    @pytest.fixture
    def tracker_with_events(self):
        tracker = GroundTruthTracker()
        tracker.add_event(
            event_type=TransientType.SN_IA,
            ra=180.0, dec=45.0,
            appearance_time="2025-01-01T00:00:00",
            is_real=True
        )
        tracker.add_event(
            event_type=TransientType.CV,
            ra=181.0, dec=46.0,
            appearance_time="2025-01-01T01:00:00",
            is_real=True
        )
        tracker.add_event(
            event_type=TransientType.UNKNOWN,
            ra=182.0, dec=47.0,
            appearance_time="2025-01-01T02:00:00",
            is_real=False  # Artifact
        )
        return tracker
    
    def test_add_event(self, tracker):
        """Events can be added"""
        event_id = tracker.add_event(
            event_type=TransientType.SN_IA,
            ra=180.0, dec=45.0,
            appearance_time="2025-01-01T00:00:00"
        )
        
        assert event_id == "GT_001"
        assert len(tracker.events) == 1
    
    def test_add_event_custom_id(self, tracker):
        """Custom event IDs work"""
        event_id = tracker.add_event(
            event_type=TransientType.NOVA,
            ra=180.0, dec=45.0,
            appearance_time="2025-01-01T00:00:00",
            event_id="CUSTOM_001"
        )
        
        assert event_id == "CUSTOM_001"
    
    def test_record_detection_match(self, tracker_with_events):
        """Detection matching works"""
        match = tracker_with_events.record_detection(
            candidate_id="CAND_01",
            ra=180.001, dec=45.001,  # Close match
            detection_time="2025-01-01T00:30:00"
        )
        
        assert match == "GT_001"
        assert tracker_with_events.events["GT_001"].detected_by_agent is True
    
    def test_record_detection_no_match(self, tracker_with_events):
        """No match for distant position"""
        match = tracker_with_events.record_detection(
            candidate_id="CAND_01",
            ra=190.0, dec=50.0,  # Far away
            detection_time="2025-01-01T00:30:00"
        )
        
        assert match is None
    
    def test_record_alert_true_positive(self, tracker_with_events):
        """Alert on real transient is true positive"""
        result = tracker_with_events.record_alert(
            candidate_id="CAND_01",
            ra=180.001, dec=45.001,
            alert_time="2025-01-01T02:00:00"
        )
        
        assert result is True
        assert tracker_with_events.get_metrics().true_positives == 1
    
    def test_record_alert_false_positive_artifact(self, tracker_with_events):
        """Alert on artifact is false positive"""
        result = tracker_with_events.record_alert(
            candidate_id="CAND_01",
            ra=182.001, dec=47.001,  # Matches the artifact
            alert_time="2025-01-01T03:00:00"
        )
        
        assert result is False
        assert tracker_with_events.get_metrics().false_positives == 1
    
    def test_record_alert_false_positive_unknown(self, tracker):
        """Alert at unknown position is false positive"""
        result = tracker.record_alert(
            candidate_id="CAND_01",
            ra=100.0, dec=10.0,  # No events here
            alert_time="2025-01-01T00:00:00"
        )
        
        assert result is False
        assert tracker.get_metrics().false_positives == 1
    
    def test_latency_calculation(self, tracker):
        """Alert latency is calculated"""
        tracker.add_event(
            event_type=TransientType.SN_IA,
            ra=180.0, dec=45.0,
            appearance_time="2025-01-01T00:00:00"
        )
        
        tracker.record_alert(
            candidate_id="CAND_01",
            ra=180.0, dec=45.0,
            alert_time="2025-01-01T02:00:00"  # 2 hours later
        )
        
        metrics = tracker.get_metrics()
        assert metrics.mean_latency_hours == 2.0
    
    def test_finalize_metrics(self, tracker_with_events):
        """Finalize counts false negatives"""
        # Alert on one real transient
        tracker_with_events.record_alert(
            candidate_id="CAND_01",
            ra=180.0, dec=45.0,
            alert_time="2025-01-01T01:00:00"
        )
        
        # Finalize - one real transient missed, one artifact correctly ignored
        metrics = tracker_with_events.finalize_metrics()
        
        assert metrics.true_positives == 1
        assert metrics.false_negatives == 1  # Missed CV
        assert metrics.true_negatives == 1  # Ignored artifact
    
    def test_reveal_mode_disabled(self, tracker_with_events):
        """Reveal returns None when disabled"""
        assert tracker_with_events.reveal_truth() is None
    
    def test_reveal_mode_enabled(self, tracker_with_events):
        """Reveal returns events when enabled"""
        tracker_with_events.enable_reveal_mode()
        truth = tracker_with_events.reveal_truth()
        
        assert truth is not None
        assert len(truth) == 3
    
    def test_get_summary_without_reveal(self, tracker_with_events):
        """Summary without revealing events"""
        summary = tracker_with_events.get_summary()
        
        assert summary["total_events"] == 3
        assert summary["real_transients"] == 2
        assert summary["artifacts"] == 1
        assert "events" not in summary
    
    def test_get_summary_with_reveal(self, tracker_with_events):
        """Summary includes events when reveal mode on"""
        tracker_with_events.enable_reveal_mode()
        summary = tracker_with_events.get_summary()
        
        assert "events" in summary
        assert len(summary["events"]) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
