"""Target conversion and embodiment-specific motion lowering.

The portable task graph is the source dialect.  Robot motion models are target
dialects with explicit legality and independent lowerers, following the same core
separation used by MLIR dialect conversion: declare what is legal for a target,
select rewrite/lowering logic, and fail when an operation cannot be legalized.
"""

from roboweaver.lowering.motion import (
    ConversionTarget,
    MOTION_LOWERER_REGISTRY,
    MotionLowerer,
    TargetLoweringError,
    get_motion_lowerer,
)

__all__ = [
    "ConversionTarget", "MOTION_LOWERER_REGISTRY", "MotionLowerer",
    "TargetLoweringError", "get_motion_lowerer",
]
