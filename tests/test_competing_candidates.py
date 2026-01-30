"""
Unit tests for multiple competing candidates in Project Sentinel.

Tests the multi-candidate injection, follow-up budget tracking,
and priority ranking functionality.

Run with: python -m pytest tests/test_competing_candidates.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
from datetime import datetime, timedelta

from src.simulation.universe import (
    UniverseController, TransientType, FollowUpBudget
)


class TestFollowUpBudget:
    """Tests for FollowUpBudget dataclass"""
    
    def test_budget_initialization(self):
        """Budget initializes with correct defaults"""
        budget = FollowUpBudget()
        assert budget.max_followups_per_hour == 2
        assert budget.current_followups == 0
    
    def test_use_followup_success(self):
        """use_followup returns True when budget available"""
        budget = FollowUpBudget(max_followups_per_hour=2)
        assert budget.use_followup() == True
        assert budget.current_followups == 1
    
    def test_use_followup_exhausted(self):
        """use_followup returns False when budget exhausted"""
        budget = FollowUpBudget(max_followups_per_hour=2)
        budget.use_followup()
        budget.use_followup()
        assert budget.use_followup() == False
        assert budget.current_followups == 2
    
    def test_remaining_calculation(self):
        """remaining() returns correct count"""
        budget = FollowUpBudget(max_followups_per_hour=3)
        assert budget.remaining() == 3
        budget.use_followup()
        assert budget.remaining() == 2
        budget.use_followup()
        assert budget.remaining() == 1
    
    def test_reset(self):
        """reset() clears followup count"""
        budget = FollowUpBudget(max_followups_per_hour=2)
        budget.use_followup()
        budget.use_followup()
        
        new_time = datetime.now()
        budget.reset(new_time)
        
        assert budget.current_followups == 0
        assert budget.window_start == new_time
    
    def test_to_dict(self):
        """to_dict() returns correct structure"""
        now = datetime.now()
        budget = FollowUpBudget(max_followups_per_hour=3, window_start=now)
        budget.use_followup()
        
        d = budget.to_dict()
        assert d["max_per_hour"] == 3
        assert d["used"] == 1
        assert d["remaining"] == 2


class TestInjectCompetingCandidates:
    """Tests for inject_competing_candidates method"""
    
    @pytest.fixture
    def universe(self):
        """Create fresh universe for each test"""
        return UniverseController(field_size=10.0, num_stars=50, random_seed=123)
    
    def test_correct_count_injected(self, universe):
        """Correct number of candidates created"""
        candidates = universe.inject_competing_candidates(count=4)
        assert len(candidates) == 4
    
    def test_default_count_is_three(self, universe):
        """Default count is 3"""
        candidates = universe.inject_competing_candidates()
        assert len(candidates) == 3
    
    def test_magnitude_range_respected(self, universe):
        """All candidates within specified magnitude range"""
        candidates = universe.inject_competing_candidates(
            count=5,
            magnitude_range=(19.0, 21.0)
        )
        
        # Step to peak time to get peak magnitude
        for c in candidates:
            peak_mag = c.peak_magnitude
            assert 19.0 <= peak_mag <= 21.0, f"Magnitude {peak_mag} outside range"
    
    def test_candidates_in_transients_list(self, universe):
        """Candidates added to transients list"""
        initial_count = len(universe.transients)
        candidates = universe.inject_competing_candidates(count=3)
        
        assert len(universe.transients) == initial_count + 3
    
    def test_candidates_have_different_types(self, universe):
        """Candidates cycle through event types"""
        candidates = universe.inject_competing_candidates(count=4)
        types = [c.event_type for c in candidates]
        
        # Should have multiple different types
        assert len(set(types)) >= 2
    
    def test_candidates_staggered_start(self, universe):
        """Candidates have staggered start times"""
        candidates = universe.inject_competing_candidates(
            count=3,
            spacing_hours=0.5
        )
        
        start_times = [c.start_time for c in candidates]
        for i in range(1, len(start_times)):
            delta = (start_times[i] - start_times[i-1]).total_seconds() / 3600
            assert abs(delta - 0.5) < 0.01


class TestGetCandidatePriorities:
    """Tests for get_candidate_priorities method"""
    
    @pytest.fixture
    def universe(self):
        """Create universe with active transients"""
        u = UniverseController(field_size=10.0, num_stars=50, random_seed=42)
        # Add transients that are active now
        u.add_transient(x=1.0, y=1.0, start_offset_hours=-0.5, duration_hours=2.0, 
                       peak_magnitude=17.0)  # Bright
        u.add_transient(x=-1.0, y=-1.0, start_offset_hours=-0.5, duration_hours=2.0, 
                       peak_magnitude=20.0)  # Faint
        return u
    
    def test_returns_list(self, universe):
        """Returns a list of candidates"""
        priorities = universe.get_candidate_priorities()
        assert isinstance(priorities, list)
    
    def test_active_only(self, universe):
        """Only active transients included"""
        # Add an expired transient
        universe.add_transient(x=0, y=0, start_offset_hours=-5.0, duration_hours=1.0, 
                              peak_magnitude=18.0)
        
        priorities = universe.get_candidate_priorities()
        # Should have 2 active, not the expired one
        assert len(priorities) == 2
    
    def test_sorted_by_priority(self, universe):
        """Brighter candidates have higher priority"""
        priorities = universe.get_candidate_priorities()
        
        # First should be brighter (mag 17 vs mag 20)
        assert priorities[0]["current_magnitude"] < priorities[1]["current_magnitude"]
    
    def test_contains_required_fields(self, universe):
        """Each candidate has required fields"""
        priorities = universe.get_candidate_priorities()
        
        for p in priorities:
            assert "id" in p
            assert "type" in p
            assert "position" in p
            assert "current_magnitude" in p
            assert "time_remaining_hours" in p
            assert "priority_score" in p


class TestResourceState:
    """Tests for get_resource_state method"""
    
    @pytest.fixture
    def universe(self):
        """Create universe"""
        return UniverseController(field_size=10.0, num_stars=50, random_seed=42)
    
    def test_resource_state_has_budget(self, universe):
        """Resource state includes follow-up budget"""
        state = universe.get_resource_state()
        assert "followup_budget" in state
    
    def test_resource_state_has_candidate_count(self, universe):
        """Resource state includes active candidate count"""
        # Inject candidates with zero spacing so all start immediately
        universe.inject_competing_candidates(count=3, spacing_hours=0.0)
        # Step time forward slightly to ensure all are active
        universe.step_time(hours=0.5)
        state = universe.get_resource_state()
        
        assert "active_candidates" in state
        assert state["active_candidates"] == 3


class TestUniverseBudgetIntegration:
    """Tests for budget integration in UniverseController"""
    
    def test_universe_has_followup_budget(self):
        """Universe initializes with a followup budget"""
        universe = UniverseController(field_size=10.0, num_stars=10)
        assert hasattr(universe, 'followup_budget')
        assert isinstance(universe.followup_budget, FollowUpBudget)
    
    def test_budget_window_start_matches_universe_time(self):
        """Budget window starts at universe start time"""
        start = datetime(2025, 1, 1, 12, 0, 0)
        universe = UniverseController(start_time=start)
        
        assert universe.followup_budget.window_start == start


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
