# PV Derivation

Stage 2 derives rooftop-PV availability from NASA POWER `ALLSKY_SFC_SW_DWN` and configured PV assumptions. The preserved NASA header reports the raw unit as `Wh/m^2`.

## Formula

When the solar-resource unit is hourly irradiation in `kWh/m^2`:

```text
pv_available_kwh = installed_capacity_kw * hourly_irradiation_kwh_m2 * performance_ratio
pv_available_kw = pv_available_kwh / 1 hour
```

When the solar-resource unit is hourly irradiation in `Wh/m^2`:

```text
solar_resource_normalized = (raw_wh_m2 / 1000) / reference_hourly_irradiation_kwh_m2
pv_available_kw = installed_capacity_kw * solar_resource_normalized * performance_ratio
pv_available_kwh = pv_available_kw * 1 hour
```

When the unit is average irradiance in `W/m^2`:

```text
pv_available_kw = installed_capacity_kw * irradiance_wm2 / 1000 * performance_ratio
pv_available_kwh = pv_available_kw * 1 hour
```

Outputs are clipped to the configured capacity cap and are zero when the source resource is at or below the nighttime threshold.

## Quality Gates

Processed outputs preserve `solar_resource_raw`, `solar_resource_unit`, `solar_resource_normalized`, `pv_conversion_branch`, `pv_formula_version`, and `pv_clipped_to_capacity`. Validation fails if positive-PV clipping exceeds the configured failure threshold or if raw solar variation is collapsed into too few derived PV values.

## Correction History

The initial Stage 2 implementation parsed the NASA header incorrectly and defaulted `ALLSKY_SFC_SW_DWN` to `kWh/m^2`. It therefore treated `Wh/m^2` values in the hundreds as kWh/m^2 and saturated almost all positive PV hours at the capacity cap. Formula version `simple_capacity_factor_v2` corrects this by explicitly converting `Wh/m^2` to kWh/m^2 before capacity-factor scaling.

## Limitations

The result is physically derived availability, not measured inverter output. It does not model inverter clipping curves, module temperature, shading, degradation, or site-specific losses beyond the configured performance ratio.
