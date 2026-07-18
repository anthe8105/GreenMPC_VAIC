from __future__ import annotations

import pytest

from greenmpc.forecasting.exceptions import ModelCompatibilityError
from greenmpc.forecasting.registry import validate_compatibility
from greenmpc.forecasting.training import current_fingerprints


def test_compatibility_mismatch_fails() -> None:
    with pytest.raises(ModelCompatibilityError):
        validate_compatibility({"fingerprints": {"a": "1"}}, {"a": "2"})


def test_selected_profile_fingerprint_keys_are_explicit() -> None:
    fingerprints = current_fingerprints()
    assert "selected_profiles" not in fingerprints
    assert "selected_tenant_profiles_csv_sha256" in fingerprints
    assert "selected_profiles_lock_yaml_sha256" in fingerprints
    assert fingerprints["selected_tenant_profiles_csv_sha256"] != fingerprints["selected_profiles_lock_yaml_sha256"]


def test_csv_and_yaml_fingerprints_are_both_validated() -> None:
    fingerprints = current_fingerprints()
    manifest = {"fingerprints": dict(fingerprints)}
    validate_compatibility(manifest, fingerprints)
    manifest["fingerprints"]["selected_tenant_profiles_csv_sha256"] = "bad"
    with pytest.raises(ModelCompatibilityError):
        validate_compatibility(manifest, fingerprints)
