"""
Unit tests for SessionRecorder.

Run with: python3 -m pytest tests/test_session_recorder.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import json
import shutil
import tempfile
from datetime import datetime

from src.utils.session_recorder import SessionRecorder, IterationData, SessionMetadata


class TestSessionRecorder:
    """Tests for SessionRecorder class"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests"""
        tmp = tempfile.mkdtemp()
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    @pytest.fixture
    def recorder(self, temp_dir):
        """Create a recorder with temp directory"""
        return SessionRecorder(base_dir=temp_dir)

    def test_start_session_creates_directories(self, recorder, temp_dir):
        """Starting a session creates required directories"""
        session_id = recorder.start_session({"max_iterations": 4})
        
        assert session_id is not None
        assert session_id.startswith("session_")
        
        session_dir = Path(temp_dir) / session_id
        assert session_dir.exists()
        assert (session_dir / "iterations").exists()
        assert (session_dir / "images").exists()

    def test_start_session_initializes_metadata(self, recorder):
        """Starting a session initializes metadata correctly"""
        config = {"max_iterations": 8, "num_transients": 2}
        session_id = recorder.start_session(config)
        
        assert recorder.metadata is not None
        assert recorder.metadata.session_id == session_id
        assert recorder.metadata.config == config
        assert recorder.metadata.total_iterations == 0
        assert not recorder.metadata.completed

    def test_record_iteration_saves_json(self, recorder, temp_dir):
        """Recording an iteration saves JSON file"""
        session_id = recorder.start_session()
        
        context_state = {
            "iteration": 1,
            "weather": {"seeing": 1.2, "cloud_extinction": 0.1},
            "candidates": [],
            "decision": {"action": "wait", "confidence": 0.8},
        }
        
        recorder.record_iteration(
            iteration=1,
            context_state=context_state,
        )
        
        iteration_file = Path(temp_dir) / session_id / "iterations" / "iteration_001.json"
        assert iteration_file.exists()
        
        data = json.loads(iteration_file.read_text())
        assert data["iteration"] == 1
        assert data["weather"]["seeing"] == 1.2

    def test_finalize_session_saves_metadata(self, recorder, temp_dir):
        """Finalizing a session saves metadata to JSON"""
        session_id = recorder.start_session({"test": True})
        
        # Record some iterations
        for i in range(3):
            recorder.record_iteration(
                iteration=i + 1,
                context_state={"iteration": i + 1, "candidates": []},
            )
        
        # Finalize
        metadata = recorder.finalize_session({"precision": 0.85})
        
        assert metadata.completed
        assert metadata.total_iterations == 3
        assert metadata.ground_truth_summary == {"precision": 0.85}
        
        session_file = Path(temp_dir) / session_id / "session.json"
        assert session_file.exists()
        
        saved_data = json.loads(session_file.read_text())
        assert saved_data["completed"] is True
        assert saved_data["total_iterations"] == 3

    def test_list_sessions(self, temp_dir):
        """List sessions returns all saved sessions"""
        # Create multiple sessions - IDs include microseconds for uniqueness
        for i in range(3):
            recorder = SessionRecorder(base_dir=temp_dir)
            recorder.start_session({"index": i})
            recorder.record_iteration(1, {"iteration": 1, "candidates": []})
            recorder.finalize_session()
        
        sessions = SessionRecorder.list_sessions(base_dir=temp_dir)
        assert len(sessions) == 3

    def test_get_session(self, recorder, temp_dir):
        """Get session retrieves metadata by ID"""
        session_id = recorder.start_session({"test": True})
        recorder.record_iteration(1, {"iteration": 1, "candidates": []})
        recorder.finalize_session()
        
        session = SessionRecorder.get_session(session_id, base_dir=temp_dir)
        assert session is not None
        assert session["session_id"] == session_id

    def test_get_iteration(self, recorder, temp_dir):
        """Get iteration retrieves iteration data"""
        session_id = recorder.start_session()
        recorder.record_iteration(1, {
            "iteration": 1,
            "candidates": [{"id": "C1", "status": "PENDING"}],
        })
        recorder.finalize_session()
        
        iteration = SessionRecorder.get_iteration(session_id, 1, base_dir=temp_dir)
        assert iteration is not None
        assert iteration["iteration"] == 1
        assert len(iteration["candidates"]) == 1


class TestIterationData:
    """Tests for IterationData dataclass"""

    def test_to_dict(self):
        """to_dict returns complete structure"""
        data = IterationData(
            iteration=5,
            timestamp="2026-01-01T00:00:00",
            weather={"seeing": 1.5},
            candidates=[{"id": "C1"}],
        )
        
        d = data.to_dict()
        assert d["iteration"] == 5
        assert d["weather"]["seeing"] == 1.5
        assert len(d["candidates"]) == 1


class TestSessionMetadata:
    """Tests for SessionMetadata dataclass"""

    def test_to_dict(self):
        """to_dict returns complete structure"""
        metadata = SessionMetadata(
            session_id="session_123",
            start_time="2026-01-01T00:00:00",
            total_iterations=10,
            completed=True,
        )
        
        d = metadata.to_dict()
        assert d["session_id"] == "session_123"
        assert d["total_iterations"] == 10
        assert d["completed"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
