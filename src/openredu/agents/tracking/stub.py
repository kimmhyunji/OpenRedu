"""
Backward-compatibility shim.
TrackingMasterAgent is now implemented in master.py.
"""
from openredu.agents.tracking.master import TrackingMasterAgent
from openredu.core.state import LearnerState

__all__ = ["TrackingMasterAgent", "LearnerState"]
