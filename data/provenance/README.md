# Raw Data Provenance

Stage 1 caches public raw inputs and stores reviewable provenance metadata.

- UCI electricity profiles are measured anonymous client-consumption profiles with Portuguese local timestamps. They are not industry-labeled, not Vietnamese, and not VRG records.
- UCI steel data is a measured South Korean steel-industry source. It is not a proxy for all future scenario tenant industries.
- NASA POWER data is satellite/model-based meteorological and solar-resource data for configurable demonstration coordinates. Raw data is retained in UTC.
- Vietnam tariff records are curated regulatory/reference metadata. Customer category and voltage level are not selected in Stage 1.

Raw archives and CSV files are excluded from Git because they are externally sourced and may be large. Reacquire them with `python scripts/acquire_public_data.py --all`; validate cached files without network calls using `python scripts/acquire_public_data.py --all --offline`.

Citation text and retrieval fingerprints are recorded in `sources.yaml` and `acquisitions.json`. The SHA-256 values are local retrieval fingerprints unless a publisher-provided checksum is separately documented.

No Stage 1 source is actual VRG operational data, actual VRG tenant data, a confidential DPPA contract, an actual VRG battery specification, or actual VRG transformer topology.
