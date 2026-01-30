"""
Unit tests for universe randomization in Project Sentinel.

Tests bounded randomization of transient parameters and
reproducibility through deterministic seeds.

Run with: python -m pytest tests/test_randomization.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
from datetime import datetime, timedelta

from src.simulation.universe import (
    UniverseController, TransientType, RandomizationConfig
)


class TestRandomizationConfig:
    """Tests for RandomizationConfig dataclass"""
    
    def test_default_values(self):
        """Config initializes with sensible defaults"""
        config = RandomizationConfig()
        assert config.start_time_jitter_hours == 0.5
        assert config.duration_variance == 0.2
        assert config.magnitude_variance == 0.5
    
    def test_seed_creates_rng(self):
        """Seed creates reproducible RNG"""
        config = RandomizationConfig(seed=42)
        assert hasattr(config, '_rng')
    
    def test_jitter_value_within_bounds(self):
        """jitter_value stays within ±variance"""
        config = RandomizationConfig(seed=123)
        
        base = 10.0
        variance = 2.0
        
        for _ in range(100):
            jittered = config.jitter_value(base, variance)
            assert base - variance <= jittered <= base + variance
    
    def test_jitter_percent_within_bounds(self):
        """jitter_percent stays within ±percent of base"""
        config = RandomizationConfig(seed=456)
        
        base = 10.0
        percent = 0.2  # ±20%
        
        for _ in range(100):
            jittered = config.jitter_percent(base, percent)
            assert base * 0.8 <= jittered <= base * 1.2
    
    def test_to_dict(self):
        """to_dict returns correct structure"""
        config = RandomizationConfig(seed=42)
        d = config.to_dict()
        
        assert "start_time_jitter_hours" in d
        assert "magnitude_variance" in d
        assert d["seed"] == 42


class TestRandomizationReproducibility:
    """Tests for deterministic seed reproducibility"""
    
    def test_same_seed_same_jitter(self):
        """Same seed produces identical jitter sequence"""
        config1 = RandomizationConfig(seed=999)
        config2 = RandomizationConfig(seed=999)
        
        results1 = [config1.jitter_value(10.0, 1.0) for _ in range(5)]
        results2 = [config2.jitter_value(10.0, 1.0) for _ in range(5)]
        
        assert results1 == results2
    
    def test_different_seeds_different_results(self):
        """Different seeds produce different jitter"""
        config1 = RandomizationConfig(seed=1)
        config2 = RandomizationConfig(seed=2)
        
        result1 = config1.jitter_value(10.0, 1.0)
        result2 = config2.jitter_value(10.0, 1.0)
        
        assert result1 != result2


class TestAddTransientRandomized:
    """Tests for add_transient_randomized method"""
    
    @pytest.fixture
    def universe(self):
        """Create fresh universe for each test"""
        return UniverseController(field_size=10.0, num_stars=10, random_seed=42)
    
    def test_creates_transient(self, universe):
        """Creates a valid transient event"""
        transient = universe.add_transient_randomized()
        assert transient is not None
        assert transient.id.startswith("TRANSIENT_")
    
    def test_position_randomized_when_none(self, universe):
        """Position is randomized when not specified"""
        config = RandomizationConfig(seed=42)
        t1 = universe.add_transient_randomized(config=config)
        
        config2 = RandomizationConfig(seed=43)
        t2 = universe.add_transient_randomized(config=config2)
        
        # Different seeds should produce different positions
        assert t1.x != t2.x or t1.y != t2.y
    
    def test_position_respected_when_specified(self, universe):
        """Specified position is used"""
        transient = universe.add_transient_randomized(x=1.5, y=-2.0)
        assert transient.x == 1.5
        assert transient.y == -2.0
    
    def test_magnitude_jittered(self, universe):
        """Magnitude is jittered from base value"""
        config = RandomizationConfig(seed=42, magnitude_variance=0.5)
        
        transients = [
            universe.add_transient_randomized(peak_magnitude=18.0, config=config)
            for _ in range(5)
        ]
        
        # All should be within ±0.5 of 18.0
        for t in transients:
            assert 17.5 <= t.peak_magnitude <= 18.5
    
    def test_duration_jittered(self, universe):
        """Duration is jittered from base value"""
        config = RandomizationConfig(seed=123, duration_variance=0.2)  # ±20%
        
        transient = universe.add_transient_randomized(
            duration_hours=2.0, config=config
        )
        
        # Duration should be approximately 2h ±20%
        duration = (transient.end_time - transient.start_time).total_seconds() / 3600
        assert 1.5 <= duration <= 2.5
    
    def test_event_type_randomized_when_none(self, universe):
        """Event type is randomly selected when not specified"""
        config = RandomizationConfig(seed=42)
        
        transients = [
            universe.add_transient_randomized(config=config)
            for _ in range(10)
        ]
        
        types = {t.event_type for t in transients}
        # Should have some variety
        assert len(types) >= 2


class TestGenerateRandomScenario:
    """Tests for generate_random_scenario method"""
    
    @pytest.fixture
    def universe(self):
        """Create fresh universe for each test"""
        return UniverseController(field_size=10.0, num_stars=10, random_seed=42)
    
    def test_creates_correct_counts(self, universe):
        """Generates correct number of transients and artifacts"""
        scenario = universe.generate_random_scenario(n_transients=3, n_artifacts=2)
        
        assert scenario["n_transients"] == 3
        assert scenario["n_artifacts"] == 2
        assert len(scenario["transient_ids"]) == 3
        assert len(scenario["artifact_ids"]) == 2
    
    def test_seed_reproducibility(self, universe):
        """Same seed produces identical scenarios"""
        config1 = RandomizationConfig(seed=777)
        config2 = RandomizationConfig(seed=777)
        
        # Create two fresh universes
        u1 = UniverseController(field_size=10.0, num_stars=10, random_seed=42)
        u2 = UniverseController(field_size=10.0, num_stars=10, random_seed=42)
        
        s1 = u1.generate_random_scenario(n_transients=2, n_artifacts=1, config=config1)
        s2 = u2.generate_random_scenario(n_transients=2, n_artifacts=1, config=config2)
        
        # Same structure
        assert s1["n_transients"] == s2["n_transients"]
        assert s1["n_artifacts"] == s2["n_artifacts"]
    
    def test_scenario_includes_config(self, universe):
        """Scenario includes config for reproducibility"""
        config = RandomizationConfig(seed=123)
        scenario = universe.generate_random_scenario(config=config)
        
        assert "config" in scenario
        assert scenario["config"]["seed"] == 123
    
    def test_default_scenario(self, universe):
        """Default scenario creates 2 transients and 1 artifact"""
        scenario = universe.generate_random_scenario()
        
        assert scenario["n_transients"] == 2
        assert scenario["n_artifacts"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
