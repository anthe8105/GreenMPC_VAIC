# PV Derivation

Stage 2 derives rooftop-PV availability from NASA POWER `ALLSKY_SFC_SW_DWN` and configured PV assumptions.

## Formula

When the solar-resource unit is hourly irradiation in `kWh/m^2`:

```text
pv_available_kwh = installed_capacity_kw * hourly_irradiation_kwh_m2 * performance_ratio
pv_available_kw = pv_available_kwh / 1 hour
```

When the unit is average irradiance in `W/m^2`:

```text
pv_available_kw = installed_capacity_kw * irradiance_wm2 / 1000 * performance_ratio
pv_available_kwh = pv_available_kw * 1 hour
```

Outputs are clipped to the configured capacity cap and are zero when the source resource is at or below the nighttime threshold.

## Limitations

The result is physically derived availability, not measured inverter output. It does not model inverter clipping curves, module temperature, shading, degradation, or site-specific losses beyond the configured performance ratio.
