"""Contract-tested context bridge between SigMap and Codex."""

from .bridge import Bridge, BridgeResult, ExitCode

__all__ = ["Bridge", "BridgeResult", "ExitCode", "__version__"]

__version__ = "0.8.0"
