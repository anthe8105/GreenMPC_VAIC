import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../api/client";
import type { ApiResponse, CommandState, ControlPhase, ControllerId, ForecastPayload, OperationMode, PlanPayload, ScenarioId, SessionResponse } from "../types/api";

type SessionLike = ApiResponse | SessionResponse;

const REVIEW_MILLISECONDS = 650;

export function useCommandCenter() {
  const [sessionId, setSessionId] = useState("");
  const [runId, setRunId] = useState("");
  const [state, setState] = useState<CommandState | null>(null);
  const [forecast, setForecast] = useState<ForecastPayload | null>(null);
  const [plan, setPlan] = useState<PlanPayload | null>(null);
  const [controller, setController] = useState<ControllerId>("deterministic_mpc");
  const [scenario, setScenario] = useState<ScenarioId>("normal");
  const [mode, setMode] = useState<OperationMode>("auto");
  const [running, setRunningState] = useState(false);
  const [phase, setPhase] = useState<ControlPhase>("READY");
  const [playbackSeconds, setPlaybackSeconds] = useState(5);
  const [maxHours, setMaxHours] = useState(12);
  const [completedHours, setCompletedHours] = useState(0);
  const [fallbackCount, setFallbackCount] = useState(0);
  const [invalidActionCount, setInvalidActionCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [nextTickAt, setNextTickAt] = useState<number | null>(null);
  const [nowMs, setNowMs] = useState(Date.now());
  const [eventBanner, setEventBanner] = useState<string | null>(null);
  const [lastDecisionReason, setLastDecisionReason] = useState("Press Start Live Simulation to watch GreenMPC forecast, optimize, validate, and execute one simulated hour at a time.");
  const activeRequest = useRef(false);
  const timeoutRef = useRef<number | null>(null);
  const latestSnapshot = useRef<{ sessionId: string; runId: string; state: CommandState | null }>({ sessionId: "", runId: "", state: null });
  const runningRef = useRef(false);
  const completedHoursRef = useRef(0);

  const clearScheduledTimer = useCallback(() => {
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  const applyResponse = useCallback((response: SessionLike) => {
    setSessionId(response.session_id);
    setRunId(response.run_id);
    setState(response.state);
    latestSnapshot.current = { sessionId: response.session_id, runId: response.run_id, state: response.state };
    if ("forecast" in response && response.forecast) setForecast(response.forecast);
    if ("plan" in response && response.plan) {
      setPlan(response.plan);
      if (response.plan.fallback_active) setFallbackCount((value) => value + 1);
      setLastDecisionReason(explainDecision(response.plan, response.state));
    }
  }, []);

  const initialize = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await api.createSession(scenario, controller);
      applyResponse(response);
      completedHoursRef.current = 0;
      setCompletedHours(0);
      setFallbackCount(0);
      setInvalidActionCount(0);
      setRunningState(false);
      runningRef.current = false;
      setPhase("READY");
    } catch (exc) {
      setError(readError(exc));
      setPhase("ERROR");
    } finally {
      setLoading(false);
    }
  }, [scenario, controller, applyResponse]);

  useEffect(() => {
    if (!sessionId) void initialize();
  }, [sessionId, initialize]);

  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const resetTo = useCallback(async (nextScenario = scenario, nextController = controller, banner: string | null = null) => {
    clearScheduledTimer();
    setRunningState(false);
    runningRef.current = false;
    setLoading(true);
    setError("");
    setForecast(null);
    setPlan(null);
    setEventBanner(banner);
    try {
      const response = sessionId
        ? await api.resetSession(sessionId, nextScenario, nextController)
        : await api.createSession(nextScenario, nextController);
      setScenario(nextScenario);
      setController(nextController);
      applyResponse(response);
      completedHoursRef.current = 0;
      setCompletedHours(0);
      setFallbackCount(0);
      setInvalidActionCount(0);
      setNextTickAt(null);
      setPhase("READY");
      setLastDecisionReason(banner ?? "Digital twin reset. Press Start Live Simulation to begin a visible control cycle.");
    } catch (exc) {
      setError(readError(exc));
      setPhase("ERROR");
    } finally {
      setLoading(false);
    }
  }, [scenario, controller, sessionId, applyResponse]);

  const reset = useCallback(() => resetTo(scenario, controller, null), [resetTo, scenario, controller]);

  const runOneVisibleCycle = useCallback(async (executionMode: OperationMode, forceController = controller): Promise<boolean> => {
    const snapshot = latestSnapshot.current;
    if (!snapshot.sessionId || !snapshot.state || activeRequest.current) return false;
    activeRequest.current = true;
    setLoading(true);
    setError("");
    setNextTickAt(null);
    try {
      setPhase("FORECASTING");
      const forecastResponse = await api.forecast(snapshot.sessionId, snapshot.runId, snapshot.state.timestamp, requestId("forecast"));
      applyResponse(forecastResponse);

      setPhase("OPTIMIZING");
      const planResponse = await api.plan(snapshot.sessionId, snapshot.runId, forecastResponse.state.timestamp, requestId("plan"), forceController);
      applyResponse(planResponse);

      if (!planResponse.plan?.valid_for_execution) {
        setInvalidActionCount((value) => value + 1);
        setPhase("ERROR");
        setError("The recommended action did not pass simulator validation.");
        runningRef.current = false;
        setRunningState(false);
        return false;
      }

      setPhase("REVIEWING_DECISION");
      await delay(REVIEW_MILLISECONDS);

      if (executionMode === "shadow") {
        setPhase("WAITING");
        return true;
      }

      setPhase("EXECUTING");
      const executeResponse = await api.execute(snapshot.sessionId, snapshot.runId, planResponse.state.timestamp, requestId("execute"));
      applyResponse(executeResponse);
      completedHoursRef.current += 1;
      setCompletedHours(completedHoursRef.current);
      setPhase("UPDATED");
      return true;
    } catch (exc) {
      setError(readError(exc));
      setPhase("ERROR");
      runningRef.current = false;
      setRunningState(false);
      return false;
    } finally {
      activeRequest.current = false;
      setLoading(false);
    }
  }, [controller, applyResponse]);

  const scheduleNext = useCallback((executionMode: OperationMode = mode) => {
    clearScheduledTimer();
    if (!runningRef.current || executionMode === "manual") return;
    if (executionMode === "auto" && completedHoursRef.current >= maxHours) {
      runningRef.current = false;
      setRunningState(false);
      setPhase("PAUSED");
      return;
    }
    const due = Date.now() + playbackSeconds * 1000;
    setPhase("WAITING");
    setNextTickAt(due);
    timeoutRef.current = window.setTimeout(async () => {
      const ok = await runOneVisibleCycle(executionMode, controller);
      if (ok && runningRef.current) scheduleNext(executionMode);
    }, playbackSeconds * 1000);
  }, [mode, maxHours, playbackSeconds, runOneVisibleCycle, controller, clearScheduledTimer]);

  const startLiveSimulation = useCallback(async () => {
    if (runningRef.current || activeRequest.current) return;
    setMode("auto");
    setRunningState(true);
    runningRef.current = true;
    const ok = await runOneVisibleCycle("auto", controller);
    if (ok && runningRef.current) scheduleNext("auto");
  }, [controller, runOneVisibleCycle, scheduleNext]);

  const startSelectedMode = useCallback(async () => {
    if (mode === "shadow") {
      setRunningState(true);
      runningRef.current = true;
      const ok = await runOneVisibleCycle("shadow", controller);
      if (ok && runningRef.current) scheduleNext("shadow");
      return;
    }
    if (mode === "manual") {
      await runOneVisibleCycle("shadow", controller);
      return;
    }
    await startLiveSimulation();
  }, [mode, controller, runOneVisibleCycle, scheduleNext, startLiveSimulation]);

  const pause = useCallback(() => {
    clearScheduledTimer();
    runningRef.current = false;
    setRunningState(false);
    setNextTickAt(null);
    setPhase("PAUSED");
  }, []);

  const stepOneHour = useCallback(async () => {
    pause();
    await runOneVisibleCycle("auto", controller);
  }, [pause, runOneVisibleCycle, controller]);

  const forecastAndPlan = useCallback(async () => {
    pause();
    await runOneVisibleCycle("shadow", controller);
  }, [pause, runOneVisibleCycle, controller]);

  const approveExecute = useCallback(async () => {
    const snapshot = latestSnapshot.current;
    if (!snapshot.sessionId || !snapshot.state || activeRequest.current) return;
    activeRequest.current = true;
    setLoading(true);
    try {
      setPhase("EXECUTING");
      const response = await api.execute(snapshot.sessionId, snapshot.runId, snapshot.state.timestamp, requestId("manual-execute"));
      applyResponse(response);
      completedHoursRef.current += 1;
      setCompletedHours(completedHoursRef.current);
      setPlan(null);
      setPhase("UPDATED");
    } catch (exc) {
      setError(readError(exc));
      setPhase("ERROR");
    } finally {
      activeRequest.current = false;
      setLoading(false);
    }
  }, [applyResponse]);

  const runGuidedDemo = useCallback(async () => {
    clearScheduledTimer();
    setMode("auto");
    setMaxHours(3);
    setRunningState(true);
    runningRef.current = true;
    await resetTo("normal", "deterministic_mpc", null);
    runningRef.current = true;
    setRunningState(true);
    for (let hour = 0; hour < 3; hour += 1) {
      const ok = await runOneVisibleCycle("auto", "deterministic_mpc");
      if (!ok) break;
    }
    runningRef.current = false;
    setRunningState(false);
    setNextTickAt(null);
    setPhase("PAUSED");
  }, [resetTo, runOneVisibleCycle]);

  const activateStressScenario = useCallback(async (nextScenario: ScenarioId) => {
    const label = scenarioLabel(nextScenario);
    await resetTo(nextScenario, controller, `${label} activated as an unannounced synthetic stress scenario. The session restarted so the existing approved event model can apply safely.`);
  }, [resetTo, controller]);

  const updateController = useCallback((value: ControllerId) => {
    setController(value);
    setPlan(null);
  }, []);

  const updateScenario = useCallback((value: ScenarioId) => {
    setScenario(value);
    setPlan(null);
  }, []);

  return {
    sessionId,
    runId,
    state,
    forecast,
    plan,
    controller,
    setController: updateController,
    scenario,
    setScenario: updateScenario,
    mode,
    setMode,
    running,
    phase,
    playbackSeconds,
    setPlaybackSeconds,
    maxHours,
    setMaxHours,
    completedHours,
    fallbackCount,
    invalidActionCount,
    loading,
    error,
    nextTickAt,
    nowMs,
    eventBanner,
    lastDecisionReason,
    initialize,
    reset,
    resetTo,
    startLiveSimulation,
    startSelectedMode,
    pause,
    runGuidedDemo,
    activateStressScenario,
    forecastAndPlan,
    approveExecute,
    stepCycle: stepOneHour
  };
}

