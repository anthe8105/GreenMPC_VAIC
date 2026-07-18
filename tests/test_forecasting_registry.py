from __future__ import annotations

import pytest

from greenmpc.forecasting.exceptions import ModelCompatibilityError
from greenmpc.forecasting.registry import validate_compatibility


def test_compatibility_mismatch_fails() -> None:
    with pytest.raises(ModelCompatibilityError):
        validate_compatibility({"fingerprints": {"a": "1"}}, {"a": "2"})
