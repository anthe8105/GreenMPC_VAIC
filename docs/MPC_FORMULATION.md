# GreenMPC Formulation

Stage 5 implements a six-interval continuous linear MPC. Interval 0 uses the simulator's current effective load and PV; intervals 1-5 use Stage 4 forecast quantiles. Horizon 6 is retained only for forecasting diagnostics.

Decision variables are continuous nonnegative allocations: PV, battery, DPPA, and grid to each tenant; PV and DPPA to battery; PV curtailment; battery energy; grid peak; renewable shortfall; and terminal reserve shortfall. There are no binary variables, integer variables, grid export, grid-to-battery charging, or unmet-load variables.

Hard constraints enforce tenant energy balance, PV balance, DPPA availability, battery dynamics and limits, transformer capacity including grid and DPPA imports, and nonnegative allocations.

The objective separates actual operating-cost proxy components from control penalties. Operating cost includes grid energy, DPPA energy, and battery degradation proxy. Control penalties include grid peak, PV curtailment, renewable shortfall, and terminal reserve shortfall. The total control objective is not an electricity bill.

A continuous LP cannot exactly forbid simultaneous charging and discharging without binary variables. GreenMPC first solves with a throughput cost, detects any meaningful conflict, then transparently re-solves with the dominant interval direction fixed when needed.
