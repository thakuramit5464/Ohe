"""
core/exceptions.py
------------------
Custom exception hierarchy for the OHE system.
"""


class OHEBaseError(Exception):
    """Root exception for all OHE-specific errors."""


# --- Ingestion ---

class IngestionError(OHEBaseError):
    """Raised when a FrameProvider cannot open or read the source."""


class EndOfStreamError(IngestionError):
    """Raised (or used as sentinel) when video/stream has no more frames."""


# --- Processing ---

class ProcessingError(OHEBaseError):
    """Raised when a processing step fails unexpectedly."""


class CalibrationError(OHEBaseError):
    """Raised when calibration data is missing, malformed, or inconsistent."""


# --- Configuration ---

class ConfigError(OHEBaseError):
    """Raised when the configuration file is missing or invalid."""


# --- Rules ---

class RulesError(OHEBaseError):
    """Raised when the rules engine encounters an invalid threshold definition."""


# --- Logging ---

class LoggingError(OHEBaseError):
    """Raised when the session logger cannot write to its destination."""
