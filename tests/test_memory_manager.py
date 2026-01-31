"""
Unit tests for memory hygiene and decay management.

Tests candidate lifecycle, archival, pruning, and reactivation.

Run with: python -m pytest tests/test_memory_manager.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Optional

from src.agent.memory_manager import (
    MemoryConfig, CandidateSummary, MemoryStats, MemoryManager
)


# Mock Candidate class for testing
@dataclass
class MockCandidate:
    """Mock candidate for testing memory manager."""
    id: str
    ra: float = 180.0
    dec: float = 45.0
    confidence: float = 0.5
    status: str = "MONITORING"
    classification: str = "unknown"
    hypothesis: str = ""
    alert_triggered: bool = False
    history: List = field(default_factory=list)
    reactivation_count: int = 0


@dataclass
class MockHistory:
    """Mock observation history entry."""
    time: str
    magnitude: float = 18.0
    confidence: float = 0.5


class TestMemoryConfig:
    """Tests for MemoryConfig"""
    
    def test_default_values(self):
        """Default config has reasonable values"""
        config = MemoryConfig()
        
        assert config.max_active_candidates == 50
        assert config.max_archived_candidates == 100
        assert config.stale_threshold_hours == 12.0
        assert config.prune_rejected_after_hours == 24.0
    
    def test_custom_values(self):
        """Custom config values are applied"""
        config = MemoryConfig(
            max_active_candidates=25,
            stale_threshold_hours=6.0
        )
        
        assert config.max_active_candidates == 25
        assert config.stale_threshold_hours == 6.0


class TestCandidateSummary:
    """Tests for CandidateSummary"""
    
    @pytest.fixture
    def sample_summary(self):
        return CandidateSummary(
            id="TC001",
            classification="SN_Ia",
            hypothesis="suspected supernova",
            outcome="confirmed",
            alert_triggered=True,
            confidence_final=0.95,
            confidence_peak=0.98,
            observation_count=15,
            first_seen="2025-01-01T00:00:00",
            last_seen="2025-01-01T12:00:00",
            duration_hours=12.0,
            ra=180.123,
            dec=45.678,
            archived_at="2025-01-03T00:00:00"
        )
    
    def test_to_dict(self, sample_summary):
        """to_dict returns complete structure"""
        d = sample_summary.to_dict()
        
        assert d["id"] == "TC001"
        assert d["classification"] == "SN_Ia"
        assert d["alert_triggered"] is True
        assert d["confidence_final"] == 0.95
    
    def test_from_dict(self, sample_summary):
        """from_dict reconstructs summary"""
        d = sample_summary.to_dict()
        restored = CandidateSummary.from_dict(d)
        
        assert restored.id == sample_summary.id
        assert restored.classification == sample_summary.classification
        assert restored.alert_triggered == sample_summary.alert_triggered


class TestMemoryManager:
    """Tests for MemoryManager class"""
    
    @pytest.fixture
    def manager(self):
        return MemoryManager(MemoryConfig(
            max_active_candidates=10,
            max_archived_candidates=20,
            stale_threshold_hours=2.0,
            prune_rejected_after_hours=4.0,
            archive_confirmed_after_hours=6.0,
            prune_archived_after_days=3
        ))
    
    @pytest.fixture
    def sample_candidates(self):
        now = datetime.now()
        return [
            MockCandidate(
                id="TC001", status="MONITORING", confidence=0.7,
                history=[MockHistory((now - timedelta(hours=1)).isoformat())]
            ),
            MockCandidate(
                id="TC002", status="CONFIRMED", confidence=0.95,
                history=[MockHistory((now - timedelta(hours=10)).isoformat())]
            ),
            MockCandidate(
                id="TC003", status="REJECTED", confidence=0.2,
                history=[MockHistory((now - timedelta(hours=5)).isoformat())]
            )
        ]
    
    def test_apply_hygiene_basic(self, manager, sample_candidates):
        """apply_hygiene runs without error"""
        candidates, archived, stats = manager.apply_hygiene(
            sample_candidates, [], datetime.now()
        )
        
        assert isinstance(candidates, list)
        assert isinstance(archived, list)
        assert isinstance(stats, MemoryStats)
    
    def test_archive_confirmed_candidates(self, manager):
        """Confirmed candidates are archived after threshold"""
        now = datetime.now()
        
        # Candidate confirmed 10 hours ago
        old_confirmed = MockCandidate(
            id="TC001", status="CONFIRMED", confidence=0.95,
            history=[MockHistory((now - timedelta(hours=10)).isoformat())]
        )
        
        candidates, archived, stats = manager.apply_hygiene(
            [old_confirmed], [], now
        )
        
        # Should be archived (threshold is 6 hours)
        assert len(candidates) == 0
        assert len(archived) == 1
        assert archived[0].id == "TC001"
    
    def test_archive_rejected_candidates(self, manager):
        """Rejected candidates are archived after threshold"""
        now = datetime.now()
        
        # Candidate rejected 5 hours ago
        old_rejected = MockCandidate(
            id="TC002", status="REJECTED", confidence=0.1,
            history=[MockHistory((now - timedelta(hours=5)).isoformat())]
        )
        
        candidates, archived, stats = manager.apply_hygiene(
            [old_rejected], [], now
        )
        
        # Should be archived (threshold is 4 hours)
        assert len(candidates) == 0
        assert len(archived) == 1
    
    def test_keep_recent_candidates(self, manager):
        """Recent candidates are not archived"""
        now = datetime.now()
        
        recent = MockCandidate(
            id="TC001", status="CONFIRMED", confidence=0.95,
            history=[MockHistory((now - timedelta(hours=1)).isoformat())]
        )
        
        candidates, archived, stats = manager.apply_hygiene(
            [recent], [], now
        )
        
        assert len(candidates) == 1
        assert len(archived) == 0
    
    def test_prune_old_archives(self, manager):
        """Old archived summaries are pruned"""
        now = datetime.now()
        
        old_archive = CandidateSummary(
            id="TC001", classification="CV", hypothesis="",
            outcome="rejected", alert_triggered=False,
            confidence_final=0.2, confidence_peak=0.3,
            observation_count=5,
            first_seen="2025-01-01T00:00:00",
            last_seen="2025-01-01T05:00:00",
            duration_hours=5.0, ra=180.0, dec=45.0,
            archived_at=(now - timedelta(days=5)).isoformat()
        )
        
        candidates, archived, stats = manager.apply_hygiene(
            [], [old_archive], now
        )
        
        # Should be pruned (threshold is 3 days)
        assert len(archived) == 0
        assert stats.candidates_pruned == 1
    
    def test_enforce_active_limit(self, manager):
        """Enforces max active candidates"""
        now = datetime.now()
        
        # Create 15 candidates (limit is 10)
        candidates = [
            MockCandidate(
                id=f"TC{i:03d}", status="MONITORING",
                confidence=0.5 + (i * 0.01),
                history=[MockHistory(now.isoformat())]
            )
            for i in range(15)
        ]
        
        result, archived, stats = manager.apply_hygiene(
            candidates, [], now
        )
        
        assert len(result) == 10
        assert len(archived) == 5
    
    def test_enforce_archived_limit(self, manager):
        """Enforces max archived candidates"""
        now = datetime.now()
        
        # Create 25 archived (limit is 20)
        archives = [
            CandidateSummary(
                id=f"TC{i:03d}", classification="CV", hypothesis="",
                outcome="rejected", alert_triggered=False,
                confidence_final=0.2, confidence_peak=0.3,
                observation_count=3, first_seen="", last_seen="",
                duration_hours=1.0, ra=180.0, dec=45.0,
                archived_at=now.isoformat()
            )
            for i in range(25)
        ]
        
        candidates, result, stats = manager.apply_hygiene(
            [], archives, now
        )
        
        assert len(result) == 20
    
    def test_stale_decay(self, manager):
        """Stale candidates have confidence decayed"""
        now = datetime.now()
        
        # Candidate not observed for 4 hours
        stale = MockCandidate(
            id="TC001", status="MONITORING", confidence=0.8,
            history=[MockHistory((now - timedelta(hours=4)).isoformat())]
        )
        
        candidates, _, _ = manager.apply_hygiene([stale], [], now)
        
        # Should have decayed (2 hours over threshold, 5% per hour = 10%)
        assert candidates[0].confidence < 0.8
    
    def test_check_reactivation_match(self, manager):
        """Reactivation finds matching archived candidate"""
        archived = CandidateSummary(
            id="TC001", classification="SN_Ia", hypothesis="",
            outcome="rejected", alert_triggered=False,
            confidence_final=0.3, confidence_peak=0.5,
            observation_count=5, first_seen="", last_seen="",
            duration_hours=2.0,
            ra=180.1234, dec=45.6789,
            archived_at=datetime.now().isoformat()
        )
        
        # Match within 0.01 degrees
        match = manager.check_reactivation(
            ra=180.1235, dec=45.6790, magnitude=18.0,
            archived=[archived]
        )
        
        assert match is not None
        assert match.id == "TC001"
    
    def test_check_reactivation_no_match(self, manager):
        """Reactivation returns None for distant detection"""
        archived = CandidateSummary(
            id="TC001", classification="SN_Ia", hypothesis="",
            outcome="rejected", alert_triggered=False,
            confidence_final=0.3, confidence_peak=0.5,
            observation_count=5, first_seen="", last_seen="",
            duration_hours=2.0,
            ra=180.0, dec=45.0,
            archived_at=datetime.now().isoformat()
        )
        
        # Too far away
        match = manager.check_reactivation(
            ra=181.0, dec=46.0, magnitude=18.0,
            archived=[archived]
        )
        
        assert match is None
    
    def test_archive_candidate(self, manager):
        """archive_candidate creates proper summary"""
        now = datetime.now()
        
        candidate = MockCandidate(
            id="TC001",
            ra=180.123, dec=45.678,
            confidence=0.85, status="CONFIRMED",
            classification="SN_Ia",
            hypothesis="Type Ia supernova",
            alert_triggered=True,
            history=[
                MockHistory("2025-01-01T00:00:00", magnitude=18.5, confidence=0.6),
                MockHistory("2025-01-01T02:00:00", magnitude=18.3, confidence=0.8),
            ]
        )
        
        summary = manager.archive_candidate(candidate, now)
        
        assert summary.id == "TC001"
        assert summary.classification == "SN_Ia"
        assert summary.hypothesis == "Type Ia supernova"
        assert summary.alert_triggered is True
        assert summary.observation_count == 2
        assert summary.ra == 180.123
    
    def test_estimate_tokens(self, manager):
        """Token estimation works correctly"""
        tokens = manager.estimate_tokens(
            active_count=10,
            archived_count=50
        )
        
        # 10 * 400 + 50 * 50 = 4000 + 2500 = 6500
        assert tokens == 6500
    
    def test_memory_stats_tracking(self, manager, sample_candidates):
        """Memory stats are tracked correctly"""
        _, _, stats = manager.apply_hygiene(
            sample_candidates, [], datetime.now()
        )
        
        assert stats.estimated_total_tokens > 0
        assert stats.active_candidates >= 0
    
    def test_get_memory_stats(self, manager, sample_candidates):
        """get_memory_stats returns current stats"""
        manager.apply_hygiene(sample_candidates, [], datetime.now())
        stats = manager.get_memory_stats()
        
        assert isinstance(stats, MemoryStats)


class TestMemoryStats:
    """Tests for MemoryStats dataclass"""
    
    def test_to_dict(self):
        """to_dict returns complete structure"""
        stats = MemoryStats(
            active_candidates=10,
            archived_candidates=50,
            total_observations=200,
            estimated_active_tokens=4000,
            estimated_archived_tokens=2500,
            estimated_total_tokens=6500,
            candidates_pruned=5
        )
        
        d = stats.to_dict()
        assert d["active_candidates"] == 10
        assert d["candidates_pruned"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
