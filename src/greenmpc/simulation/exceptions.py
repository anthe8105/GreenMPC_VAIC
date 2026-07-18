"""Simulation-specific exceptions with user-facing detail."""

from __future__ import annotations


class SimulationError(Exception):
    """Base class for digital-twin simulation failures."""


class SimulationDataError(SimulationError):
    """Raised when processed input data is invalid for simulation."""


class SimulationFinishedError(SimulationError):
    """Raised when a step is requested after the dataset is exhausted."""


class InvalidTenantError(SimulationError):
    """Raised when an action or event references invalid tenant IDs."""


class InvalidActionError(SimulationError):
    """Raised when an action fails strict simulator validation."""

    def __init__(self, message: str, validation_result: object | None = None) -> None:
        super().__init__(message)
        self.validation_result = validation_result


class PowerBalanceError(InvalidActionError):
    """Raised for tenant power-balance failures."""


class PVAvailabilityError(InvalidActionError):
    """Raised for PV balance or availability failures."""


class DPPAAvailabilityError(InvalidActionError):
    """Raised for DPPA availability failures."""


class BatteryConstraintError(InvalidActionError):
    """Raised for battery physics or inventory failures."""


class TransformerConstraintError(InvalidActionError):
    """Raised for transformer-capacity failures."""


class EventValidationError(SimulationError):
    """Raised when a runtime event is invalid."""
