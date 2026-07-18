import { useMemo, useState } from "react";
import type { CommandState, PlanPayload, TopologyEdge } from "../types/api";
import { useI18n } from "../i18n/LanguageContext";
import type { I18n } from "../i18n/LanguageContext";
import type { TranslationKey } from "../i18n/translations";
import solarIcon from "../assets/energy/solar.svg";
import dppaIcon from "../assets/energy/dppa.svg";
import gridIcon from "../assets/energy/grid.svg";
import batteryIcon from "../assets/energy/battery.svg";
import transformerIcon from "../assets/energy/transformer.svg";
import electronicsIcon from "../assets/energy/factory-electronics.svg";
import semiconductorIcon from "../assets/energy/factory-semiconductor.svg";
import textileIcon from "../assets/energy/factory-textile.svg";
import warehouseIcon from "../assets/energy/warehouse.svg";

const nodes: Record<string, { x: number; y: number; icon: string; labelKey: TranslationKey; kind: string }> = {
  "Rooftop Solar": { x: 90, y: 80, icon: solarIcon, labelKey: "node.rooftopSolar", kind: "source" },
  "DPPA Renewable Supply": { x: 90, y: 210, icon: dppaIcon, labelKey: "node.dppa", kind: "source" },
  Grid: { x: 90, y: 340, icon: gridIcon, labelKey: "node.grid", kind: "source" },
  "Battery Storage": { x: 90, y: 470, icon: batteryIcon, labelKey: "node.batteryStorage", kind: "source" },
  "Curtailed Solar": { x: 410, y: 80, icon: solarIcon, labelKey: "node.curtailedSolar", kind: "sink" },
  "Shared Park Bus / Transformer": { x: 410, y: 270, icon: transformerIcon, labelKey: "node.transformer", kind: "bus" },
  Electronics_A: { x: 735, y: 70, icon: electronicsIcon, labelKey: "node.electronicsA", kind: "tenant" },
  Semiconductor_B: { x: 735, y: 170, icon: semiconductorIcon, labelKey: "node.semiconductorB", kind: "tenant" },
  Textile_C: { x: 735, y: 270, icon: textileIcon, labelKey: "node.textileC", kind: "tenant" },
  Warehouse_D: { x: 735, y: 370, icon: warehouseIcon, labelKey: "node.warehouseD", kind: "tenant" },
  Electronics_E: { x: 735, y: 470, icon: electronicsIcon, labelKey: "node.electronicsE", kind: "tenant" }
};

const colors: Record<string, string> = {
  pv: "#0f766e",
  dppa: "#d97706",
  grid: "#2563eb",
  battery: "#4f46e5",
  curtailment: "#dc2626"
};

const sourceLabels: Record<string, string> = {
  "Rooftop PV": "Rooftop Solar",
  DPPA: "DPPA Renewable Supply",
  BESS: "Battery Storage",
  "Park bus": "Shared Park Bus / Transformer",
  Curtailment: "Curtailed Solar"
};

