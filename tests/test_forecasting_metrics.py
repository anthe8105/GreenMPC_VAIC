from __future__ import annotations

import pandas as pd

from greenmpc.forecasting.metrics import interval_metrics, pinball_loss, point_metrics, skill_score


def test_point_metrics_are_correct() -> None:
    metrics = point_metrics([1, 2, 3], [1, 2, 5])
    assert metrics["MAE"] == 2 / 3
    assert round(metrics["WAPE"], 6) == round(2 / 6, 6)


def test_pinball_interval_and_skill() -> None:
    assert pinball_loss([10], [8], 0.5) == 1.0
    assert interval_metrics([5], [4], [6], 0.8)["empirical_coverage"] == 1.0
    assert skill_score(2.0, 4.0) == 0.5


def test_interval_coverage_grouping_by_horizon() -> None:
    rows = pd.DataFrame({
        "horizon_hours": [1, 1, 2, 2],
        "actual": [10.0, 20.0, 10.0, 20.0],
        "p10": [9.0, 19.0, 30.0, 40.0],
        "p90": [11.0, 21.0, 31.0, 41.0],
    })
    grouped = {
        horizon: interval_metrics(group["actual"], group["p10"], group["p90"], 0.8)["empirical_coverage"]
        for horizon, group in rows.groupby("horizon_hours")
    }
    assert grouped == {1: 1.0, 2: 0.0}
