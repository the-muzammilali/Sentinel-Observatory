"""
Basic unit tests for the Sentinel Agent module.

Tests cover:
- Data model validation
- Prompt generation
- Context management
- Agent initialization (without API calls)
"""

import pytest
import json
from datetime import datetime
from pathlib import Path
import tempfile
import shutil

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.models import (
    CandidateHistory,
    Candidate,
    WeatherContext,
    ContextState,
    AgentDecision,
    create_default_wait_decision,
    create_initial_context
)
from src.agent.prompts import (
    build_context_prompt,
    build_full_prompt,
    format_candidates_table
)
from src.agent.context_manager import ContextManager


class TestCandidateHistory:
    """Tests for CandidateHistory model."""
    
    def test_create_basic(self):
        """Test creating a basic history entry."""
        history = CandidateHistory(
            time="2024-03-15T01:00:00",
            magnitude=18.5,
            note="First detection",
            confidence=0.7
        )
        assert history.time == "2024-03-15T01:00:00"
        assert history.magnitude == 18.5
        assert history.confidence == 0.7
    
    def test_optional_magnitude(self):
        """Test that magnitude is optional."""
        history = CandidateHistory(
            time="2024-03-15T01:00:00",
            note="No magnitude available"
        )
        assert history.magnitude is None
        assert history.confidence == 0.5  # Default
    
    def test_confidence_bounds(self):
        """Test confidence validation bounds."""
        with pytest.raises(Exception):
            CandidateHistory(time="2024-03-15", confidence=1.5)
        
        with pytest.raises(Exception):
            CandidateHistory(time="2024-03-15", confidence=-0.1)


class TestCandidate:
    """Tests for Candidate model."""
    
    def test_create_basic(self):
        """Test creating a basic candidate."""
        candidate = Candidate(
            id="CAND_01",
            x=512,
            y=340,
            first_detected="2024-03-15T01:00:00",
            last_observed="2024-03-15T01:00:00"
        )
        assert candidate.id == "CAND_01"
        assert candidate.status == "NEW"  # Default
        assert len(candidate.history) == 0
    
    def test_id_pattern(self):
        """Test that ID must match CAND_XX pattern."""
        with pytest.raises(Exception):
            Candidate(
                id="invalid_id",
                x=0, y=0,
                first_detected="2024-03-15",
                last_observed="2024-03-15"
            )
    
    def test_add_observation(self):
        """Test adding observations to history."""
        candidate = Candidate(
            id="CAND_01",
            x=512, y=340,
            first_detected="2024-03-15T01:00:00",
            last_observed="2024-03-15T01:00:00"
        )
        
        # Add first observation
        candidate.add_observation(
            time="2024-03-15T01:30:00",
            magnitude=18.0,
            note="Second observation"
        )
        
        assert len(candidate.history) == 1
        assert candidate.last_observed == "2024-03-15T01:30:00"
        assert candidate.status == "NEW"  # Still new after 1 observation
        
        # Add second observation - should upgrade to MONITORING
        candidate.add_observation(
            time="2024-03-15T02:00:00",
            magnitude=17.5
        )
        
        assert len(candidate.history) == 2
        assert candidate.status == "MONITORING"
    
    def test_auto_confirm_on_brightening(self):
        """Test automatic confirmation on brightening pattern."""
        candidate = Candidate(
            id="CAND_02",
            x=100, y=200,
            first_detected="2024-03-15T01:00:00",
            last_observed="2024-03-15T01:00:00",
            status="MONITORING"
        )
        
        # Add brightening observations (decreasing magnitude = brighter)
        candidate.add_observation("T1", magnitude=19.0)
        candidate.add_observation("T2", magnitude=18.0)
        candidate.add_observation("T3", magnitude=17.0)  # Clear brightening
        
        assert candidate.status == "CONFIRMED"


class TestWeatherContext:
    """Tests for WeatherContext model."""
    
    def test_create_basic(self):
        """Test basic weather context creation."""
        weather = WeatherContext(
            seeing=1.2,
            cloud_extinction=0.15,
            observability="GOOD"
        )
        assert weather.seeing == 1.2
        assert weather.cloud_extinction == 0.15
    
    def test_from_weather_system(self):
        """Test automatic observability calculation."""
        # Excellent conditions
        weather = WeatherContext.from_weather_system(seeing=0.8, cloud_extinction=0.05)
        assert weather.observability == "EXCELLENT"
        
        # Good conditions
        weather = WeatherContext.from_weather_system(seeing=1.5, cloud_extinction=0.2)
        assert weather.observability == "GOOD"
        
        # Poor conditions
        weather = WeatherContext.from_weather_system(seeing=2.5, cloud_extinction=0.4)
        assert weather.observability == "POOR"
        
        # Unusable conditions
        weather = WeatherContext.from_weather_system(seeing=1.0, cloud_extinction=0.7)
        assert weather.observability == "UNUSABLE"