export function Topology({ state, plan, viewModeLabel }: { state: CommandState; plan: PlanPayload | null; viewModeLabel: string }) {
  const { t } = useI18n();
  const [viewMode, setViewMode] = useState<"executed" | "plan">("executed");
  const edges = useMemo(() => {
    if (viewMode === "plan" && plan?.tenant_plan?.length) return plannedEdges(plan);
    return executedEdges(state.topology.edges ?? []);
  }, [viewMode, plan, state.topology.edges]);
  const sourceSummaries = summarizeSources(edges);
  const tenantDemand = tenantDemandMap(state);
  const hasExecutedHistory = state.history.length > 0;
  return (
    <section className="topology-card">
      <div className="topology-controls">
        <div>
          <strong>{viewMode === "plan" ? t("topology.nextHourPlan") : hasExecutedHistory ? t("topology.liveExecutedFlow") : t("topology.currentMeasurements")}</strong>
          <span>{viewMode === "executed" && !hasExecutedHistory ? t("topology.awaitingDispatch") : viewModeLabel}</span>
        </div>
        <div className="segmented">
          <button className={viewMode === "executed" ? "active" : ""} onClick={() => setViewMode("executed")}>{t("topology.liveFlow")}</button>
          <button className={viewMode === "plan" ? "active" : ""} onClick={() => setViewMode("plan")} disabled={!plan}>{t("topology.nextHourPlanBtn")}</button>
        </div>
      </div>
      <svg className="topology-svg" viewBox="0 0 880 560" role="img" aria-label="live energy topology with renewable, grid, battery, transformer, and tenants">
        {edges.map((edge, index) => <FlowPath key={`${edge.source}-${edge.target}-${index}`} edge={edge} fallback={state.fallback_active} />)}
        {Object.entries(nodes).map(([key, node]) => (
          <Node key={key} nodeKey={key} node={node} state={state} sourceSummaries={sourceSummaries} tenantDemand={tenantDemand} />
        ))}
      </svg>
    </section>
  );
}

function Node({
  nodeKey,
  node,
  state,
  sourceSummaries,
  tenantDemand
}: {
  nodeKey: string;
  node: { x: number; y: number; icon: string; labelKey: TranslationKey; kind: string };
  state: CommandState;
  sourceSummaries: Record<string, number>;
  tenantDemand: Record<string, number>;
}) {
  const { t } = useI18n();
  const value = nodeValue(nodeKey, state, sourceSummaries, tenantDemand, t);
  const status = nodeStatus(nodeKey, state, sourceSummaries, t);
  return (
    <foreignObject x={node.x - 64} y={node.y - 44} width="128" height="88">
      <div className={`asset-node ${node.kind}`}>
        <img src={node.icon} alt="" />
        <strong>{t(node.labelKey)}</strong>
        <span>{value}</span>
        <em>{status}</em>
      </div>
    </foreignObject>
  );
}

function FlowPath({ edge, fallback }: { edge: TopologyEdge; fallback: boolean }) {
  const start = nodes[edge.source];
  const end = nodes[edge.target];
  if (!start || !end) return null;
  const active = Number(edge.kw) > 1e-6;
  const stroke = active ? (fallback ? "#dc2626" : colors[edge.style] ?? "#94a3b8") : "#d5dde8";
  const width = active ? Math.max(1.8, Number(edge.width ?? 2)) : 1;
  const controlX = (start.x + end.x) / 2;
  const d = `M${start.x + 58},${start.y} C${controlX},${start.y} ${controlX},${end.y} ${end.x - 58},${end.y}`;
  const labelX = (start.x + end.x) / 2;
  const labelY = (start.y + end.y) / 2 - 8;
  return (
    <g className={active ? "active-flow" : "inactive-flow"}>
      <path d={d} fill="none" stroke={stroke} strokeWidth={width} strokeLinecap="round" />
      {active && <text x={labelX} y={labelY} className="flow-label">{Number(edge.kw).toFixed(0)} kW</text>}
    </g>
  );
}

function executedEdges(raw: TopologyEdge[]) {
  return raw.map((edge) => ({
    ...edge,
    source: sourceLabels[edge.source] ?? edge.source,
    target: sourceLabels[edge.target] ?? edge.target
  }));
}

