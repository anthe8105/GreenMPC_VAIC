# Energy Accounting

Stage 3 records operational energy allocation for the offline demo. It is not an official renewable certificate.

## Source Allocation

For each tenant and timestep:

```text
PV + battery discharge + DPPA + grid = effective tenant load
```

The simulator rejects actions that do not reconcile within configured tolerances.

## Renewable Delivery

Direct renewable energy is rooftop PV plus renewable-eligible DPPA delivered directly to tenants. Battery charging is not counted as tenant renewable consumption until the battery later discharges to tenants.

## Battery Renewable Inventory

The configured method is `proportional_mixing`. The initial battery renewable-energy status is a configurable demo assumption.

Before discharge:

```text
renewable_fraction = renewable_energy_kwh / total_energy_kwh
```

Tenant battery discharge is split into renewable and nonrenewable or unclassified portions using that fraction. Battery losses are not allocated to tenants.

## Costs

Stage 3 calculates operating cost components:

- grid energy cost;
- DPPA direct and DPPA-to-battery purchase cost;
- battery degradation proxy cost.

PV has no operating-energy cost in the MVP. CAPEX, MPC objective penalties, peak-demand objective penalties, and investment economics remain out of scope.

## No Double Counting

Direct PV, direct DPPA, and renewable battery discharge are counted once. Charging energy is stored inventory, not immediate tenant renewable consumption.
