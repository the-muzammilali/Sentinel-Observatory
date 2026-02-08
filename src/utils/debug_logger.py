"""
Debug Logger for Marathon Analysis

Provides detailed, structured logging for debugging ground truth matching,
coordinate conversions, and detection pipeline.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class TransientInjectionLog:
    """Log entry for transient injection."""
    transient_id: str
    event_type: str
    sky_coords: tuple  # (ra, dec) in arcsec
    pixel_coords: tuple  # (x, y) expected pixel position
    peak_magnitude: float
    start_time: str
    duration_hours: float
    is_real: bool  # True for transient, False for artifact


@dataclass
class DetectionLog:
    """Log entry for differencer detection."""
    iteration: int
    candidate_id: str
    pixel_coords: tuple  # (x, y)
    sky_coords: tuple  # (ra, dec) in arcsec
    flux: float
    magnitude: float
    significance: float


@dataclass
class GroundTruthMatchLog:
    """Log entry for ground truth matching attempt."""
    iteration: int
    candidate_id: str
    candidate_sky_coords: tuple
    matched_event_id: Optional[str]
    distance_arcsec: Optional[float]
    match_threshold: float
    is_match: bool
    nearby_events: List[Dict]  # List of nearby ground truth events with distances


@dataclass
class AlertLog:
    """Log entry for alert trigger."""
    iteration: int
    candidate_id: str
    sky_coords: tuple
    is_true_positive: bool
    matched_event_id: Optional[str]
    distance_arcsec: Optional[float]


class DebugLogger:
    """
    Comprehensive debug logger for marathon analysis.
    
    Logs all critical events in a structured format for post-marathon analysis.
    """
    
    def __init__(self, output_dir: str = "logs/debug"):
        """
        Initialize debug logger.
        
        Args:
            output_dir: Directory to save debug logs
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique session ID
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.log_file = self.output_dir / f"marathon_{self.session_id}.json"
        
        # Storage for structured logs
        self.logs = {
            "session_id": self.session_id,
            "start_time": datetime.now().isoformat(),
            "transient_injections": [],
            "detections": [],
            "ground_truth_matches": [],
            "alerts": [],
            "summary": {}
        }
        
        # Setup file logger
        self.logger = logging.getLogger(f"DebugLogger.{self.session_id}")
        self.logger.setLevel(logging.DEBUG)
        
        # File handler for detailed logs
        fh = logging.FileHandler(self.output_dir / f"marathon_{self.session_id}.log")
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
        
        self.logger.info(f"Debug logger initialized: {self.session_id}")
    
    def log_transient_injection(
        self,
        transient_id: str,
        event_type: str,
        sky_coords: tuple,
        pixel_coords: tuple,
        peak_magnitude: float,
        start_time: str,
        duration_hours: float,
        is_real: bool = True
    ):
        """Log a transient injection event."""
        entry = TransientInjectionLog(
            transient_id=transient_id,
            event_type=event_type,
            sky_coords=sky_coords,
            pixel_coords=pixel_coords,
            peak_magnitude=peak_magnitude,
            start_time=start_time,
            duration_hours=duration_hours,
            is_real=is_real
        )
        
        self.logs["transient_injections"].append(asdict(entry))
        
        self.logger.info(
            f"INJECTION: {transient_id} ({event_type}) at sky ({sky_coords[0]:.3f}, {sky_coords[1]:.3f}) "
            f"→ pixel ({pixel_coords[0]}, {pixel_coords[1]}), mag={peak_magnitude:.2f}, "
            f"real={is_real}"
        )
    
    def log_detection(
        self,
        iteration: int,
        candidate_id: str,
        pixel_coords: tuple,
        sky_coords: tuple,
        flux: float,
        magnitude: float,
        significance: float
    ):
        """Log a differencer detection."""
        entry = DetectionLog(
            iteration=iteration,
            candidate_id=candidate_id,
            pixel_coords=pixel_coords,
            sky_coords=sky_coords,
            flux=flux,
            magnitude=magnitude,
            significance=significance
        )
        
        self.logs["detections"].append(asdict(entry))
        
        self.logger.info(
            f"DETECTION [Iter {iteration}]: {candidate_id} at pixel ({pixel_coords[0]}, {pixel_coords[1]}) "
            f"→ sky ({sky_coords[0]:.3f}, {sky_coords[1]:.3f}), "
            f"mag={magnitude:.2f}, sig={significance:.1f}σ"
        )
    
    def log_ground_truth_match(
        self,
        iteration: int,
        candidate_id: str,
        candidate_sky_coords: tuple,
        matched_event_id: Optional[str],
        distance_arcsec: Optional[float],
        match_threshold: float,
        nearby_events: List[Dict]
    ):
        """Log a ground truth matching attempt."""
        is_match = matched_event_id is not None
        
        entry = GroundTruthMatchLog(
            iteration=iteration,
            candidate_id=candidate_id,
            candidate_sky_coords=candidate_sky_coords,
            matched_event_id=matched_event_id,
            distance_arcsec=distance_arcsec,
            match_threshold=match_threshold,
            is_match=is_match,
            nearby_events=nearby_events
        )
        
        self.logs["ground_truth_matches"].append(asdict(entry))
        
        if is_match:
            self.logger.info(
                f"GT_MATCH [Iter {iteration}]: {candidate_id} at ({candidate_sky_coords[0]:.3f}, {candidate_sky_coords[1]:.3f}) "
                f"MATCHED {matched_event_id} (distance={distance_arcsec:.3f} arcsec)"
            )
        else:
            self.logger.warning(
                f"GT_NO_MATCH [Iter {iteration}]: {candidate_id} at ({candidate_sky_coords[0]:.3f}, {candidate_sky_coords[1]:.3f}) "
                f"NO MATCH within {match_threshold:.1f} arcsec. Nearby: {len(nearby_events)} events"
            )
            for event in nearby_events:
                self.logger.warning(
                    f"  - {event['id']} at ({event['ra']:.3f}, {event['dec']:.3f}), "
                    f"distance={event['distance']:.3f} arcsec"
                )
    
    def log_alert(
        self,
        iteration: int,
        candidate_id: str,
        sky_coords: tuple,
        is_true_positive: bool,
        matched_event_id: Optional[str],
        distance_arcsec: Optional[float]
    ):
        """Log an alert trigger."""
        entry = AlertLog(
            iteration=iteration,
            candidate_id=candidate_id,
            sky_coords=sky_coords,
            is_true_positive=is_true_positive,
            matched_event_id=matched_event_id,
            distance_arcsec=distance_arcsec
        )
        
        self.logs["alerts"].append(asdict(entry))
        
        if is_true_positive:
            self.logger.info(
                f"ALERT [Iter {iteration}]: {candidate_id} → TRUE POSITIVE "
                f"(matched {matched_event_id}, distance={distance_arcsec:.3f} arcsec)"
            )
        else:
            self.logger.error(
                f"ALERT [Iter {iteration}]: {candidate_id} → FALSE POSITIVE "
                f"at ({sky_coords[0]:.3f}, {sky_coords[1]:.3f})"
            )
    
    def log_summary(
        self,
        total_iterations: int,
        total_transients: int,
        total_detections: int,
        total_alerts: int,
        true_positives: int,
        false_positives: int,
        false_negatives: int,
        precision: float,
        recall: float,
        f1_score: float
    ):
        """Log final marathon summary."""
        self.logs["summary"] = {
            "total_iterations": total_iterations,
            "total_transients": total_transients,
            "total_detections": total_detections,
            "total_alerts": total_alerts,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "precision": precision,
            "recall": recall,
            "f1_score": f1_score
        }
        
        self.logger.info("=" * 70)
        self.logger.info("MARATHON SUMMARY")
        self.logger.info("=" * 70)
        self.logger.info(f"Total Iterations: {total_iterations}")
        self.logger.info(f"Total Transients Injected: {total_transients}")
        self.logger.info(f"Total Detections: {total_detections}")
        self.logger.info(f"Total Alerts: {total_alerts}")
        self.logger.info(f"True Positives: {true_positives}")
        self.logger.info(f"False Positives: {false_positives}")
        self.logger.info(f"False Negatives: {false_negatives}")
        self.logger.info(f"Precision: {precision:.2%}")
        self.logger.info(f"Recall: {recall:.2%}")
        self.logger.info(f"F1 Score: {f1_score:.2%}")
        self.logger.info("=" * 70)
    
    def finalize(self):
        """Save structured logs to JSON file."""
        try:
            self.logs["end_time"] = datetime.now().isoformat()
            
            # Save JSON file
            self.logger.info(f"Attempting to save JSON to: {self.log_file}")
            with open(self.log_file, 'w') as f:
                json.dump(self.logs, f, indent=2)
            
            self.logger.info(f"✓ JSON saved successfully: {self.log_file}")
            
            # Create human-readable summary
            summary_file = self.output_dir / f"summary_{self.session_id}.txt"
            self.logger.info(f"Attempting to save summary to: {summary_file}")
            self._write_summary(summary_file)
            self.logger.info(f"✓ Summary saved successfully: {summary_file}")
            
            return str(self.log_file)
        except Exception as e:
            self.logger.error(f"Error finalizing debug logs: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            # Return the log file path even if JSON/summary failed
            return str(self.log_file) if self.log_file else None
    
    def _write_summary(self, summary_file: Path):
        """Write human-readable summary."""
        with open(summary_file, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write("MARATHON DEBUG SUMMARY\n")
            f.write("=" * 70 + "\n\n")
            
            f.write(f"Session ID: {self.session_id}\n")
            f.write(f"Start Time: {self.logs['start_time']}\n")
            f.write(f"End Time: {self.logs.get('end_time', 'N/A')}\n\n")
            
            f.write("TRANSIENT INJECTIONS\n")
            f.write("-" * 70 + "\n")
            for inj in self.logs["transient_injections"]:
                f.write(f"  {inj['transient_id']} ({inj['event_type']})\n")
                f.write(f"    Sky: ({inj['sky_coords'][0]:.3f}, {inj['sky_coords'][1]:.3f}) arcsec\n")
                f.write(f"    Pixel: ({inj['pixel_coords'][0]}, {inj['pixel_coords'][1]})\n")
                f.write(f"    Magnitude: {inj['peak_magnitude']:.2f}\n")
                f.write(f"    Real: {inj['is_real']}\n\n")
            
            f.write("\nDETECTIONS BY ITERATION\n")
            f.write("-" * 70 + "\n")
            for det in self.logs["detections"]:
                f.write(f"  Iter {det['iteration']}: {det['candidate_id']}\n")
                f.write(f"    Pixel: ({det['pixel_coords'][0]}, {det['pixel_coords'][1]})\n")
                f.write(f"    Sky: ({det['sky_coords'][0]:.3f}, {det['sky_coords'][1]:.3f}) arcsec\n")
                f.write(f"    Magnitude: {det['magnitude']:.2f}, Significance: {det['significance']:.1f}σ\n\n")
            
            f.write("\nGROUND TRUTH MATCHES\n")
            f.write("-" * 70 + "\n")
            for match in self.logs["ground_truth_matches"]:
                status = "✓ MATCHED" if match['is_match'] else "✗ NO MATCH"
                f.write(f"  Iter {match['iteration']}: {match['candidate_id']} - {status}\n")
                if match['is_match']:
                    f.write(f"    Matched: {match['matched_event_id']}\n")
                    f.write(f"    Distance: {match['distance_arcsec']:.3f} arcsec\n")
                else:
                    f.write(f"    Threshold: {match['match_threshold']:.1f} arcsec\n")
                    if match['nearby_events']:
                        f.write(f"    Nearby events:\n")
                        for event in match['nearby_events']:
                            f.write(f"      - {event['id']}: {event['distance']:.3f} arcsec away\n")
                f.write("\n")
            
            f.write("\nALERTS\n")
            f.write("-" * 70 + "\n")
            for alert in self.logs["alerts"]:
                status = "TRUE POSITIVE" if alert['is_true_positive'] else "FALSE POSITIVE"
                f.write(f"  Iter {alert['iteration']}: {alert['candidate_id']} - {status}\n")
                if alert['is_true_positive']:
                    f.write(f"    Matched: {alert['matched_event_id']}\n")
                    f.write(f"    Distance: {alert['distance_arcsec']:.3f} arcsec\n")
                f.write("\n")
            
            if self.logs["summary"]:
                f.write("\nFINAL METRICS\n")
                f.write("-" * 70 + "\n")
                s = self.logs["summary"]
                f.write(f"  Iterations: {s['total_iterations']}\n")
                f.write(f"  Transients: {s['total_transients']}\n")
                f.write(f"  Detections: {s['total_detections']}\n")
                f.write(f"  Alerts: {s['total_alerts']}\n")
                f.write(f"  True Positives: {s['true_positives']}\n")
                f.write(f"  False Positives: {s['false_positives']}\n")
                f.write(f"  False Negatives: {s['false_negatives']}\n")
                f.write(f"  Precision: {s['precision']:.2%}\n")
                f.write(f"  Recall: {s['recall']:.2%}\n")
                f.write(f"  F1 Score: {s['f1_score']:.2%}\n")
        
        self.logger.info(f"Human-readable summary saved to: {summary_file}")


# Global debug logger instance
_debug_logger: Optional[DebugLogger] = None


def get_debug_logger() -> Optional[DebugLogger]:
    """Get the global debug logger instance."""
    return _debug_logger


def initialize_debug_logger(output_dir: str = "logs/debug") -> DebugLogger:
    """Initialize the global debug logger."""
    global _debug_logger
    _debug_logger = DebugLogger(output_dir)
    return _debug_logger


def finalize_debug_logger() -> Optional[str]:
    """Finalize and save debug logs."""
    global _debug_logger
    if _debug_logger:
        log_file = _debug_logger.finalize()
        _debug_logger = None
        return log_file
    return None
