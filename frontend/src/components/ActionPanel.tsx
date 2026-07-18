import type { ControllerId, OperationMode, PlanPayload, CommandState } from "../types/api";
import { useI18n } from "../i18n/LanguageContext";
import type { I18n } from "../i18n/LanguageContext";

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
  const { t } = useI18n();
  if (!plan) {
    return (
      <div className="decision-empty">
        <strong>{t("decision.empty.title")}</strong>
        <span>{t("decision.empty.desc")}</span>
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
          <span>{t("decision.totalDemand")}</span>
          <strong>{kw(total)}</strong>
        </div>
        <div className="stacked-allocation" aria-label="next-hour source allocation">
          <div className="alloc solar" style={{ width: `${100 * allocation.solar / total}%` }} />
          <div className="alloc dppa" style={{ width: `${100 * allocation.dppa / total}%` }} />
          <div className="alloc battery" style={{ width: `${100 * allocation.battery / total}%` }} />
          <div className="alloc grid" style={{ width: `${100 * allocation.grid / total}%` }} />
        </div>
        <div className="allocation-legend">
          <Legend color="solar" label={t("source.solar")} value={kw(allocation.solar)} />
          <Legend color="dppa" label={t("source.dppa")} value={kw(allocation.dppa)} />
          <Legend color="battery" label={t("source.battery")} value={kw(allocation.battery)} />
          <Legend color="grid" label={t("source.grid")} value={kw(allocation.grid)} />
        </div>
      </div>

      <div className="decision-details">
        {fallback && <div className="fallback-warning">{t("decision.fallbackWarning")}</div>}
        <dl>
          <div><dt>{t("decision.batteryAction")}</dt><dd>{batteryAction(action, t)}</dd></div>
          <div><dt>{t("decision.transformerLoading")}</dt><dd>{percent(action.transformer_utilization_fraction)}</dd></div>
          <div><dt>{t("decision.firstHourCost")}</dt><dd>{money((plan.decision_comparison as any)?.greenmpc?.planned_cost_vnd)}</dd></div>
          <div><dt>{t("decision.validation")}</dt><dd>{action.validation_result ? String(action.validation_result) : t("decision.validated")}</dd></div>
          <div><dt>{t("decision.fallback")}</dt><dd>{fallback ? t("decision.fallbackVisible") : t("decision.fallbackNone")}</dd></div>
        </dl>
        <button className="primary-button execute-button" disabled={!valid} onClick={onExecute}>
          {running ? t("execute.executingAuto") : fallback ? t("execute.approveFallback") : t("execute.approveExecute")}
        </button>
        {running && <p className="caption">{t("decision.autoNote", { countdown })}</p>}
        {mode === "shadow" && <p className="caption">{t("pb.shadowNote")}</p>}
      </div>

      {comparison && <Comparison comparison={comparison} t={t} />}

      <details className="technical-details">
        <summary>{t("tech.summary")}</summary>
        <p>{t("tech.controller", { value: readableController(String(action.controller ?? state.controller_id), t) })}</p>
        <p>{t("tech.solverStatus", { value: String(action.solver_status ?? plan.solver?.solver_status ?? t("tech.notReported")) })}</p>
        <p>{t("tech.latency")}</p>
      </details>
    </div>
  );
}

function Legend({ color, label, value }: { color: string; label: string; value: string }) {
  return <span><i className={color} />{label}: <strong>{value}</strong></span>;
}

function Comparison({ comparison, t }: { comparison: ReturnType<typeof materialComparison>; t: I18n["t"] }) {
  if (!comparison) return null;
  return (
    <details className="comparison-collapsed">
      <summary>{t("compare.summary")}</summary>
      <div className="comparison-list">
        <span>{t("compare.costDiff")} <strong>{money(comparison.costDiff)}</strong></span>
        <span>{t("compare.gridDiff")} <strong>{kw(comparison.gridDiff)}</strong></span>
        <span>{t("compare.renewableDiff")} <strong>{t("compare.renewableDiffValue", { value: (comparison.renewableDiff * 100).toFixed(1) })}</strong></span>
        <span>{t("compare.batteryDiff")} <strong>{kw(comparison.batteryDiff)}</strong></span>
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

function batteryAction(action: Record<string, unknown>, t: I18n["t"]) {
  const charge = Number(action.battery_charge_kw ?? 0);
  const discharge = Number(action.battery_discharge_kw ?? 0);
  if (charge > 1) return t("battery.charging", { value: kw(charge) });
  if (discharge > 1) return t("battery.discharging", { value: kw(discharge) });
  return t("battery.idle");
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

function readableController(value: string, t: I18n["t"]) {
  if (value === "rule_based" || value === "deterministic_mpc" || value === "greenmpc_conservative") {
    return t(`controller.${value as ControllerId}`);
  }
  return value || t("controller.deterministic_mpc");
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
