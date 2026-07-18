import { useEffect, useState } from "react";
import { LiveTwinPage } from "./pages/LiveTwinPage";
import { ScenarioBenchmarkPage } from "./pages/ScenarioBenchmarkPage";
import { InvestmentLabPage } from "./pages/InvestmentLabPage";
import { useCommandCenter } from "./hooks/useCommandCenter";
import { loadBenchmark, loadProvenance } from "./api/client";
import { useI18n } from "./i18n/LanguageContext";
import { LanguageSwitch } from "./components/LanguageSwitch";

type Page = "live" | "investment" | "results";

export function App() {
  const command = useCommandCenter();
  const { t } = useI18n();
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
        <section className="loading-panel">{t("app.loading")}</section>
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
            <span>{t("brand.tagline")}</span>
          </div>
        </div>
        <nav className="top-nav" aria-label="Primary navigation">
          <button className={page === "live" ? "active" : ""} onClick={() => setPage("live")}>{t("nav.live")}</button>
          <button className={page === "investment" ? "active" : ""} onClick={() => setPage("investment")}>{t("nav.investment")}</button>
          <button className={page === "results" ? "active" : ""} onClick={() => setPage("results")}>{t("nav.results")}</button>
        </nav>
        <div className="header-status">
          <span>{command.state.timestamp}</span>
          <span>{t(`scenario.${command.scenario}`)}</span>
          <span>{t(`controller.${command.controller}`)}</span>
          <span>{command.running ? t("status.running") : t("status.paused")}</span>
        </div>
        <div className="header-actions">
          <LanguageSwitch />
          <button className="start-demo-small" onClick={command.startLiveSimulation} disabled={command.loading || command.running}>{t("action.startLiveDemo")}</button>
          <button onClick={command.pause} disabled={!command.running}>{t("action.pause")}</button>
          <button onClick={command.reset} disabled={command.loading}>{t("action.reset")}</button>
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

      {page === "investment" && <InvestmentLabPage />}

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
