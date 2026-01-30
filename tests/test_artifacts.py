"""
Unit tests for artifact injection (false positives) in Project Sentinel.

Tests the ArtifactType enum, ArtifactEvent dataclass, and UniverseController
artifact injection methods added for Improvement #1: Introduce Ambiguity.

Run with: python -m pytest tests/test_artifacts.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
from datetime import datetime, timedelta

from src.simulation.universe import (
    UniverseController,
    ArtifactType,
    ArtifactEvent,
    TransientType
)


class TestArtifactTypeEnum:
    """Tests for ArtifactType enum"""
    
    def test_artifact_types_exist(self):
        """Verify all artifact types are defined"""
        assert ArtifactType.COSMIC_RAY.value == "Cosmic Ray"
        assert ArtifactType.HOT_PIXEL.value == "Hot Pixel"
        assert ArtifactType.SATELLITE_STREAK.value == "Satellite"
        assert ArtifactType.DETECTOR_ARTIFACT.value == "Detector"
    
    def test_artifact_types_count(self):
        """Should have exactly 4 artifact types"""
        assert len(ArtifactType) == 4


class TestArtifactEvent:
    """Tests for ArtifactEvent dataclass"""
    
    @pytest.fixture
    def sample_artifact(self):
        """Create a sample cosmic ray artifact"""
        return ArtifactEvent(
            id="ARTIFACT_001",
            x=1.0,
            y=2.0,
            artifact_time=datetime(2024, 3, 15, 22, 0, 0),
            duration_seconds=1.0,
            brightness_magnitude=16.0,
            artifact_type=ArtifactType.COSMIC_RAY
        )
    
    def test_artifact_visibility_within_window(self, sample_artifact):
        """Artifact is visible within its duration window"""
        # Exactly at artifact_time
        assert sample_artifact.is_visible(datetime(2024, 3, 15, 22, 0, 0)) == True
        # 0.5 seconds after
        assert sample_artifact.is_visible(datetime(2024, 3, 15, 22, 0, 0) + timedelta(seconds=0.5)) == True
        # Exactly at end
        assert sample_artifact.is_visible(datetime(2024, 3, 15, 22, 0, 1)) == True
    
    def test_artifact_invisible_before_start(self, sample_artifact):
        """Artifact is invisible before start time"""
        before_time = datetime(2024, 3, 15, 21, 59, 59)
        assert sample_artifact.is_visible(before_time) == False
    
    def test_artifact_invisible_after_end(self, sample_artifact):
        """Artifact is invisible after duration ends"""
        after_time = datetime(2024, 3, 15, 22, 0, 2)
        assert sample_artifact.is_visible(after_time) == False
    
    def test_artifact_magnitude_instant_on(self, sample_artifact):
        """Artifact has instant brightness (not Gaussian)"""
        # When visible, should return brightness_magnitude exactly
        visible_time = datetime(2024, 3, 15, 22, 0, 0)
        assert sample_artifact.get_magnitude_at_time(visible_time) == 16.0
    
    def test_artifact_magnitude_instant_off(self, sample_artifact):
        """Artifact disappears instantly (returns 99.0)"""
        invisible_time = datetime(2024, 3, 15, 22, 0, 5)
        assert sample_artifact.get_magnitude_at_time(invisible_time) == 99.0
    
    def test_artifact_flux_when_visible(self, sample_artifact):
        """Flux is positive when visible"""
        visible_time = datetime(2024, 3, 15, 22, 0, 0)
        flux = sample_artifact.get_flux_at_time(visible_time)
        assert flux > 0.0
    
    def test_artifact_flux_when_invisible(self, sample_artifact):
        """Flux is zero when invisible"""
        invisible_time = datetime(2024, 3, 15, 22, 0, 5)
        flux = sample_artifact.get_flux_at_time(invisible_time)
        assert flux == 0.0
    
    def test_ground_truth_flag(self, sample_artifact):
        """Artifact marked as ground truth artifact by default"""
        assert sample_artifact.is_ground_truth_artifact == True


class TestUniverseControllerArtifacts:
    """Tests for artifact injection in UniverseController"""
    
    @pytest.fixture
    def universe(self):
        """Create a universe for testing"""
        return UniverseController(
            field_size=10.0,
            num_stars=50,
            start_time=datetime(2024, 3, 15, 22, 0, 0),
            random_seed=42
        )
    
    def test_artifacts_list_initialized(self, universe):
        """Universe has empty artifacts list on init"""
        assert hasattr(universe, 'artifacts')
        assert len(universe.artifacts) == 0
    
    def test_inject_artifact_random_position(self, universe):
        """inject_artifact with no position uses random position"""
        artifact = universe.inject_artifact()
        
        assert artifact.id == "ARTIFACT_000"
        assert -5.0 <= artifact.x <= 5.0  # Within field bounds
        assert -5.0 <= artifact.y <= 5.0
        assert len(universe.artifacts) == 1
    
    def test_inject_artifact_specific_position(self, universe):
        """inject_artifact respects specified coordinates"""
        artifact = universe.inject_artifact(x=2.5, y=-1.5)
        
        assert artifact.x == 2.5
        assert artifact.y == -1.5
    
    def test_inject_artifact_type(self, universe):
        """inject_artifact sets correct artifact type"""
        artifact = universe.inject_artifact(artifact_type=ArtifactType.HOT_PIXEL)
        assert artifact.artifact_type == ArtifactType.HOT_PIXEL
    
    def test_inject_artifact_parameters(self, universe):
        """inject_artifact respects brightness and duration"""
        artifact = universe.inject_artifact(
            brightness_magnitude=14.5,
            duration_seconds=2.5
        )
        
        assert artifact.brightness_magnitude == 14.5
        assert artifact.duration_seconds == 2.5
    
    def test_inject_artifact_offset(self, universe):
        """inject_artifact with offset delays appearance"""
        artifact = universe.inject_artifact(offset_seconds=60.0)
        
        expected_time = universe.current_time + timedelta(seconds=60.0)
        assert artifact.artifact_time == expected_time
    
    def test_inject_false_positive_cluster(self, universe):
        """inject_false_positive_cluster creates multiple artifacts"""
        artifacts = universe.inject_false_positive_cluster(n_artifacts=5)
        
        assert len(artifacts) == 5
        assert len(universe.artifacts) == 5
        
        # All should have unique IDs
        ids = [a.id for a in artifacts]
        assert len(set(ids)) == 5
    
    def test_inject_cluster_cycles_types(self, universe):
        """Cluster injection cycles through provided types"""
        types = [ArtifactType.COSMIC_RAY, ArtifactType.SATELLITE_STREAK]
        artifacts = universe.inject_false_positive_cluster(
            n_artifacts=4,
            artifact_types=types
        )
        
        # Should alternate: COSMIC_RAY, SATELLITE, COSMIC_RAY, SATELLITE
        assert artifacts[0].artifact_type == ArtifactType.COSMIC_RAY
        assert artifacts[1].artifact_type == ArtifactType.SATELLITE_STREAK
        assert artifacts[2].artifact_type == ArtifactType.COSMIC_RAY
        assert artifacts[3].artifact_type == ArtifactType.SATELLITE_STREAK


class TestArtifactInSourceList:
    """Tests for artifact inclusion in ScopeSim source list"""
    
    @pytest.fixture
    def universe_with_artifact(self):
        """Universe with a visible artifact"""
        universe = UniverseController(
            field_size=10.0,
            num_stars=10,
            start_time=datetime(2024, 3, 15, 22, 0, 0),
            random_seed=42
        )
        # Inject artifact visible at current time
        universe.inject_artifact(
            x=0.0,
            y=0.0,
            brightness_magnitude=14.0,
            duration_seconds=300.0  # 5 minutes - plenty of time
        )
        return universe
    
    def test_visible_artifact_in_source_list(self, universe_with_artifact):
        """Visible artifact appears in ScopeSim source list"""
        source = universe_with_artifact.get_source_list_for_scopesim()
        
        # Should have 10 stars + 1 artifact = 11 sources
        # ScopeSim stores table in fields[0].field for TableSourceField
        assert len(source.table_fields) == 1  # One table field
        table = source.table_fields[0].field
        assert len(table) == 11
    
    def test_expired_artifact_not_in_source_list(self, universe_with_artifact):
        """Expired artifact excluded from source list"""
        # Move time forward past artifact duration
        universe_with_artifact.current_time += timedelta(seconds=600)
        
        source = universe_with_artifact.get_source_list_for_scopesim()
        
        # Should only have 10 stars (artifact expired)
        table = source.table_fields[0].field
        assert len(table) == 10


class TestGroundTruthWithArtifacts:
    """Tests for ground truth including artifact information"""
    
    @pytest.fixture
    def universe_mixed(self):
        """Universe with both transient and artifact"""
        universe = UniverseController(
            field_size=10.0,
            num_stars=10,
            start_time=datetime(2024, 3, 15, 22, 0, 0),
            random_seed=42
        )
        # Add real transient
        universe.add_transient(
            x=1.0, y=1.0,
            start_offset_hours=0.0,
            duration_hours=4.0,
            peak_magnitude=16.0
        )
        # Add artifact
        universe.inject_artifact(
            x=-1.0, y=-1.0,
            duration_seconds=60.0
        )
        return universe
    
    def test_ground_truth_has_artifacts_key(self, universe_mixed):
        """Ground truth includes visible_artifacts key"""
        truth = universe_mixed.get_ground_truth()
        
        assert "visible_artifacts" in truth
        assert "total_artifacts" in truth
    
    def test_ground_truth_artifact_marked(self, universe_mixed):
        """Artifacts have is_artifact=True flag"""
        truth = universe_mixed.get_ground_truth()
        
        for artifact in truth["visible_artifacts"]:
            assert artifact["is_artifact"] == True
    
    def test_ground_truth_transient_not_artifact(self, universe_mixed):
        """Transients have is_artifact=False flag"""
        truth = universe_mixed.get_ground_truth()
        
        for transient in truth["active_transients"]:
            assert transient["is_artifact"] == False
    
    def test_ground_truth_counts(self, universe_mixed):
        """Ground truth has correct counts"""
        truth = universe_mixed.get_ground_truth()
        
        assert truth["total_real_events"] == 1
        assert truth["total_artifacts"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
