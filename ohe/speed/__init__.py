"""ohe.speed — vehicle speed providers for the OHE pipeline."""
from ohe.speed.provider import NullSpeedProvider, SimulatedSpeedProvider, SpeedProvider

__all__ = ["SpeedProvider", "SimulatedSpeedProvider", "NullSpeedProvider"]
