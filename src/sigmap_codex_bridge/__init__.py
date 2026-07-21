"""Contract-tested context bridge between SigMap and Codex."""

from .bridge import Bridge, BridgeResult, ExitCode
from .sigmap import (
    ContextProvider,
    ContextResult,
    ContextStatus,
    RawContextProvider,
    SigMapContextProvider,
)

__all__ = [
    "Bridge",
    "BridgeResult",
    "ExitCode",
    "ContextProvider",
    "ContextResult",
    "ContextStatus",
    "RawContextProvider",
    "SigMapContextProvider",
    "__version__",
]

__version__ = "1.0.0"