function requestId(prefix: string) {
  return `${prefix}-${crypto.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function readError(exc: unknown) {
  return exc instanceof Error ? exc.message : String(exc);
}

function explainDecision(plan: PlanPayload, state: CommandState) {
  const first = plan.park_plan?.[0];
  if (!first) return "The controller produced a validated next-hour action.";
  const load = Number(state.kpis.park_load_kw ?? 0);
  const solar = Number(state.kpis.pv_available_kw ?? 0);
  const soc = Number(state.kpis.battery_soc_fraction ?? 0);
  const grid = Number(first.grid_import_kw ?? 0);
  const dppa = Number(first.dppa_import_kw ?? 0);
  const discharge = Number(first.battery_discharge_kw ?? 0);
  const charge = Number(first.battery_charge_kw ?? 0);
  if (plan.fallback_active) return `Optimization could not provide an executable plan, so the validated safe fallback dispatch is shown for the current hour.`;
  if (solar < load * 0.2 && discharge > 1) return `Solar availability is low relative to demand. The optimizer uses DPPA and battery discharge to reduce grid import while respecting transformer and battery limits.`;
  if (charge > 1) return `Solar or DPPA supply exceeds immediate tenant use, so the optimizer charges the battery for later hours while keeping all tenant load served.`;
  if (grid > dppa) return `The optimizer serves the current load with available renewable supply first, then uses grid import for the remaining demand within the transformer limit.`;
  if (soc < 0.25) return `Battery state of charge is low, so the plan preserves battery inventory and uses external supply for this hour.`;
  return `The optimizer balances PV, DPPA, grid, and battery flows to serve ${load.toFixed(0)} kW of park demand without violating the transformer limit.`;
}

function scenarioLabel(value: ScenarioId) {
  return {
    normal: "Normal Operations",
    cloudy: "Solar Drop",
    production_shift: "Production Demand Surge",
    combined_stress: "Combined Stress Event"
  }[value];
}
