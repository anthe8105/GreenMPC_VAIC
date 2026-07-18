# MPC Inputs

GreenMPC input construction is leakage-audited.

Permitted current input:
- current effective tenant load and PV from the digital twin.

Permitted future inputs:
- tenant-load forecast quantiles;
- rooftop-PV forecast quantiles;
- known tariff schedule;
- contractual DPPA availability and price;
- transformer rating.

Forbidden future inputs:
- actual future tenant load;
- actual future PV;
- actual future solar resource or weather;
- unannounced future runtime event effects.

Expected mode uses P50 tenant load and P50 PV. Conservative mode uses P90 tenant load and P10 PV. This is quantile-conservative deterministic MPC, not a formal stochastic or chance-constrained optimizer.
