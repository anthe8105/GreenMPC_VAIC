from __future__ import annotations

import pandas as pd

from greenmpc.forecasting.metrics import reconcile_quantiles


def test_crossing_quantiles_are_reconciled() -> None:
    df = pd.DataFrame({"raw_p10_kw": [5.0], "raw_p50_kw": [3.0], "raw_p90_kw": [4.0]})
    out = reconcile_quantiles(df, "load")
    assert out.loc[0, "p10_kw"] <= out.loc[0, "p50_kw"] <= out.loc[0, "p90_kw"]
    assert out.loc[0, "quantile_corrected"]


def test_solar_clipping_and_nighttime_zero() -> None:
    df = pd.DataFrame({"raw_p10_kw": [-1.0], "raw_p50_kw": [5000.0], "raw_p90_kw": [6000.0], "target_is_daylight": [False]})
    out = reconcile_quantiles(df, "solar", capacity_kw=1000.0)
    assert out.loc[0, "p50_kw"] == 0.0
    assert out.loc[0, "forced_nighttime_zero"]
