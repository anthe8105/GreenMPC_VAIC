from __future__ import annotations

from greenmpc.forecasting.metrics import interval_metrics, pinball_loss, point_metrics, skill_score


def test_point_metrics_are_correct() -> None:
    metrics = point_metrics([1, 2, 3], [1, 2, 5])
    assert metrics["MAE"] == 2 / 3
    assert round(metrics["WAPE"], 6) == round(2 / 6, 6)


def test_pinball_interval_and_skill() -> None:
    assert pinball_loss([10], [8], 0.5) == 1.0
    assert interval_metrics([5], [4], [6], 0.8)["empirical_coverage"] == 1.0
    assert skill_score(2.0, 4.0) == 0.5
