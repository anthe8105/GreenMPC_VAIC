from __future__ import annotations

import pandas as pd

from greenmpc.config import load_config
from greenmpc.data.dataset_builder import load_dataset_build_config
from greenmpc.data.processed_validation import validate_park_hourly, validate_selected_profiles, validate_tenant_hourly


def test_existing_processed_outputs_validate_when_present() -> None:
    demo = load_config("configs/demo.yaml")
    cfg = load_dataset_build_config("configs/dataset_build.yaml")
    tenant = pd.read_csv("data/processed/tenant_hourly.csv")
    park = pd.read_csv("data/processed/park_hourly.csv")
    selected = pd.read_csv("data/processed/selected_tenant_profiles.csv")
    validate_selected_profiles(selected, [t.tenant_id for t in demo.tenants])
    validate_tenant_hourly(tenant, demo, cfg)
    validate_park_hourly(park, tenant, cfg)
