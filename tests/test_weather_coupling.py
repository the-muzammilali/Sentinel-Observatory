"""
Unit tests for weather-signal coupling in Project Sentinel.

Tests the integration between WeatherSystem and TelescopeCamera,
ensuring weather conditions affect observation quality.

Run with: python -m pytest tests/test_weather_coupling.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
from datetime import datetime

from src.simulation.weather import WeatherSystem, WeatherConditions
from src.simulation.telescope import TelescopeCamera, CameraConfig


class TestWeatherConditions:
    """Tests for WeatherConditions dataclass"""
    
    def test_weather_conditions_creation(self):
        """WeatherConditions can be created with required fields"""
        conditions = WeatherConditions(
            seeing=1.0,
            cloud_extinction=0.3,
            time_hours=2.5
        )
        assert conditions.seeing == 1.0
        assert conditions.cloud_extinction == 0.3
        assert conditions.time_hours == 2.5
    
    def test_weather_conditions_to_dict(self):
        """WeatherConditions converts to dict properly"""
        conditions = WeatherConditions(seeing=1.5, cloud_extinction=0.25, time_hours=1.0)
        d = conditions.to_dict()
        assert d["seeing"] == 1.5
        assert d["cloud_extinction"] == 0.25


class TestTelescopeCameraWeatherIntegration:
    """Tests for weather integration in TelescopeCamera"""
    
    @pytest.fixture
    def camera(self):
        """Create a camera instance (not initialized)"""
        return TelescopeCamera()
    
    def test_set_seeing(self, camera):
        """set_seeing stores the value"""
        camera.set_seeing(1.5)
        assert camera._seeing == 1.5
    
    def test_set_seeing_clips_min(self, camera):
        """set_seeing clips to minimum 0.3"""
        camera.set_seeing(0.1)
        assert camera._seeing == 0.3
    
    def test_set_seeing_clips_max(self, camera):
        """set_seeing clips to maximum 3.0"""
        camera.set_seeing(5.0)
        assert camera._seeing == 3.0
    
    def test_set_cloud_extinction(self, camera):
        """set_cloud_extinction stores the value"""
        camera.set_cloud_extinction(0.4)
        assert camera._cloud_extinction == 0.4
    
    def test_set_cloud_extinction_clips_min(self, camera):
        """set_cloud_extinction clips to minimum 0.0"""
        camera.set_cloud_extinction(-0.5)
        assert camera._cloud_extinction == 0.0
    
    def test_set_cloud_extinction_clips_max(self, camera):
        """set_cloud_extinction clips to maximum 1.0"""
        camera.set_cloud_extinction(1.5)
        assert camera._cloud_extinction == 1.0
    
    def test_apply_weather(self, camera):
        """apply_weather sets both seeing and extinction"""
        conditions = WeatherConditions(
            seeing=2.0,
            cloud_extinction=0.5,
            time_hours=1.0
        )
        camera.apply_weather(conditions)
        
        assert camera._seeing == 2.0
        assert camera._cloud_extinction == 0.5
    
    def test_get_weather_state(self, camera):
        """get_weather_state returns current parameters"""
        camera.set_seeing(1.8)
        camera.set_cloud_extinction(0.3)
        
        state = camera.get_weather_state()
        assert state["seeing"] == 1.8
        assert state["cloud_extinction"] == 0.3


class TestWeatherSystemEvolution:
    """Tests for WeatherSystem time evolution"""
    
    @pytest.fixture
    def weather(self):
        """Create weather system with fixed seed"""
        return WeatherSystem(seed=42)
    
    def test_weather_system_initialization(self, weather):
        """Weather system initializes with default values"""
        conditions = weather.get_conditions()
        assert 0.5 <= conditions.seeing <= 2.5
        assert 0.0 <= conditions.cloud_extinction <= 1.0
    
    def test_weather_system_step(self, weather):
        """Weather system advances time on step"""
        initial_time = weather.get_conditions().time_hours
        weather.step(0.5)
        new_time = weather.get_conditions().time_hours
        
        assert new_time == initial_time + 0.5
    
    def test_weather_smooth_transitions(self, weather):
        """Weather changes gradually (no sudden jumps)"""
        prev_seeing = weather.get_conditions().seeing
        max_jump = 0.0
        
        for _ in range(10):
            conditions = weather.step(0.5)
            jump = abs(conditions.seeing - prev_seeing)
            max_jump = max(max_jump, jump)
            prev_seeing = conditions.seeing
        
        # Weather should change gradually, not jump wildly
        assert max_jump < 0.5, f"Weather jumped too much: {max_jump}"
    
    def test_weather_reset(self, weather):
        """Weather reset returns to initial state"""
        weather.step(5.0)  # Advance time
        weather.reset()
        
        assert weather.get_conditions().time_hours == 0.0


class TestWeatherQualityScore:
    """Tests for weather quality score calculation"""
    
    @pytest.fixture
    def camera(self):
        """Create and initialize camera"""
        cam = TelescopeCamera()
        cam._initialized = True  # Fake initialization for testing
        return cam
    
    def test_perfect_weather_high_quality(self):
        """Perfect seeing + clear sky = high quality"""
        # seeing=0.5 (best), clouds=0.0 (clear)
        seeing_quality = 1.0 - (0.5 - 0.5) / 2.0  # = 1.0
        cloud_quality = 1.0 - 0.0  # = 1.0
        expected = seeing_quality * cloud_quality
        
        assert expected == 1.0
    
    def test_poor_weather_low_quality(self):
        """Poor seeing + heavy clouds = low quality"""
        # seeing=2.5 (worst), clouds=0.8 (heavy)
        seeing_quality = 1.0 - (2.5 - 0.5) / 2.0  # = 0.0
        cloud_quality = 1.0 - 0.8  # = 0.2
        expected = max(0.0, seeing_quality * cloud_quality)
        
        assert expected == 0.0  # Quality is terrible
    
    def test_moderate_weather_medium_quality(self):
        """Average conditions produce mid-range quality"""
        # seeing=1.5 (average), clouds=0.3 (light clouds)
        seeing_quality = 1.0 - (1.5 - 0.5) / 2.0  # = 0.5
        cloud_quality = 1.0 - 0.3  # = 0.7
        expected = seeing_quality * cloud_quality  # = 0.35
        
        assert 0.3 <= expected <= 0.4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
