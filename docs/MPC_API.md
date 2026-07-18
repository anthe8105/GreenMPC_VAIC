# MPC API

```python
from greenmpc.control import GreenMPCController, MPCMode
from greenmpc.forecasting.inference import ForecastService
from greenmpc.simulation.park import IndustrialParkSimulator

simulator = IndustrialParkSimulator.from_processed_files(start_timestamp="2013-11-08T09:00:00+07:00")
service = ForecastService.from_registry("configs/forecasting.yaml")
load_forecast, solar_forecast = service.forecast_all(tenant_hourly, park_hourly, simulator.get_state().timestamp_local, 6)

controller = GreenMPCController.from_config()
plan = controller.plan(simulator, load_forecast, solar_forecast, MPCMode.EXPECTED)
action = plan.first_action
validation = simulator.validate_action(action)
```

Use `plan_with_fallback(...)` only when a current-step fallback is acceptable and clearly labeled. The controller does not call `simulator.step()`.