function plannedEdges(plan: PlanPayload): TopologyEdge[] {
  const tenantRows = plan.tenant_plan.filter((row) => Number(row.interval_index ?? 0) === 0);
  const parkRow = plan.park_plan.find((row) => Number(row.interval_index ?? 0) === 0);
  const edges: TopologyEdge[] = [];
  for (const row of tenantRows) {
    const tenant = String(row.tenant_id);
    edges.push(edge("Rooftop Solar", tenant, row.pv_to_tenant_kw, "pv"));
    edges.push(edge("DPPA Renewable Supply", tenant, row.dppa_to_tenant_kw, "dppa"));
    edges.push(edge("Grid", tenant, row.grid_to_tenant_kw, "grid"));
    edges.push(edge("Battery Storage", tenant, row.battery_to_tenant_kw, "battery"));
  }
  if (parkRow) {
    edges.push(edge("Rooftop Solar", "Battery Storage", parkRow.pv_to_battery_kw, "pv"));
    edges.push(edge("DPPA Renewable Supply", "Battery Storage", parkRow.dppa_to_battery_kw, "dppa"));
    edges.push(edge("Rooftop Solar", "Curtailed Solar", parkRow.pv_curtailment_kw, "curtailment"));
  }
  const maxKw = Math.max(1, ...edges.map((item) => Number(item.kw)));
  return edges.map((item) => ({ ...item, active: Number(item.kw) > 1e-6, width: 1 + 6 * Number(item.kw) / maxKw }));
}

function edge(source: string, target: string, value: unknown, style: string): TopologyEdge {
  return { source, target, kw: Math.max(0, Number(value ?? 0)), style, active: Number(value ?? 0) > 1e-6 };
}

function summarizeSources(edges: TopologyEdge[]) {
  const result: Record<string, number> = {};
  for (const edge of edges) result[edge.source] = (result[edge.source] ?? 0) + Number(edge.kw ?? 0);
  return result;
}

function tenantDemandMap(state: CommandState) {
  const result: Record<string, number> = { ...(state.tenant_load_kw_by_tenant ?? {}) };
  for (const edge of state.topology.edges ?? []) {
    const tenant = edge.target;
    if (tenant in nodes) result[tenant] = (result[tenant] ?? 0) + Number(edge.kw ?? 0);
  }
  return result;
}

function nodeValue(nodeKey: string, state: CommandState, sourceSummaries: Record<string, number>, tenantDemand: Record<string, number>, t: I18n["t"]) {
  if (nodeKey === "Rooftop Solar") return t("node.val.available", { value: kw(state.kpis.pv_available_kw) });
  if (nodeKey === "DPPA Renewable Supply") return t("node.val.supplied", { value: kw(sourceSummaries[nodeKey] ?? state.kpis.dppa_import_kw) });
  if (nodeKey === "Grid") return t("node.val.supplied", { value: kw(sourceSummaries[nodeKey] ?? state.kpis.grid_import_kw) });
  if (nodeKey === "Battery Storage") return t("node.val.soc", { value: percent(state.kpis.battery_soc_fraction) });
  if (nodeKey === "Curtailed Solar") return t("node.val.curtailed", { value: kw(sourceSummaries[nodeKey] ?? 0) });
  if (nodeKey === "Shared Park Bus / Transformer") return t("node.val.utilized", { value: percent(state.kpis.transformer_utilization_fraction) });
  return t("node.val.demand", { value: kw(tenantDemand[nodeKey] ?? 0) });
}

function nodeStatus(nodeKey: string, state: CommandState, sourceSummaries: Record<string, number>, t: I18n["t"]) {
  if (nodeKey === "Rooftop Solar") return Number(state.kpis.pv_available_kw ?? 0) <= 1 ? t("node.status.noGeneration") : t("node.status.available");
  if (nodeKey === "Battery Storage") {
    const battery = sourceSummaries[nodeKey] ?? 0;
    return battery > 1 ? t("node.status.discharging") : t("node.status.idle");
  }
  if (nodeKey === "Shared Park Bus / Transformer") return t("node.status.importLimit");
  if (nodeKey === "Curtailed Solar") return (sourceSummaries[nodeKey] ?? 0) > 1 ? t("node.status.unusedPV") : t("node.status.noCurtailment");
  if (nodeKey === "DPPA Renewable Supply") return t("node.status.renewableContract");
  if (nodeKey === "Grid") return t("node.status.utilityImport");
  return t("node.status.industrialTenant");
}

function kw(value: unknown) {
  return `${Number(value ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })} kW`;
}

function percent(value: unknown) {
  return `${(Number(value ?? 0) * 100).toFixed(1)}%`;
}
