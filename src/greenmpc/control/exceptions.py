"""Control-layer exceptions for GreenMPC."""

from __future__ import annotations


class ControlError(Exception):
    """Base class for MPC control errors."""


class MPCConfigError(ControlError):
    """Raised when MPC configuration is invalid."""


class MPCInputError(ControlError):
    """Raised when planning inputs are invalid or leaky."""


class MPCSolverError(ControlError):
    """Raised when the LP solver fails or returns an unusable result."""


class MPCInfeasibleError(MPCSolverError):
    """Raised when the MPC LP is infeasible."""


class MPCPostprocessingError(ControlError):
    """Raised when solved values cannot be converted to a valid action."""


class MPCFallbackError(ControlError):
    """Raised when fallback action construction also fails."""


class UnsupportedRenewableInventoryForLinearMPCError(ControlError):
    """Raised when Stage 3 renewable inventory assumptions do not fit the linear MVP."""
