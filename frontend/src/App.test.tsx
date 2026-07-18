import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ForecastPanel } from "./components/Charts";
import { ActionPanel } from "./components/ActionPanel";
import { PlaybackControls } from "./components/PlaybackControls";
import { Topology } from "./components/Topology";
import { useCommandCenter } from "./hooks/useCommandCenter";
import type { CommandState } from "./types/api";

const baseState: CommandState = {
  session_id: "s1",
  run_id: "r1",
  timestamp: "2013-06-01T00:00:00+07:00",
  status: "Paused",
  operation_mode: "Manual Approval",
  controller_id: "deterministic_mpc",
  scenario_id: "normal",
  compatibility_status: "compatible",
  kpis: {
    renewable_share_fraction: 0.42,
    operating_cost_vnd: 1_200_000,
    battery_soc_fraction: 0.61,
    transformer_utilization_fraction: 0.44,
    park_load_kw: 4100,
    pv_available_kw: 900,
    grid_import_kw: 1000,
    dppa_import_kw: 500,
    external_import_kw: 1500,
    renewable_shortfall_kwh: 200
  },
  topology: {
    nodes: [],
    edges: [
      { source: "Rooftop PV", target: "Electronics_A", kw: 500, style: "pv", active: true, width: 4 },
      { source: "Grid", target: "Electronics_A", kw: 0, style: "grid", active: false, width: 1 },
      { source: "Rooftop PV", target: "BESS", kw: 100, style: "pv", active: true, width: 2 }
    ]
  },
  alerts: [],
  history: [],
  timings: {},
  completed_hours: 0,
  maximum_hours: 24,
  fallback_active: false
};

afterEach(() => cleanup());

describe("command center components", () => {
  it("shows designed forecast placeholder before forecasting", () => {
    const { container } = render(<ForecastPanel forecast={null} state={baseState} />);
    expect(screen.getByText(/Forecast appears here during the first live cycle/)).toBeInTheDocument();
    expect(container.querySelector("svg")).toBeNull();
  });

  it("renders fallback action as a distinct warning", () => {
    render(<ActionPanel plan={{ park_plan: [], tenant_plan: [], recommended_action: {}, solver: {}, objective: [], fallback_active: true, fallback_reason: "solver infeasible", valid_for_execution: true }} state={{ ...baseState, fallback_active: true }} mode="manual" running={false} countdown="paused" onExecute={() => undefined} />);
    expect(screen.getByText(/validated safe fallback dispatch/)).toBeInTheDocument();
    expect(screen.getByText("Approve Fallback Action")).toBeInTheDocument();
  });

  it("uses user-friendly advanced labels and exposes no unrelated pages", () => {
    render(<PlaybackControls mode="manual" setMode={() => undefined} controller="deterministic_mpc" setController={() => undefined} scenario="normal" setScenario={() => undefined} playbackSeconds={5} setPlaybackSeconds={() => undefined} maxHours={24} setMaxHours={() => undefined} running={false} startSelectedMode={() => undefined} pause={() => undefined} onReset={() => undefined} onStep={() => undefined} onForecastPlan={() => undefined} loading={false} />);
    expect(screen.getAllByText("Cost & Peak Optimizer").length).toBeGreaterThan(0);
    expect(screen.getByText("Operator Approval")).toBeInTheDocument();
    expect(screen.queryByText(/Water|Effluent|Investment Lab/i)).not.toBeInTheDocument();
  });

  it("renders live topology from backend flow values", () => {
    render(<Topology state={baseState} plan={null} viewModeLabel="LIVE EXECUTED FLOW" />);
    expect(screen.getByRole("img", { name: "live energy topology with renewable, grid, battery, transformer, and tenants" })).toBeInTheDocument();
    expect(screen.getAllByText("500 kW").length).toBeGreaterThan(0);
    expect(screen.getByText("Battery Storage")).toBeInTheDocument();
  });
});

vi.mock("./api/client", () => {
  const response = (timestamp: string) => ({
    session_id: "s1",
    run_id: "r1",
    state: { ...baseState, timestamp },
    alerts: [],
    history: [],
    timings: {},
    fallback_active: false,
    message: "ok"
  });
  return {
    createSession: vi.fn(async () => ({ session_id: "s1", run_id: "r1", state: baseState })),
    resetSession: vi.fn(async () => ({ session_id: "s1", run_id: "r2", state: { ...baseState, run_id: "r2" } })),
    forecast: vi.fn(async () => ({ ...response(baseState.timestamp), forecast: { aggregate: [], load: [], solar: [], metadata: {} } })),
    plan: vi.fn(async () => ({ ...response(baseState.timestamp), plan: { park_plan: [], tenant_plan: [], recommended_action: {}, solver: {}, objective: [], decision_comparison: {}, fallback_active: false, valid_for_execution: true } })),
    execute: vi.fn(async () => response("2013-06-01T01:00:00+07:00")),
    controlCycle: vi.fn(async () => response("2013-06-01T01:00:00+07:00")),
    loadBenchmark: vi.fn(async () => ({ rows: [] })),
    loadProvenance: vi.fn(async () => ({ data: { disclosures: [] } }))
  };
});

function Harness() {
  const command = useCommandCenter();
  return (
    <div>
      <span>{command.state?.timestamp ?? "loading"}</span>
      <span>{command.phase}</span>
      <span>{command.running ? "running" : "paused"}</span>
      <span>hours {command.completedHours}</span>
      <button onClick={() => command.setMode("auto")}>auto</button>
      <button onClick={() => command.startLiveSimulation()}>start</button>
      <button onClick={() => command.pause()}>pause</button>
      <button onClick={() => command.runGuidedDemo()}>guided</button>
    </div>
  );
}

describe("frontend live controls", () => {
  it("starts ready and exposes visible live phases", async () => {
    render(<Harness />);
    await screen.findByText(baseState.timestamp);
    expect(screen.getByText("paused")).toBeInTheDocument();
    fireEvent.click(screen.getByText("auto"));
    fireEvent.click(screen.getByText("start"));
    await screen.findByText("2013-06-01T01:00:00+07:00");
    fireEvent.click(screen.getByText("pause"));
    expect(screen.getByText("paused")).toBeInTheDocument();
  });

  it("runs a one-click three-hour guided demo", async () => {
    render(<Harness />);
    await screen.findByText(baseState.timestamp);
    fireEvent.click(screen.getByText("guided"));
    await screen.findByText("hours 3", {}, { timeout: 6000 });
    expect(screen.getByText("2013-06-01T01:00:00+07:00")).toBeInTheDocument();
  });
});
