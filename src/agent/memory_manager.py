"""
Memory hygiene and decay management for long-running Sentinel sessions.

Implements:
- Token budget management for LLM context window
- Candidate lifecycle (NEW → MONITORING → BRIGHTENING/REJECTED → ALERTED → ARCHIVED → PRUNED)
- Age-based pruning with configurable thresholds
- Candidate reactivation on new anomalies
- Archive summarization for minimal token usage

Enables month-scale operation without memory growth or context poisoning.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class MemoryConfig:
    """
    Configuration for memory hygiene policies.
    
    All thresholds are configurable to tune behavior for
    different operational scenarios.
    """
    
    # Candidate limits
    max_active_candidates: int = 50
    max_archived_candidates: int = 100
    
    # Age-based thresholds
    stale_threshold_hours: float = 12.0
    prune_rejected_after_hours: float = 24.0
    archive_confirmed_after_hours: float = 48.0
    prune_archived_after_days: int = 7
    
    # Reactivation settings
    reactivation_radius_degrees: float = 0.01  # ~36 arcsec
    reactivation_signal_threshold: float = 0.5  # Magnitude difference
    
    # Confidence decay on stale candidates
    stale_decay_per_hour: float = 0.05  # 5% per hour


@dataclass
class CandidateSummary:
    """
    Compressed summary of an archived candidate.
    
    Preserves key information in minimal token footprint (~50 tokens).
    Used for statistics, analysis, and potential reactivation.
    """
    
    id: str
    
    # Classification info
    classification: str  # "SN_Ia", "CV", "asteroid", "cosmic_ray", etc.
    hypothesis: str      # "suspected supernova", "false positive", etc.
    
    # Outcome tracking
    outcome: str  # "confirmed", "rejected", "false_positive"
    alert_triggered: bool  # Was an alert sent for this candidate?
    
    # Statistics
    confidence_final: float
    confidence_peak: float
    observation_count: int
    first_seen: str  # ISO timestamp
    last_seen: str   # ISO timestamp
    duration_hours: float
    
    # Location (for reactivation matching)
    ra: float
    dec: float
    
    # Archival metadata
    archived_at: str  # ISO timestamp
    reactivation_count: int = 0  # How many times reactivated
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "classification": self.classification,
            "hypothesis": self.hypothesis,
            "outcome": self.outcome,
            "alert_triggered": self.alert_triggered,
            "confidence_final": self.confidence_final,
            "confidence_peak": self.confidence_peak,
            "observation_count": self.observation_count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "duration_hours": self.duration_hours,
            "ra": self.ra,
            "dec": self.dec,
            "archived_at": self.archived_at,
            "reactivation_count": self.reactivation_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandidateSummary":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class MemoryStats:
    """Statistics about current memory usage."""
    
    active_candidates: int
    archived_candidates: int
    total_observations: int
    
    # Token estimates
    estimated_active_tokens: int
    estimated_archived_tokens: int
    estimated_total_tokens: int
    
    # Hygiene actions taken
    candidates_pruned: int = 0
    candidates_archived: int = 0
    candidates_reactivated: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "active_candidates": self.active_candidates,
            "archived_candidates": self.archived_candidates,
            "total_observations": self.total_observations,
            "estimated_active_tokens": self.estimated_active_tokens,
            "estimated_archived_tokens": self.estimated_archived_tokens,
            "estimated_total_tokens": self.estimated_total_tokens,
            "candidates_pruned": self.candidates_pruned,
            "candidates_archived": self.candidates_archived,
            "candidates_reactivated": self.candidates_reactivated
        }


class MemoryManager:
    """
    Manages memory hygiene for long-running Sentinel sessions.
    
    Implements candidate lifecycle management, age-based pruning,
    archival summarization, and reactivation checking.
    """
    
    # Token cost estimates (conservative)
    TOKENS_PER_ACTIVE_CANDIDATE = 400
    TOKENS_PER_ARCHIVED_SUMMARY = 50
    
    def __init__(self, config: Optional[MemoryConfig] = None):
        """
        Initialize memory manager.
        
        Args:
            config: Memory configuration. Uses defaults if not provided.
        """
        self.config = config or MemoryConfig()
        self._stats = MemoryStats(
            active_candidates=0,
            archived_candidates=0,
            total_observations=0,
            estimated_active_tokens=0,
            estimated_archived_tokens=0,
            estimated_total_tokens=0
        )
    
    def apply_hygiene(
        self,
        candidates: List[Any],
        archived: List[CandidateSummary],
        current_time: datetime
    ) -> Tuple[List[Any], List[CandidateSummary], MemoryStats]:
        """
        Apply memory hygiene to candidate lists.
        
        This is the main entry point for memory management.
        
        Args:
            candidates: List of active Candidate objects
            archived: List of archived CandidateSummary objects
            current_time: Current simulated time
            
        Returns:
            Tuple of (pruned_candidates, updated_archived, stats)
        """
        stats = MemoryStats(
            active_candidates=len(candidates),
            archived_candidates=len(archived),
            total_observations=sum(
                len(getattr(c, 'history', [])) for c in candidates
            ),
            estimated_active_tokens=0,
            estimated_archived_tokens=0,
            estimated_total_tokens=0
        )
        
        # Step 1: Apply confidence decay to stale candidates
        candidates = self._apply_stale_decay(candidates, current_time)
        
        # Step 2: Archive confirmed candidates past threshold
        candidates, new_archived = self._archive_confirmed(
            candidates, current_time
        )
        archived.extend(new_archived)
        stats.candidates_archived += len(new_archived)
        
        # Step 3: Archive rejected candidates past threshold
        candidates, rejected_archived = self._archive_rejected(
            candidates, current_time
        )
        archived.extend(rejected_archived)
        stats.candidates_archived += len(rejected_archived)
        
        # Step 4: Prune old archived summaries
        archived, pruned_count = self._prune_old_archives(
            archived, current_time
        )
        stats.candidates_pruned += pruned_count
        
        # Step 5: Enforce active candidate limit
        if len(candidates) > self.config.max_active_candidates:
            candidates, overflow = self._enforce_active_limit(candidates)
            archived.extend(overflow)
            stats.candidates_archived += len(overflow)
        
        # Step 6: Enforce archived limit
        if len(archived) > self.config.max_archived_candidates:
            archived = archived[-self.config.max_archived_candidates:]
            excess = len(archived) - self.config.max_archived_candidates
            stats.candidates_pruned += max(0, excess)
        
        # Update stats
        stats.active_candidates = len(candidates)
        stats.archived_candidates = len(archived)
        stats.estimated_active_tokens = (
            len(candidates) * self.TOKENS_PER_ACTIVE_CANDIDATE
        )
        stats.estimated_archived_tokens = (
            len(archived) * self.TOKENS_PER_ARCHIVED_SUMMARY
        )
        stats.estimated_total_tokens = (
            stats.estimated_active_tokens + stats.estimated_archived_tokens
        )
        
        self._stats = stats
        
        logger.info(
            f"Memory hygiene: {stats.active_candidates} active, "
            f"{stats.archived_candidates} archived, "
            f"~{stats.estimated_total_tokens} tokens"
        )
        
        return candidates, archived, stats
    
    def _apply_stale_decay(
        self,
        candidates: List[Any],
        current_time: datetime
    ) -> List[Any]:
        """Apply confidence decay to stale candidates."""
        threshold = timedelta(hours=self.config.stale_threshold_hours)
        
        for candidate in candidates:
            if candidate.status not in ("BRIGHTENING", "ALERTED", "REJECTED"):
                last_obs = self._get_last_observation_time(candidate)
                if last_obs and (current_time - last_obs) > threshold:
                    # Calculate hours stale
                    hours_stale = (
                        (current_time - last_obs).total_seconds() / 3600
                    )
                    decay = self.config.stale_decay_per_hour * hours_stale
                    candidate.confidence = max(0.1, candidate.confidence - decay)
        
        return candidates
    
    def _archive_confirmed(
        self,
        candidates: List[Any],
        current_time: datetime
    ) -> Tuple[List[Any], List[CandidateSummary]]:
        """Archive confirmed candidates past threshold."""
        threshold = timedelta(hours=self.config.archive_confirmed_after_hours)
        
        active = []
        to_archive = []
        
        for candidate in candidates:
            if candidate.status in ("BRIGHTENING", "ALERTED"):
                last_obs = self._get_last_observation_time(candidate)
                if last_obs and (current_time - last_obs) > threshold:
                    summary = self.archive_candidate(candidate, current_time)
                    to_archive.append(summary)
                    continue
            active.append(candidate)
        
        return active, to_archive
    
    def _archive_rejected(
        self,
        candidates: List[Any],
        current_time: datetime
    ) -> Tuple[List[Any], List[CandidateSummary]]:
        """Archive rejected candidates past threshold."""
        threshold = timedelta(hours=self.config.prune_rejected_after_hours)
        
        active = []
        to_archive = []
        
        for candidate in candidates:
            if candidate.status == "REJECTED":
                last_obs = self._get_last_observation_time(candidate)
                if last_obs and (current_time - last_obs) > threshold:
                    summary = self.archive_candidate(candidate, current_time)
                    to_archive.append(summary)
                    continue
            active.append(candidate)
        
        return active, to_archive
    
    def _prune_old_archives(
        self,
        archived: List[CandidateSummary],
        current_time: datetime
    ) -> Tuple[List[CandidateSummary], int]:
        """Remove archived summaries past retention period."""
        threshold = timedelta(days=self.config.prune_archived_after_days)
        
        kept = []
        pruned = 0
        
        for summary in archived:
            archived_time = datetime.fromisoformat(summary.archived_at)
            if (current_time - archived_time) <= threshold:
                kept.append(summary)
            else:
                pruned += 1
        
        return kept, pruned
    
    def _enforce_active_limit(
        self,
        candidates: List[Any]
    ) -> Tuple[List[Any], List[CandidateSummary]]:
        """
        Enforce max active candidates by archiving lowest priority.
        
        Priority (keep first):
        1. CONFIRMED status
        2. Higher confidence
        3. More observations
        """
        if len(candidates) <= self.config.max_active_candidates:
            return candidates, []
        
        # Sort by priority (lower = archive first)
        def priority(c):
            status_priority = {
                "ALERTED": 4,
                "BRIGHTENING": 3,
                "MONITORING": 2,
                "REJECTED": 1
            }
            return (
                status_priority.get(c.status, 0),
                c.confidence,
                len(getattr(c, 'history', []))
            )
        
        sorted_candidates = sorted(candidates, key=priority, reverse=True)
        
        keep = sorted_candidates[:self.config.max_active_candidates]
        archive = sorted_candidates[self.config.max_active_candidates:]
        
        # Convert overflow to summaries
        overflow_summaries = [
            self.archive_candidate(c, datetime.now())
            for c in archive
        ]
        
        return keep, overflow_summaries
    
    def archive_candidate(
        self,
        candidate: Any,
        archive_time: datetime
    ) -> CandidateSummary:
        """
        Create compressed summary from a candidate.
        
        Args:
            candidate: Candidate object to archive
            archive_time: Time of archival
            
        Returns:
            CandidateSummary with minimal token footprint
        """
        # Extract timestamps
        first_seen = None
        last_seen = None
        peak_confidence = candidate.confidence
        
        history = getattr(candidate, 'history', [])
        if history:
            first_seen = history[0].time if hasattr(history[0], 'time') else None
            last_seen = history[-1].time if hasattr(history[-1], 'time') else None
            
            # Find peak confidence
            for obs in history:
                conf = getattr(obs, 'confidence', 0)
                if conf > peak_confidence:
                    peak_confidence = conf
        
        # Calculate duration
        duration_hours = 0.0
        if first_seen and last_seen:
            try:
                t1 = datetime.fromisoformat(str(first_seen))
                t2 = datetime.fromisoformat(str(last_seen))
                duration_hours = (t2 - t1).total_seconds() / 3600
            except (ValueError, TypeError):
                pass
        
        return CandidateSummary(
            id=candidate.id,
            classification=getattr(candidate, 'classification', 'unknown'),
            hypothesis=getattr(candidate, 'hypothesis', ''),
            outcome=self._determine_outcome(candidate),
            alert_triggered=getattr(candidate, 'alert_triggered', False),
            confidence_final=candidate.confidence,
            confidence_peak=peak_confidence,
            observation_count=len(history),
            first_seen=str(first_seen) if first_seen else "",
            last_seen=str(last_seen) if last_seen else "",
            duration_hours=duration_hours,
            ra=getattr(candidate, 'ra', 0.0),
            dec=getattr(candidate, 'dec', 0.0),
            archived_at=archive_time.isoformat(),
            reactivation_count=getattr(candidate, 'reactivation_count', 0)
        )
    
    def check_reactivation(
        self,
        ra: float,
        dec: float,
        magnitude: float,
        archived: List[CandidateSummary]
    ) -> Optional[CandidateSummary]:
        """
        Check if a new detection matches an archived candidate.
        
        Args:
            ra: Right ascension of new detection
            dec: Declination of new detection
            magnitude: Magnitude of new detection
            archived: List of archived summaries to check
            
        Returns:
            Matching CandidateSummary if reactivation warranted, else None
        """
        radius = self.config.reactivation_radius_degrees
        
        for summary in archived:
            # Check position match
            if abs(ra - summary.ra) > radius:
                continue
            if abs(dec - summary.dec) > radius:
                continue
            
            # Position matches - this is a potential reactivation
            logger.info(
                f"Reactivation candidate found: {summary.id} at "
                f"({summary.ra:.4f}, {summary.dec:.4f})"
            )
            return summary
        
        return None
    
    def _determine_outcome(self, candidate: Any) -> str:
        """Determine outcome category for archival."""
        status = getattr(candidate, 'status', 'UNKNOWN')
        classification = getattr(candidate, 'classification', '').lower()
        
        if status in ("BRIGHTENING", "ALERTED"):
            return "confirmed"
        elif status == "REJECTED":
            # Check if it was a false positive
            false_positive_types = [
                "cosmic_ray", "artifact", "satellite", 
                "asteroid", "hot_pixel"
            ]
            if any(fp in classification for fp in false_positive_types):
                return "false_positive"
            return "rejected"
        else:
            return "inconclusive"
    
    def _get_last_observation_time(
        self,
        candidate: Any
    ) -> Optional[datetime]:
        """Get the timestamp of the last observation."""
        history = getattr(candidate, 'history', [])
        if not history:
            return None
        
        last = history[-1]
        time_str = getattr(last, 'time', None)
        
        if time_str:
            try:
                return datetime.fromisoformat(str(time_str))
            except (ValueError, TypeError):
                pass
        
        return None
    
    def get_memory_stats(self) -> MemoryStats:
        """Get current memory statistics."""
        return self._stats
    
    def estimate_tokens(
        self,
        active_count: int,
        archived_count: int
    ) -> int:
        """
        Estimate total token usage.
        
        Args:
            active_count: Number of active candidates
            archived_count: Number of archived summaries
            
        Returns:
            Estimated token count
        """
        return (
            active_count * self.TOKENS_PER_ACTIVE_CANDIDATE +
            archived_count * self.TOKENS_PER_ARCHIVED_SUMMARY
        )
