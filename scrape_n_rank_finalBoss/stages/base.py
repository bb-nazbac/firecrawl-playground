from abc import ABC, abstractmethod
from pathlib import Path
import logging

class BaseStage(ABC):
    """Abstract base class for pipeline stages."""

    STAGE_NAME = "base"  # Override in subclasses

    def __init__(self, config, spec, analytics, output, logger):
        self.config = config      # Stage-specific config section from YAML
        self.spec = spec          # AnalysisSpec (JSON spec)
        self.analytics = analytics  # AnalyticsEngine
        self.output = output      # OutputManager
        self.logger = logger      # logging.Logger

    @abstractmethod
    def run(self, input_data):
        """Execute stage with batch input. Returns output data for next stage."""
        pass

    def run_from_queue(self, queue, upstream_complete_event):
        """For streaming mode: consume from queue. Default: collect all then run()."""
        items = []
        while True:
            item = queue.get(timeout=1.0)
            if item is not None:
                items.append(item)
            elif upstream_complete_event.is_set() and queue._queue.empty():
                break
        return self.run(items)
