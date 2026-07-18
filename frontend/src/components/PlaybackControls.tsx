import type { ControllerId, OperationMode, ScenarioId } from "../types/api";
import { controllerLabel, modeLabel, scenarioLabel } from "../types/labels";

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
  return (
    <div className="advanced-grid">
      <label>Operating mode<select value={mode} onChange={(e) => setMode(e.target.value as OperationMode)} title={mode}>
        <option value="manual">{modeLabel("manual")}</option>
        <option value="auto">{modeLabel("auto")}</option>
        <option value="shadow">{modeLabel("shadow")}</option>
      </select></label>
      <label>Controller<select value={controller} onChange={(e) => setController(e.target.value as ControllerId)} title={controller}>
        <option value="deterministic_mpc">{controllerLabel("deterministic_mpc")}</option>
        <option value="greenmpc_conservative">{controllerLabel("greenmpc_conservative")}</option>
        <option value="rule_based">{controllerLabel("rule_based")}</option>
      </select></label>
      <label>Scenario on reset<select value={scenario} onChange={(e) => setScenario(e.target.value as ScenarioId)} title={scenario}>
        <option value="normal">{scenarioLabel("normal")}</option>
        <option value="cloudy">{scenarioLabel("cloudy")}</option>
        <option value="production_shift">{scenarioLabel("production_shift")}</option>
        <option value="combined_stress">{scenarioLabel("combined_stress")}</option>
      </select></label>
      <label>Playback speed<select value={playbackSeconds} onChange={(e) => setPlaybackSeconds(Number(e.target.value))}>
        <option value={2}>1 simulated hour every 2 seconds</option>
        <option value={5}>1 simulated hour every 5 seconds</option>
        <option value={10}>1 simulated hour every 10 seconds</option>
      </select></label>
      <label>Maximum simulated hours<input type="number" min="1" max="24" value={maxHours} onChange={(e) => setMaxHours(Number(e.target.value))} /></label>
      <div className="button-row expert-buttons">
        <button disabled={running || loading} onClick={startSelectedMode}>Start Selected Mode</button>
        <button disabled={!running} onClick={pause}>Pause</button>
        <button disabled={loading || running} onClick={onStep}>Step One Hour</button>
        <button disabled={loading || running} onClick={onForecastPlan}>Forecast and Recommend</button>
        <button disabled={loading} onClick={onReset}>Reset</button>
      </div>
      {mode === "shadow" && <p className="caption">Recommendation only - no command executed.</p>}
    </div>
  );
}
