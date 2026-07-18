# Digital Twin

Stage 3 implements a deterministic, controller-independent industrial-park simulator.

## State

The simulator state contains the current timestamp, immutable exogenous data, battery inventory, cumulative park metrics, and tenant-level cumulative energy totals. The battery state tracks total stored energy, SOC, renewable stored energy, and the renewable fraction.

## Action

`ParkAction` is an externally generated allocation request. It contains per-tenant PV, battery, DPPA, and grid supply plus park-level PV-to-battery, DPPA-to-battery, and PV curtailment. It does not contain unmet load or grid-to-battery charging.

## Transition

Each `step()` call:

1. Retrieves baseline processed data.
2. Applies enabled runtime events to copied effective values.
3. Strictly validates the action.
4. Updates battery energy and renewable inventory.
5. Creates tenant and park energy records.
6. Updates cumulative metrics and history.
7. Advances one hourly timestep.

Invalid actions raise `InvalidActionError` and do not mutate battery state, cumulative metrics, history, or the current timestamp.

## Battery

The battery transition is:

```text
next_energy_kwh =
current_energy_kwh
+ charge_efficiency * charge_power_kw * dt
- discharge_power_kw * dt / discharge_efficiency
```

The MVP forbids grid-to-battery charging and rejects simultaneous meaningful charge and discharge unless explicitly configured otherwise.

## Transformer

The MVP topology assumes all external imports pass through the shared transformer:

```text
external_import_kw = grid_to_tenant_kw + dppa_to_tenant_kw + dppa_to_battery_kw
```

Onsite rooftop PV and onsite battery discharge do not count against this external-import transformer constraint.

## Separation

The simulator never chooses actions. Controllers, forecasting, MPC optimization, Streamlit controls, and investment analysis remain outside Stage 3.

## Limitations

This simulator is a deterministic hourly accounting twin. It does not model AC power flow, voltage, reactive power, equipment telemetry, physical SCADA control, forecasting errors, or optimized dispatch.