class TestContextState:
    """Tests for ContextState model."""
    
    def test_create_initial(self):
        """Test creating initial context."""
        weather = WeatherContext(seeing=1.0, cloud_extinction=0.1, observability="EXCELLENT")
        context = create_initial_context(
            simulated_time="2024-03-15T00:00:00",
            weather=weather
        )
        
        assert context.iteration == 1
        assert context.total_observations == 0
        assert len(context.candidates) == 0
    
    def test_next_candidate_id(self):
        """Test candidate ID generation."""
        weather = WeatherContext(seeing=1.0, cloud_extinction=0.1, observability="GOOD")
        context = ContextState(
            iteration=1,
            simulated_time="2024-03-15",
            weather=weather,
            candidates=[]
        )
        
        assert context.next_candidate_id() == "CAND_01"
        
        # Add a candidate
        context.candidates.append(Candidate(
            id="CAND_01",
            x=0, y=0,
            first_detected="2024-03-15",
            last_observed="2024-03-15"
        ))
        
        assert context.next_candidate_id() == "CAND_02"
    
    def test_get_active_candidates(self):
        """Test filtering active candidates."""
        weather = WeatherContext(seeing=1.0, cloud_extinction=0.1, observability="GOOD")
        context = ContextState(
            iteration=1,
            simulated_time="2024-03-15",
            weather=weather,
            candidates=[
                Candidate(id="CAND_01", x=0, y=0, first_detected="T", last_observed="T", status="MONITORING"),
                Candidate(id="CAND_02", x=0, y=0, first_detected="T", last_observed="T", status="REJECTED"),
                Candidate(id="CAND_03", x=0, y=0, first_detected="T", last_observed="T", status="CONFIRMED"),
            ]
        )
        
        active = context.get_active_candidates()
        assert len(active) == 2
        assert all(c.status != "REJECTED" for c in active)


class TestAgentDecision:
    """Tests for AgentDecision model."""
    
    def test_create_observe_again(self):
        """Test creating observe_again decision."""
        decision = AgentDecision(
            action="observe_again",
            reasoning="Need to confirm new detection",
            confidence=0.7
        )
        assert decision.action == "observe_again"
        assert decision.target_coordinates is None
    
    def test_slew_to_validation(self):
        """Test slew_to action coordinate validation."""
        decision = AgentDecision(
            action="slew_to",
            target_coordinates=(500, 600),
            reasoning="Moving to new field",
            confidence=0.9
        )
        assert decision.validate_slew_action() == True
        
        # Invalid: slew_to without coordinates
        decision_invalid = AgentDecision(
            action="slew_to",
            target_coordinates=None,
            reasoning="Missing coordinates",
            confidence=0.5
        )
        assert decision_invalid.validate_slew_action() == False
    
    def test_default_wait_decision(self):
        """Test default wait decision factory."""
        decision = create_default_wait_decision("Test fallback")
        
        assert decision.action == "wait"
        assert decision.confidence == 0.1
        assert "Test fallback" in decision.reasoning


