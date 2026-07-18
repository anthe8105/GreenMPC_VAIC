from __future__ import annotations

import streamlit as st

from greenmpc.config import load_config
from greenmpc.logging_utils import configure_logging


def main() -> None:
    configure_logging()
    st.set_page_config(page_title="GreenMPC Twin", layout="wide")

    try:
        config = load_config("configs/demo.yaml")
    except Exception as exc:
        st.error(f"Configuration could not be loaded: {exc}")
        st.stop()

    st.title(config.project.name)
    st.caption(config.project.synthetic_demo_notice)
    st.warning("No actual VRG operational data is currently used.")

    st.subheader("Project Stage")
    st.write("Stage 0 — Architecture initialized")

    st.subheader("Configured Tenants")
    tenant_rows = [
        {
            "Tenant ID": tenant.tenant_id,
            "Display Name": tenant.display_name,
            "Scenario Industry": tenant.scenario_industry,
            "Nominal Load (kW)": tenant.nominal_load_kw,
            "Renewable Target": tenant.renewable_target_fraction,
        }
        for tenant in config.tenants
    ]
    st.dataframe(tenant_rows, use_container_width=True, hide_index=True)

    st.subheader("Asset and Control Summary")
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Solar Portfolio", f"{config.solar.installed_capacity_kw:,.0f} kW")
    col_b.metric("Battery Capacity", f"{config.battery.energy_capacity_kwh:,.0f} kWh")
    col_c.metric("Transformer Limit", f"{config.grid.transformer_capacity_kw:,.0f} kW")
    col_d.metric("MPC Horizon", f"{config.mpc.horizon_hours} hours")

    st.subheader("Solver")
    st.write(config.mpc.solver)


if __name__ == "__main__":
    main()
