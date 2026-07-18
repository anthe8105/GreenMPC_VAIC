from __future__ import annotations

import pytest

from greenmpc.forecasting.exceptions import LeakageError
from greenmpc.forecasting.features import audit_feature_manifest


def test_future_feature_is_rejected() -> None:
    manifest = {
        "target_column": "target_load_kw",
        "feature_columns": ["future_load_kw"],
        "features": [{"feature_name": "future_load_kw", "source_timestamp_offset_hours": 1, "known_calendar_metadata": False}],
        "leakage_checks": {"target_column_excluded": True},
    }
    with pytest.raises(LeakageError):
        audit_feature_manifest(manifest)


def test_target_column_feature_is_rejected() -> None:
    manifest = {"target_column": "target_load_kw", "feature_columns": ["target_load_kw"], "features": [], "leakage_checks": {}}
    with pytest.raises(LeakageError):
        audit_feature_manifest(manifest)