class TestPrompts:
    """Tests for prompt generation."""
    
    def test_format_candidates_table_empty(self):
        """Test formatting empty candidate list."""
        result = format_candidates_table([])
        assert "No candidates" in result
    
    def test_format_candidates_table_with_data(self):
        """Test formatting candidate table."""
        candidates = [
            Candidate(
                id="CAND_01",
                x=512, y=340,
                first_detected="2024-03-15",
                last_observed="2024-03-15",
                status="MONITORING",
                history=[CandidateHistory(time="T1", magnitude=18.5)]
            )
        ]
        
        result = format_candidates_table(candidates)
        assert "CAND_01" in result
        assert "512" in result
        assert "MONITORING" in result
    
    def test_build_context_prompt(self):
        """Test building context prompt."""
        weather = WeatherContext(seeing=1.2, cloud_extinction=0.15, observability="GOOD")
        context = ContextState(
            iteration=5,
            simulated_time="2024-03-15T02:30:00",
            weather=weather,
            candidates=[],
            alerts_triggered=1
        )
        
        prompt = build_context_prompt(context)
        
        assert "Iteration:** 5" in prompt
        assert "2024-03-15T02:30:00" in prompt
        assert "1.20" in prompt  # Seeing
        assert "GOOD" in prompt
    
    def test_build_full_prompt(self):
        """Test building complete prompt."""
        weather = WeatherContext(seeing=1.0, cloud_extinction=0.1, observability="EXCELLENT")
        context = create_initial_context("2024-03-15T00:00:00", weather)
        
        prompt = build_full_prompt(context, include_examples=True)
        
        # Check system instruction included
        assert "SENTINEL" in prompt
        assert "autonomous" in prompt.lower()
        
        # Check examples included
        assert "Example" in prompt
        assert "observe_again" in prompt


class TestContextManager:
    """Tests for ContextManager."""
    
    @pytest.fixture
    def temp_state_dir(self):
        """Create temporary directory for state files."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    def test_initialize_context(self, temp_state_dir):
        """Test context initialization."""
        manager = ContextManager(state_dir=temp_state_dir)
        weather = WeatherContext(seeing=1.0, cloud_extinction=0.1, observability="EXCELLENT")
        
        context = manager.initialize_context(
            simulated_time="2024-03-15T00:00:00",
            weather=weather
        )
        
        assert context.iteration == 1
        assert len(context.candidates) == 0
    
    def test_save_and_load_context(self, temp_state_dir):
        """Test saving and loading context."""
        manager = ContextManager(state_dir=temp_state_dir)
        weather = WeatherContext(seeing=1.2, cloud_extinction=0.2, observability="GOOD")
        
        context = ContextState(
            iteration=5,
            simulated_time="2024-03-15T02:30:00",
            weather=weather,
            candidates=[
                Candidate(
                    id="CAND_01",
                    x=512, y=340,
                    first_detected="T1",
                    last_observed="T2",
                    status="MONITORING"
                )
            ],
            alerts_triggered=1
        )
        
        # Save
        filepath = manager.save_context(context)
        assert filepath.exists()
        
        # Load
        loaded = manager.load_context(filepath.name)
        
        assert loaded.iteration == 5
        assert len(loaded.candidates) == 1
        assert loaded.candidates[0].id == "CAND_01"
    
    def test_update_context(self, temp_state_dir):
        """Test context update with decision."""
        manager = ContextManager(state_dir=temp_state_dir)
        weather = WeatherContext(seeing=1.0, cloud_extinction=0.1, observability="EXCELLENT")
        
        old_context = ContextState(
            iteration=1,
            simulated_time="2024-03-15T01:00:00",
            weather=weather,
            candidates=[],
            total_observations=0
        )
        
        decision = AgentDecision(
            action="observe_again",
            reasoning="Detected new candidate",
            updated_candidates=[
                Candidate(
                    id="CAND_01",
                    x=512, y=340,
                    first_detected="2024-03-15T01:00:00",
                    last_observed="2024-03-15T01:00:00",
                    status="NEW"
                )
            ],
            confidence=0.7
        )
        
        new_weather = WeatherContext(seeing=1.1, cloud_extinction=0.12, observability="GOOD")
        
        new_context = manager.update_context(
            old_context=old_context,
            decision=decision,
            new_weather=new_weather,
            new_simulated_time="2024-03-15T01:30:00"
        )
        
        assert new_context.iteration == 2
        assert len(new_context.candidates) == 1
        assert new_context.candidates[0].id == "CAND_01"
        assert new_context.total_observations == 1
    
    def test_load_latest_context(self, temp_state_dir):
        """Test loading latest context."""
        manager = ContextManager(state_dir=temp_state_dir)
        weather = WeatherContext(seeing=1.0, cloud_extinction=0.1, observability="GOOD")
        
        # No files yet
        assert manager.load_latest_context() is None
        
        # Create some contexts
        for i in range(1, 4):
            context = ContextState(
                iteration=i,
                simulated_time=f"2024-03-15T0{i}:00:00",
                weather=weather,
                candidates=[]
            )
            manager.save_context(context)
        
        # Load latest
        latest = manager.load_latest_context()
        assert latest.iteration == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
