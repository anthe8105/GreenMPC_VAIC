import type { ControllerId, OperationMode, ScenarioId } from "../types/api";
import { useI18n } from "../i18n/LanguageContext";

export function PlaybackControls({
  mode,
  setMode,
  controller,
  setController,
  scenario,
  setScenario,
  playbackSeconds,
  setPlaybackSeconds,
  maxHours,
  setMaxHours,
  running,
  startSelectedMode,
  pause,
  onReset,
  onStep,
  onForecastPlan,
  loading
}: {
  mode: OperationMode;
  setMode: (value: OperationMode) => void;
  controller: ControllerId;
  setController: (value: ControllerId) => void;
  scenario: ScenarioId;
  setScenario: (value: ScenarioId) => void;
  playbackSeconds: number;
  setPlaybackSeconds: (value: number) => void;
  maxHours: number;
  setMaxHours: (value: number) => void;
  running: boolean;
  startSelectedMode: () => void;
  pause: () => void;
  onReset: () => void;
  onStep: () => void;
  onForecastPlan: () => void;
  loading: boolean;
}) {
  const { t } = useI18n();
  return (
    <div className="advanced-grid">
      <label>{t("pb.operatingMode")}<select value={mode} onChange={(e) => setMode(e.target.value as OperationMode)} title={mode}>
        <option value="manual">{t("mode.manual")}</option>
        <option value="auto">{t("mode.auto")}</option>
        <option value="shadow">{t("mode.shadow")}</option>
      </select></label>
      <label>{t("pb.controller")}<select value={controller} onChange={(e) => setController(e.target.value as ControllerId)} title={controller}>
        <option value="deterministic_mpc">{t("controller.deterministic_mpc")}</option>
        <option value="greenmpc_conservative">{t("controller.greenmpc_conservative")}</option>
        <option value="rule_based">{t("controller.rule_based")}</option>
      </select></label>
      <label>{t("pb.scenarioOnReset")}<select value={scenario} onChange={(e) => setScenario(e.target.value as ScenarioId)} title={scenario}>
        <option value="normal">{t("scenario.normal")}</option>
        <option value="cloudy">{t("scenario.cloudy")}</option>
        <option value="production_shift">{t("scenario.production_shift")}</option>
        <option value="combined_stress">{t("scenario.combined_stress")}</option>
      </select></label>
      <label>{t("pb.playbackSpeed")}<select value={playbackSeconds} onChange={(e) => setPlaybackSeconds(Number(e.target.value))}>
        <option value={2}>{t("pb.speed2")}</option>
        <option value={5}>{t("pb.speed5")}</option>
        <option value={10}>{t("pb.speed10")}</option>
      </select></label>
      <label>{t("pb.maxHours")}<input type="number" min="1" max="24" value={maxHours} onChange={(e) => setMaxHours(Number(e.target.value))} /></label>
      <div className="button-row expert-buttons">
        <button disabled={running || loading} onClick={startSelectedMode}>{t("pb.startSelected")}</button>
        <button disabled={!running} onClick={pause}>{t("action.pause")}</button>
        <button disabled={loading || running} onClick={onStep}>{t("action.stepOneHour")}</button>
        <button disabled={loading || running} onClick={onForecastPlan}>{t("pb.forecastRecommend")}</button>
        <button disabled={loading} onClick={onReset}>{t("action.reset")}</button>
      </div>
      {mode === "shadow" && <p className="caption">{t("pb.shadowNote")}</p>}
    </div>
  );
}
