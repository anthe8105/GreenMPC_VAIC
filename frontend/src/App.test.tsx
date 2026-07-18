import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ForecastPanel } from "./components/Charts";
import { ActionPanel } from "./components/ActionPanel";
import { PlaybackControls } from "./components/PlaybackControls";
import { Topology } from "./components/Topology";
import { InvestmentLabPage } from "./pages/InvestmentLabPage";
import { App } from "./App";
import { LanguageProvider } from "./i18n/LanguageContext";
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
    expect(screen.queryByText(/Water|Effluent/i)).not.toBeInTheDocument();
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
    loadProvenance: vi.fn(async () => ({ data: { disclosures: [] } })),
    loadInvestmentDefaults: vi.fn(async () => ({
      baseline: investmentCandidate(2500),
      proposal: investmentCandidate(3000),
      financial: {
        pv_capex_vnd_per_kwp: 1000,
        bess_energy_capex_vnd_per_kwh: 1000,
        bess_power_capex_vnd_per_kw: 1000,
        fixed_implementation_cost_vnd: 0,
        annual_pv_om_fraction: 0,
        annual_bess_om_fraction: 0,
        project_life_years: 10,
        annual_operating_days: 300,
        discount_rate: 0.1,
        assumptions_version: "test"
      },
      defaults: { scenario_id: "normal", controller_id: "deterministic_mpc", duration_hours: 24 },
      durations: { smoke_hours: 6, quick_hours: 24, evidence_hours: 72 },
      valuation_prices: [1100, 1500, 2000, 2500],
      disclosure: "Editable demonstration assumptions"
    })),
    createInvestmentAnalysis: vi.fn(async () => ({
      analysis_id: "inv_test",
      status: "completed",
      progress_percentage: 100,
      current_phase: "Completed",
      completed_hours: 6,
      requested_hours: 6,
      elapsed_seconds: 1
    })),
    getInvestmentStatus: vi.fn(async () => ({
      analysis_id: "inv_test",
      status: "completed",
      progress_percentage: 100,
      current_phase: "Completed",
      completed_hours: 6,
      requested_hours: 6,
      elapsed_seconds: 1
    })),
    getInvestmentResult: vi.fn(async () => ({
      analysis_id: "inv_test",
      scenario_id: "normal",
      controller_id: "deterministic_mpc",
      duration_hours: 6,
      completed_successfully: true,
      completed_hours: 6,
      baseline_configuration: investmentCandidate(2500),
      proposal_configuration: investmentCandidate(3000),
      technical_metrics: {
        baseline: investmentMetrics(0.4, 2000),
        proposal: investmentMetrics(0.5, 1800),
        comparison: {}
      },
      financial_metrics: {
        incremental_capex_vnd: 1000000,
        annualized_operating_savings_vnd: 200000,
        incremental_annual_om_vnd: 0,
        net_annual_savings_vnd: 200000,
        simple_payback_years: 5,
        payback_status: "calculated"
      },
      tenant_summary: [
        { case: "baseline", tenant_id: "Electronics_A", load_served_kwh: 100, renewable_share: 0.4, grid_energy_kwh: 60, shortfall_kwh: 10 },
        { case: "proposal", tenant_id: "Electronics_A", load_served_kwh: 100, renewable_share: 0.5, grid_energy_kwh: 50, shortfall_kwh: 0 }
      ],
      evidence_zip_path: "data/outputs/stage8_investment/inv_test/greenmpc_investment_inv_test.zip",
      loaded_from_cache: false,
      runtime_seconds: 1,
      assumptions: []
    })),
    listInvestmentAnalyses: vi.fn(async () => ({ analyses: [] }))
  };
});

function investmentCandidate(pv_capacity_kw: number) {
  return {
    pv_capacity_kw,
    battery_energy_capacity_kwh: 3000,
    battery_power_kw: 1000,
    minimum_soc_fraction: 0.1,
    initial_soc_fraction: 0.5,
    dppa_available_kw: 1500,
    dppa_price_vnd_per_kwh: 1750,
    dppa_availability_multiplier: 1,
    renewable_target_fraction: 0.55,
    transformer_capacity_kw: 5200,
    terminal_inventory_valuation_vnd_per_kwh: 2000
  };
}

function investmentMetrics(renewableShare: number, peak: number) {
  return {
    completed_steps: 6,
    total_load_served_kwh: 1000,
    inventory_adjusted_operating_cost_vnd: 1000000,
    total_realized_operating_cost_proxy_vnd: 1000000,
    park_renewable_share: renewableShare,
    peak_grid_import_kw: peak,
    peak_external_import_kw: peak + 1500,
    renewable_shortfall_total_kwh: 10,
    pv_curtailment_kwh: 5,
    battery_throughput_kwh: 100,
    final_soc: 0.5,
    direct_pv_delivery_kwh: 200,
    realized_dppa_energy_kwh: 200,
    battery_delivery_kwh: 100,
    realized_grid_energy_kwh: 500
  };
}

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

describe("language switch", () => {
  it("switches the whole interface between English and Vietnamese", async () => {
    window.localStorage.clear();
    render(
      <LanguageProvider>
        <App />
      </LanguageProvider>
    );
    await screen.findByText("Live Demo");
    fireEvent.click(screen.getByText("VI"));
    expect(screen.getByText("Trình diễn trực tiếp")).toBeInTheDocument();
    expect(screen.queryByText("Live Demo")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("EN"));
    expect(screen.getByText("Live Demo")).toBeInTheDocument();
    window.localStorage.clear();
  });
});

describe("investment lab", () => {
  it("renders progressive investment storyline and does not start on input changes", async () => {
    const api = await import("./api/client");
    render(<InvestmentLabPage />);
    await screen.findByText("Investment Scenario Lab");
    expect(screen.getByText("1. Define the Target")).toBeInTheDocument();
    expect(screen.getByText("2. Configure the Energy System")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Rooftop PV capacity/i), { target: { value: "3500" } });
    expect(api.createInvestmentAnalysis).not.toHaveBeenCalled();
  });

  it("runs one investment job and renders evidence export", async () => {
    const api = await import("./api/client");
    render(<InvestmentLabPage />);
    await screen.findByText("Investment Scenario Lab");
    const before = vi.mocked(api.createInvestmentAnalysis).mock.calls.length;
    fireEvent.click(screen.getByText("Run Investment Analysis"));
    await screen.findByText(/Result storyline/);
    expect(screen.getByText(/Download evidence ZIP/)).toBeInTheDocument();
    expect(screen.getByText(/not an official certificate/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Terminal battery valuation/i), { target: { value: "2500" } });
    expect(vi.mocked(api.createInvestmentAnalysis).mock.calls.length).toBe(before + 1);
  });
});
