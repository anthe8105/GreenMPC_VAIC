import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createInvestmentAnalysis, getInvestmentResult, getInvestmentStatus, listInvestmentAnalyses, loadInvestmentDefaults } from "../api/client";
import type { ControllerId, InvestmentCandidate, InvestmentDefaults, InvestmentFinancial, InvestmentJobStatus, InvestmentResult, ScenarioId } from "../types/api";

export function useInvestmentLab() {
  const [defaults, setDefaults] = useState<InvestmentDefaults | null>(null);
  const [candidate, setCandidate] = useState<InvestmentCandidate | null>(null);
  const [financial, setFinancial] = useState<InvestmentFinancial | null>(null);
  const [scenario, setScenario] = useState<ScenarioId>("normal");
  const [controller, setController] = useState<ControllerId>("deterministic_mpc");
  const [durationHours, setDurationHours] = useState(24);
  const [job, setJob] = useState<InvestmentJobStatus | null>(null);
  const [result, setResult] = useState<InvestmentResult | null>(null);
  const [savedAnalyses, setSavedAnalyses] = useState<InvestmentJobStatus[]>([]);
  const [error, setError] = useState("");
  const [resultStale, setResultStale] = useState(false);
  const pollingRef = useRef<number | null>(null);

  useEffect(() => {
    void loadInvestmentDefaults()
      .then((data) => {
        setDefaults(data);
        setCandidate(data.proposal);
        setFinancial(data.financial);
        setScenario((data.defaults.scenario_id as ScenarioId) ?? "normal");
        setController((data.defaults.controller_id as ControllerId) ?? "deterministic_mpc");
        setDurationHours(Number(data.defaults.duration_hours ?? 24));
      })
      .catch((exc) => setError(readError(exc)));
    void listInvestmentAnalyses().then((data) => setSavedAnalyses(data.analyses ?? [])).catch(() => undefined);
  }, []);

  useEffect(() => () => {
    if (pollingRef.current !== null) window.clearTimeout(pollingRef.current);
  }, []);

  const updateCandidate = useCallback((patch: Partial<InvestmentCandidate>) => {
    setCandidate((current) => current ? { ...current, ...patch } : current);
    const physicalKeys = Object.keys(patch).filter((key) => key !== "terminal_inventory_valuation_vnd_per_kwh");
    if (physicalKeys.length > 0) setResultStale(true);
  }, []);

  const updateFinancial = useCallback((patch: Partial<InvestmentFinancial>) => {
    setFinancial((current) => current ? { ...current, ...patch } : current);
  }, []);

  const resetToBaseline = useCallback(() => {
    if (!defaults) return;
    setCandidate(defaults.baseline);
    setFinancial(defaults.financial);
    setResult(null);
    setResultStale(false);
  }, [defaults]);

  const runAnalysis = useCallback(async () => {
    if (!candidate || !financial) return;
    setError("");
    setResult(null);
    setResultStale(false);
    const started = await createInvestmentAnalysis({
      scenario_id: scenario,
      controller_id: controller,
      duration_hours: durationHours,
      candidate,
      financial,
      request_id: crypto.randomUUID()
    });
    setJob(started);
    pollUntilDone(started.analysis_id);
  }, [candidate, financial, scenario, controller, durationHours]);

  const pollUntilDone = useCallback((analysisId: string) => {
    if (pollingRef.current !== null) window.clearTimeout(pollingRef.current);
    const tick = async () => {
      try {
        const status = await getInvestmentStatus(analysisId);
        setJob(status);
        if (status.status === "completed") {
          const completed = await getInvestmentResult(analysisId);
          setResult(completed);
          void listInvestmentAnalyses().then((data) => setSavedAnalyses(data.analyses ?? []));
          return;
        }
        if (status.status === "failed" || status.status === "cancelled") {
          setError(status.error ?? status.status);
          return;
        }
        pollingRef.current = window.setTimeout(tick, 1000);
      } catch (exc) {
        setError(readError(exc));
      }
    };
    void tick();
  }, []);

  const sensitivityResult = useMemo(() => {
    if (!result || !financial) return null;
    const baseline = result.baseline_configuration;
    const proposal = result.proposal_configuration;
    const incrementalCapex =
      proposal.pv_capacity_kw * financial.pv_capex_vnd_per_kwp +
      proposal.battery_energy_capacity_kwh * financial.bess_energy_capex_vnd_per_kwh +
      proposal.battery_power_kw * financial.bess_power_capex_vnd_per_kw -
      (baseline.pv_capacity_kw * financial.pv_capex_vnd_per_kwp +
        baseline.battery_energy_capacity_kwh * financial.bess_energy_capex_vnd_per_kwh +
        baseline.battery_power_kw * financial.bess_power_capex_vnd_per_kw);
    return { incrementalCapex };
  }, [result, financial]);

  return {
    defaults,
    candidate,
    updateCandidate,
    financial,
    updateFinancial,
    scenario,
    setScenario,
    controller,
    setController,
    durationHours,
    setDurationHours,
    job,
    result,
    error,
    resultStale,
    savedAnalyses,
    runAnalysis,
    resetToBaseline,
    sensitivityResult
  };
}

function readError(exc: unknown) {
  return exc instanceof Error ? exc.message : String(exc);
}
