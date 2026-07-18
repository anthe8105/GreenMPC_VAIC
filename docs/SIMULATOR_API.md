# Simulator API

## Initialization

```python
from greenmpc.simulation.park import IndustrialParkSimulator

sim = IndustrialParkSimulator.from_processed_files()
state = sim.get_state()
```

## Observation

```python
baseline = sim.get_baseline_exogenous()
effective = sim.get_effective_exogenous()
window = sim.get_exogenous_window(horizon_hours=6)
```

## Action Construction

```python
from greenmpc.simulation.reference_action import build_reference_action

action = build_reference_action(state, sim.config)
```

The reference helper is a feasible-action constructor for simulator verification, not the final operational controller.

## Validation and Step

```python
validation = sim.validate_action(action)
if validation.valid:
    result = sim.step(action)
```

Invalid actions raise `InvalidActionError` and leave state unchanged.

## Events

```python
sim.activate_catalog_event("EVT_CLOUD_001")
active = sim.list_active_events()
effective, event_record = sim.preview_event_effects()
```

## Clone and Reset

```python
clone = sim.clone()
clone.step(build_reference_action(clone.get_state(), clone.config))

sim.reset()
```

Clones have independent runtime events and histories. Reset restores the initial timestamp, battery state, and configured initial events.

## History Export

```python
sim.export_history("data/outputs/stage3_smoke")
```

Exports are explicit and include states, actions, park energy, tenant energy, event effects, violations, and a simulation summary.
