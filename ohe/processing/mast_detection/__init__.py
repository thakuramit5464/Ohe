"""
processing/mast_detection
--------------------------
Mast detection sub-package.

Exports:
    MastDetector       — classical CV mast candidate detector
    MastEventTracker   — temporal consistency filter; emits confirmed MastEvents
"""

from ohe.processing.mast_detection.mast_detector import MastDetector
from ohe.processing.mast_detection.mast_event_tracker import MastEventTracker

__all__ = ["MastDetector", "MastEventTracker"]
