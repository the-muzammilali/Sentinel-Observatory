"""
Unit tests for regime-shift stress testing scenarios.

Tests phase transitions, timing, and scenario execution.

Run with: python -m pytest tests/test_scenarios.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime, timedelta

from src.simulation.scenarios import (
    RegimePhase, ScenarioPhase, MarathonScenario, ScenarioResult,
    create_standard_marathon, create_false_positive_stress,
    create_weather_chaos, create_multi_candidate_pressure,
    get_scenario, list_scenarios, SCENARIOS
)


class TestRegimePhase:
    """Tests for RegimePhase enum"""
    
    def test_all_phases_have_values(self):
        """Each phase has a string value"""
        for phase in RegimePhase:
            assert len(phase.value) > 0
    
    def test_core_phases_exist(self):
        """Core phases are defined"""
        assert hasattr(RegimePhase, 'QUIET_BASELINE')
        assert hasattr(RegimePhase, 'FALSE_POSITIVE_CLUSTER')
        assert hasattr(RegimePhase, 'DELAYED_TRANSIENT')
        assert hasattr(RegimePhase, 'POST_ALERT_DECAY')
    
    def test_environmental_phases_exist(self):
        """Environmental phases are defined"""
        assert hasattr(RegimePhase, 'WEATHER_DISRUPTION')
        assert hasattr(RegimePhase, 'POOR_SEEING')


class TestScenarioPhase:
    """Tests for ScenarioPhase dataclass"""
    
    @pytest.fixture
    def sample_phase(self):
        return ScenarioPhase(
            phase_type=RegimePhase.QUIET_BASELINE,
            duration_hours=2.0,
            description="Test phase"
        )
    
    def test_get_duration(self, sample_phase):
        """get_duration returns correct timedelta"""
        duration = sample_phase.get_duration()
        assert duration == timedelta(hours=2.0)
    
    def test_is_active_without_times(self, sample_phase):
        """is_active returns False without times set"""
        now = datetime.now()
        assert sample_phase.is_active(now) is False
    
    def test_is_active_during_phase(self, sample_phase):
        """is_active returns True during active window"""
        now = datetime.now()
        sample_phase.start_time = now - timedelta(hours=1)
        sample_phase.end_time = now + timedelta(hours=1)
        
        assert sample_phase.is_active(now) is True
    
    def test_is_active_before_phase(self, sample_phase):
        """is_active returns False before phase starts"""
        now = datetime.now()
        sample_phase.start_time = now + timedelta(hours=1)
        sample_phase.end_time = now + timedelta(hours=3)
        
        assert sample_phase.is_active(now) is False
    
    def test_to_dict(self, sample_phase):
        """to_dict returns correct structure"""
        d = sample_phase.to_dict()
        
        assert d["phase_type"] == "quiet_baseline"
        assert d["duration_hours"] == 2.0
        assert d["description"] == "Test phase"


class TestMarathonScenario:
    """Tests for MarathonScenario class"""
    
    @pytest.fixture
    def simple_scenario(self):
        return MarathonScenario(
            name="Test Scenario",
            phases=[
                ScenarioPhase(RegimePhase.QUIET_BASELINE, 1.0),
                ScenarioPhase(RegimePhase.FALSE_POSITIVE_CLUSTER, 0.5),
                ScenarioPhase(RegimePhase.DELAYED_TRANSIENT, 1.0)
            ]
        )
    
    def test_requires_at_least_one_phase(self):
        """Scenario requires at least one phase"""
        with pytest.raises(ValueError):
            MarathonScenario(name="Empty", phases=[])
    
    def test_get_total_duration(self, simple_scenario):
        """Total duration sums all phases"""
        total = simple_scenario.get_total_duration_hours()
        assert total == 2.5
    
    def test_initialize_sets_times(self, simple_scenario):
        """initialize sets all phase times"""
        start = datetime(2025, 1, 1, 12, 0, 0)
        simple_scenario.initialize(start)
        
        assert simple_scenario.phases[0].start_time == start
        assert simple_scenario.phases[0].end_time == start + timedelta(hours=1)
        assert simple_scenario.phases[1].start_time == start + timedelta(hours=1)
    
    def test_get_current_phase(self, simple_scenario):
        """get_current_phase returns correct phase"""
        simple_scenario.initialize(datetime.now())
        
        phase = simple_scenario.get_current_phase()
        assert phase.phase_type == RegimePhase.QUIET_BASELINE
    
    def test_update_transitions_phase(self, simple_scenario):
        """update transitions to next phase"""
        start = datetime.now() - timedelta(hours=1.5)
        simple_scenario.initialize(start)
        
        # Should be past first phase
        result = simple_scenario.update(datetime.now())
        
        assert result == RegimePhase.FALSE_POSITIVE_CLUSTER
        assert simple_scenario.current_phase_index == 1
    
    def test_is_complete(self, simple_scenario):
        """is_complete returns True when all phases done"""
        simple_scenario.initialize(datetime.now())
        simple_scenario.current_phase_index = 3
        
        assert simple_scenario.is_complete() is True
    
    def test_get_phase_at_time(self, simple_scenario):
        """get_phase_at_time finds correct phase"""
        start = datetime(2025, 1, 1, 12, 0, 0)
        simple_scenario.initialize(start)
        
        # Query time in second phase
        query = start + timedelta(hours=1.25)
        phase = simple_scenario.get_phase_at_time(query)
        
        assert phase.phase_type == RegimePhase.FALSE_POSITIVE_CLUSTER
    
    def test_get_phase_transitions(self, simple_scenario):
        """get_phase_transitions returns all transitions"""
        start = datetime(2025, 1, 1, 12, 0, 0)
        simple_scenario.initialize(start)
        
        transitions = simple_scenario.get_phase_transitions()
        
        assert len(transitions) == 3
        assert transitions[0][0] == "quiet_baseline"
        assert transitions[1][0] == "false_positive_cluster"
    
    def test_to_dict(self, simple_scenario):
        """to_dict returns correct structure"""
        simple_scenario.initialize(datetime.now())
        d = simple_scenario.to_dict()
        
        assert d["name"] == "Test Scenario"
        assert len(d["phases"]) == 3
        assert d["is_complete"] is False


class TestScenarioResult:
    """Tests for ScenarioResult dataclass"""
    
    def test_to_dict(self):
        """to_dict returns correct structure"""
        result = ScenarioResult(
            scenario_name="Test",
            total_duration_hours=3.0,
            phases_completed=2,
            total_phases=3,
            events_injected=5
        )
        
        d = result.to_dict()
        assert d["scenario_name"] == "Test"
        assert d["events_injected"] == 5


class TestPrebuiltScenarios:
    """Tests for pre-built scenarios"""
    
    def test_standard_marathon_structure(self):
        """Standard marathon has 4 phases"""
        scenario = create_standard_marathon()
        
        assert scenario.name == "Standard Marathon"
        assert len(scenario.phases) == 4
    
    def test_false_positive_stress_structure(self):
        """False positive stress has correct phases"""
        scenario = create_false_positive_stress()
        
        assert "False Positive" in scenario.name
        assert any(p.phase_type == RegimePhase.FALSE_POSITIVE_CLUSTER 
                  for p in scenario.phases)
    
    def test_weather_chaos_structure(self):
        """Weather chaos has weather disruption phase"""
        scenario = create_weather_chaos()
        
        assert any(p.phase_type == RegimePhase.WEATHER_DISRUPTION 
                  for p in scenario.phases)
    
    def test_multi_candidate_structure(self):
        """Multi-candidate has prioritization phases"""
        scenario = create_multi_candidate_pressure()
        
        assert any(p.phase_type == RegimePhase.MULTI_CANDIDATE 
                  for p in scenario.phases)
    
    def test_get_scenario(self):
        """get_scenario returns correct scenario"""
        scenario = get_scenario("standard")
        assert scenario.name == "Standard Marathon"
    
    def test_get_scenario_invalid(self):
        """get_scenario raises for unknown name"""
        with pytest.raises(KeyError):
            get_scenario("nonexistent")
    
    def test_list_scenarios(self):
        """list_scenarios returns all available"""
        scenarios = list_scenarios()
        
        assert "standard" in scenarios
        assert "false_positive" in scenarios
        assert "weather" in scenarios
        assert "multi_candidate" in scenarios


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
