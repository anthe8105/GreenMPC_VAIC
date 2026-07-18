import { useEffect, useState } from "react";
import { LiveTwinPage } from "./pages/LiveTwinPage";
import { ScenarioBenchmarkPage } from "./pages/ScenarioBenchmarkPage";
import { useCommandCenter } from "./hooks/useCommandCenter";
import { loadBenchmark, loadProvenance } from "./api/client";
import { controllerLabel, scenarioLabel } from "./types/labels";

type Page = "live" | "results";

export function App() {
  const command = useCommandCenter();
  const [page, setPage] = useState<Page>("live");
  const [valuationPrice, setValuationPrice] = useState(1500);
  const [benchmark, setBenchmark] = useState<Record<string, unknown> | null>(null);
  const [provenance, setProvenance] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    void loadBenchmark(valuationPrice).then(setBenchmark).catch(() => setBenchmark(null));
  }, [valuationPrice]);

  useEffect(() => {
    void loadProvenance().then(setProvenance).catch(() => setProvenance(null));
  }, []);

  if (!command.state) {
    return (
      <div className="app-shell">
        <section className="loading-panel">Loading the offline GreenMPC digital twin...</section>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <header className="product-header">
        <div className="brand-lockup">
          <div className="logo-mark">GM</div>
          <div>
            <strong>GreenMPC Twin</strong>
            <span>AI energy orchestration for industrial parks</span>
          </div>
        </div>
        <nav className="top-nav" aria-label="Primary navigation">
          <button className={page === "live" ? "active" : ""} onClick={() => setPage("live")}>Live Demo</button>
          <button className={page === "results" ? "active" : ""} onClick={() => setPage("results")}>Results and Evidence</button>
        </nav>
        <div className="header-status">
          <span>{command.state.timestamp}</span>
          <span>{scenarioLabel(command.scenario)}</span>
          <span>{controllerLabel(command.controller)}</span>
          <span>{command.running ? "Running" : "Paused"}</span>
        </div>
        <div className="header-actions">
          <button className="start-demo-small" onClick={command.startLiveSimulation} disabled={command.loading || command.running}>Start Live Demo</button>
          <button onClick={command.pause} disabled={!command.running}>Pause</button>
          <button onClick={command.reset} disabled={command.loading}>Reset</button>
        </div>
      </header>

      {page === "live" && (
        <LiveTwinPage
          state={command.state}
          forecast={command.forecast}
          plan={command.plan}
          controls={{
            mode: command.mode,
            setMode: command.setMode,
            controller: command.controller,
            setController: command.setController,
            scenario: command.scenario,
            setScenario: command.setScenario,
            playbackSeconds: command.playbackSeconds,
            setPlaybackSeconds: command.setPlaybackSeconds,
            maxHours: command.maxHours,
            setMaxHours: command.setMaxHours,
            running: command.running,
            startLiveSimulation: command.startLiveSimulation,
            startSelectedMode: command.startSelectedMode,
            pause: command.pause,
            runGuidedDemo: command.runGuidedDemo,
            activateStressScenario: command.activateStressScenario,
            onReset: command.reset,
            onStep: command.stepCycle
          }}
          running={command.running}
          phase={command.phase}
          nextTickAt={command.nextTickAt}
          nowMs={command.nowMs}
          completedHours={command.completedHours}
          maxHours={command.maxHours}
          fallbackCount={command.fallbackCount}
          invalidActionCount={command.invalidActionCount}
          eventBanner={command.eventBanner}
          decisionReason={command.lastDecisionReason}
          onForecastPlan={command.forecastAndPlan}
          onExecute={command.approveExecute}
          loading={command.loading}
          error={command.error}
        />
      )}

      {page === "results" && (
        <ScenarioBenchmarkPage
          benchmark={benchmark}
          provenance={provenance}
          valuationPrice={valuationPrice}
          setValuationPrice={setValuationPrice}
        />
      )}
    </div>
  );
}
