# Time Alignment

The UCI electricity load source uses Portuguese local wall-clock timestamps. NASA POWER data is requested and cached in UTC for demonstration coordinates in southern Vietnam.

## Load Handling

Stage 2 parses UCI timestamps as source-local wall-clock timestamps, audits duplicate and missing local timestamps, aggregates quarter-hour values into hourly profiles, and transfers the local date and hour into the Vietnam scenario calendar.

This is a calendar-preserving profile transfer. It is not a conversion of simultaneous Portuguese measurements into Vietnam time.

## Weather Handling

NASA timestamps are converted from UTC to `Asia/Ho_Chi_Minh`. Incomplete local boundary days created by timezone conversion are removed when configured.

## Alignment

The final processed index uses complete Vietnam-local days available in both the transferred load profiles and NASA weather data. The two sources are not co-located observations.
