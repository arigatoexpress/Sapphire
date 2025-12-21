"""
Scientific Experiment Tracking & Data Logging
Tracks system revisions, experiments, and performance metrics for data-driven improvement.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from google.cloud import firestore

logger = logging.getLogger(__name__)


@dataclass
class Experiment:
    id: str
    name: str
    hypothesis: str
    start_time: float
    version_id: str
    metrics: Dict[str, List[float]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ExperimentTracker:
    """
    Tracks trading experiments and system performance metrics.
    Uses Firestore for persistent storage of experiment data.
    """

    def __init__(self, version_id: str = "v1.0.0"):
        self.version_id = version_id
        self.current_experiment: Optional[Experiment] = None
        self.db = firestore.Client()
        self.collection = "trading_experiments"
        self._setup_logging()

    def _setup_logging(self):
        """Setup structured logging for experiments."""
        # Ensure we have a dedicated experiment log functionality if needed
        pass

    def start_experiment(self, name: str, hypothesis: str, metadata: Dict[str, Any] = None) -> str:
        """
        Start a new tracking experiment.

        Args:
            name: Name of the experiment (e.g. "aggressive_order_cancellation")
            hypothesis: What we expect to happen (e.g. "Reduces slippage by 50%")
            metadata: Additional context tags

        Returns:
            Experiment ID
        """
        exp_id = str(uuid.uuid4())
        self.current_experiment = Experiment(
            id=exp_id,
            name=name,
            hypothesis=hypothesis,
            start_time=time.time(),
            version_id=self.version_id,
            metadata=metadata or {},
        )

        # Log start to DB
        doc_ref = self.db.collection(self.collection).document(exp_id)
        doc_ref.set(
            {
                "name": name,
                "hypothesis": hypothesis,
                "start_time": datetime.utcnow(),
                "version_id": self.version_id,
                "status": "running",
                "metadata": metadata or {},
            }
        )

        logger.info(f"🧪 Started Experiment {exp_id}: {name}")
        return exp_id

    def track_metric(self, metric_name: str, value: float, context: Dict[str, Any] = None):
        """
        Track a specific performance metric.

        Args:
            metric_name: e.g. "order_fill_time_ms", "slippage_bps"
            value: Numerical value
            context: Contextual data (symbol, order_id, etc)
        """
        if not self.current_experiment:
            # If no active manual experiment, log as 'continuous_monitoring'
            pass

        timestamp = datetime.utcnow()

        # Log to structured logger immediately
        log_entry = {
            "metric": metric_name,
            "value": value,
            "experiment_id": (
                self.current_experiment.id if self.current_experiment else "continuous"
            ),
            "timestamp": timestamp.isoformat(),
            "context": context or {},
        }
        logger.info(f"📊 Metric: {json.dumps(log_entry)}")

        # Store in Firestore sub-collection for granular analysis
        if self.current_experiment:
            self.db.collection(self.collection).document(self.current_experiment.id).collection(
                "metrics"
            ).add(log_entry)

            # Update local aggregation
            if metric_name not in self.current_experiment.metrics:
                self.current_experiment.metrics[metric_name] = []
            self.current_experiment.metrics[metric_name].append(value)

    def conclude_experiment(self, conclusion: str = ""):
        """Conclude the current experiment and generate summary."""
        if not self.current_experiment:
            return

        end_time = datetime.utcnow()
        duration = end_time.timestamp() - self.current_experiment.start_time

        # Calculate summary statistics
        summary = {}
        for metric, values in self.current_experiment.metrics.items():
            if values:
                summary[metric] = {
                    "count": len(values),
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                }

        # Update DB
        self.db.collection(self.collection).document(self.current_experiment.id).update(
            {
                "status": "completed",
                "end_time": end_time,
                "duration_seconds": duration,
                "conclusion": conclusion,
                "results_summary": summary,
            }
        )

        logger.info(
            f"🧪 Concluded Experiment {self.current_experiment.id}. Duration: {duration:.2f}s"
        )
        self.current_experiment = None


# Global instance
_tracker: Optional[ExperimentTracker] = None


def get_experiment_tracker() -> ExperimentTracker:
    global _tracker
    if _tracker is None:
        _tracker = ExperimentTracker()
    return _tracker
