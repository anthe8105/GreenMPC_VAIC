import type { ControllerId, OperationMode, PlanPayload, CommandState } from "../types/api";
import { controllerLabel } from "../types/labels";

export function ActionPanel({
  plan,
  state,
  mode,
  running,
  countdown,
  onExecute
}: {
  plan: PlanPayload | null;
  state: CommandState;
  mode: OperationMode;
  running: boolean;
  countdown: string;
  onExecute: () => void;
}) {
  if (!plan) {
    return (
      <div className="decision-empty">
        <strong>GreenMPC decision appears here during the live cycle.</strong>
        <span>The optimizer will choose the next-hour mix of solar, DPPA, battery, and grid supply after a forecast is available.</span>
      </div>
    );
  }

  const action = plan.recommended_action ?? {};
  const allocation = sourceAllocation(action);
  const total = Math.max(1, allocation.solar + allocation.dppa + allocation.battery + allocation.grid);
  const valid = Boolean(plan.valid_for_execution) && mode !== "shadow" && !running;
  const fallback = Boolean(plan.fallback_active ?? state.fallback_active);
  const comparison = materialComparison(plan.decision_comparison);

  return (
    <div className={`decision-layout ${fallback ? "fallback" : ""}`}>
      <div className="allocation-visual">
        <div className="demand-total">
          <span>Total next-hour demand</span>
          <strong>{kw(total)}</strong>
        </div>
        <div className="stacked-allocation" aria-label="next-hour source allocation">
          <div className="alloc solar" style={{ width: `${100 * allocation.solar / total}%` }} />
          <div className="alloc dppa" style={{ width: `${100 * allocation.dppa / total}%` }} />
          <div className="alloc battery" style={{ width: `${100 * allocation.battery / total}%` }} />
          <div className="alloc grid" style={{ width: `${100 * allocation.grid / total}%` }} />
        </div>
        <div className="allocation-legend">
          <Legend color="solar" label="Solar" value={kw(allocation.solar)} />
          <Legend color="dppa" label="DPPA" value={kw(allocation.dppa)} />
          <Legend color="battery" label="Battery" value={kw(allocation.battery)} />
          <Legend color="grid" label="Grid" value={kw(allocation.grid)} />
        </div>
      </div>

      <div className="decision-details">
        {fallback && <div className="fallback-warning">MPC could not produce an executable plan. This is a validated safe fallback dispatch, not a successful GreenMPC optimization.</div>}
        <dl>
          <div><dt>Battery action</dt><dd>{batteryAction(action)}</dd></div>
          <div><dt>Transformer loading</dt><dd>{percent(action.transformer_utilization_fraction)}</dd></div>
          <div><dt>Expected first-hour cost</dt><dd>{money((plan.decision_comparison as any)?.greenmpc?.planned_cost_vnd)}</dd></div>
          <div><dt>Validation</dt><dd>{String(action.validation_result ?? "validated")}</dd></div>
          <div><dt>Fallback</dt><dd>{fallback ? "visible" : "none"}</dd></div>
        </dl>
        <button className="primary-button execute-button" disabled={!valid} onClick={onExecute}>
          {running ? "Executing Automatically" : fallback ? "Approve Fallback Action" : "Approve and Execute Next Hour"}
        </button>
        {running && <p className="caption">Live Autonomous Demo will execute validated actions automatically. Next cycle: {countdown}.</p>}
        {mode === "shadow" && <p className="caption">Recommendation only - no command executed.</p>}
      </div>

      {comparison && <Comparison comparison={comparison} />}

      <details className="technical-details">
        <summary>Technical Details</summary>
        <p>Controller: {readableController(String(action.controller ?? state.controller_id))}</p>
        <p>Solver status: {String(action.solver_status ?? plan.solver?.solver_status ?? "not reported")}</p>
        <p>Forecast and planning latency are available in the backend state timings.</p>
      </details>
    </div>
  );
}

function Legend({ color, label, value }: { color: string; label: string; value: string }) {
  return <span><i className={color} />{label}: <strong>{value}</strong></span>;
}

function Comparison({ comparison }: { comparison: ReturnType<typeof materialComparison> }) {
  if (!comparison) return null;
  return (
    <details className="comparison-collapsed">
      <summary>Compare with conventional control</summary>
      <div className="comparison-list">
        <span>Expected cost difference: <strong>{money(comparison.costDiff)}</strong></span>
        <span>Grid-peak difference: <strong>{kw(comparison.gridDiff)}</strong></span>
        <span>Renewable-share difference: <strong>{(comparison.renewableDiff * 100).toFixed(1)} percentage points</strong></span>
        <span>Battery-action difference: <strong>{kw(comparison.batteryDiff)}</strong></span>
      </div>
    </details>
  );
}

function sourceAllocation(action: Record<string, unknown>) {
  return {
    solar: Number(action.pv_allocation_kw ?? 0),
    dppa: Number(action.dppa_allocation_kw ?? 0),
    battery: Number(action.battery_discharge_kw ?? 0),
    grid: Number(action.grid_import_kw ?? 0)
  };
}

function batteryAction(action: Record<string, unknown>) {
  const charge = Number(action.battery_charge_kw ?? 0);
  const discharge = Number(action.battery_discharge_kw ?? 0);
  if (charge > 1) return `charging ${kw(charge)}`;
  if (discharge > 1) return `discharging ${kw(discharge)}`;
  return "idle";
}

function materialComparison(raw: Record<string, unknown> | undefined) {
  const green = (raw?.greenmpc ?? {}) as Record<string, unknown>;
  const rule = (raw?.rule_based ?? {}) as Record<string, unknown>;
  if (!Object.keys(green).length) return null;
  const costDiff = Number(green.planned_cost_vnd ?? 0) - Number(rule.planned_cost_vnd ?? 0);
  const gridDiff = Number(green.grid_peak_kw ?? 0) - Number(rule.grid_peak_kw ?? 0);
  const renewableDiff = Number(green.renewable_share_fraction ?? 0) - Number(rule.renewable_share_fraction ?? 0);
  const batteryDiff = Number(green.battery_discharge_kw ?? 0) - Number(rule.battery_discharge_kw ?? 0);
  if (Math.abs(costDiff) < 1 && Math.abs(gridDiff) < 1 && Math.abs(renewableDiff) < 0.001 && Math.abs(batteryDiff) < 1) return null;
  return { costDiff, gridDiff, renewableDiff, batteryDiff };
}

function readableController(value: string) {
  if (value === "rule_based" || value === "deterministic_mpc" || value === "greenmpc_conservative") {
    return controllerLabel(value as ControllerId);
  }
  return value || "Cost & Peak Optimizer";
}

function kw(value: unknown) {
  return `${Number(value ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })} kW`;
}

function percent(value: unknown) {
  return `${(Number(value ?? 0) * 100).toFixed(1)}%`;
}

function money(value: unknown) {
  return `${(Number(value ?? 0) / 1_000_000).toFixed(3)}M VND`;
}
