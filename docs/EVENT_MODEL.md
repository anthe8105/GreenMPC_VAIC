# Event Model

Stage 3 supports runtime scenario events without modifying the Stage 2 baseline dataset.

## Baseline and Effective Values

Baseline values come from validated processed files. Effective values are copied from baseline values and then adjusted by active runtime events for the current timestep.

## Event Types

- `cloud_event`: multiplies effective PV availability.
- `production_shift_event`: multiplies one selected tenant load.
- `high_load_event`: multiplies all tenant loads.
- `combined_stress_event`: may multiply load, PV, and DPPA availability.

Multiple active events compose multiplicatively in deterministic event-id order.

## Catalog Activation

`scenario_events.csv` is a catalog only. Catalog events are inactive until explicitly activated through the simulator API. Runtime-injected events must start no earlier than the current simulator timestamp.

## Safety

Events never modify historical completed steps and never alter Stage 2 processed baseline files.
