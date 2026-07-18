# MPC Safety

The controller never executes actions. It builds a plan, extracts the first `ParkAction`, and validates that action with the Stage 3 simulator. Stage 6 will own closed-loop evaluation.

Solver failures, infeasibility, invalid numerical results, and invalid extracted actions are not hidden. When configured, a clearly labeled fallback uses the Stage 3 current-step reference feasible-action constructor. That fallback uses no forecasts and performs no optimization; it is not GreenMPC performance and not the Stage 6 benchmark controller.

Battery discharge is counted as renewable in the linear MVP only because the current configuration assumes initial battery renewable fraction is 1.0, PV is renewable, DPPA is renewable eligible, and grid-to-battery charging is impossible. The simulator remains the source of truth for executed renewable accounting.
