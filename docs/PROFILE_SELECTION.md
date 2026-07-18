# Profile Selection

Stage 2 selects five anonymous UCI electricity clients using deterministic archetype scoring. The source client IDs are anonymous profile-shape sources, not real tenant identities.

## Process

1. Read the configured source year from the ZIP without extracting the large archive.
2. Aggregate quarter-hour values to hourly profiles.
3. Calculate quality, scale, temporal, continuity, and ramp metrics for every client.
4. Filter profiles below configured valid-data and nonzero thresholds.
5. Score eligible profiles against five archetypes:
   - continuous_high_baseload
   - daytime_concentrated
   - variable_shift_driven
   - two_shift_stable
   - spiky_overtime
6. Select in configured priority order with deterministic source-client tie-breaking.
7. Enforce pairwise diversity where possible using normalized hourly-shape correlation.
8. Store `configs/selected_profiles.yaml` to prevent silent reselection.

## Lock File

Future builds reuse `configs/selected_profiles.yaml` when present. Reselection requires explicit `--reselect-profiles --force`.

## Scenario Limitation

Mappings such as `Semiconductor_B -> continuous_high_baseload` are scenario design decisions. They are not claims that UCI source clients are semiconductor, electronics, textile, or warehouse facilities.
