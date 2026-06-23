# Story: HAEO 01 CHEAP_GRID_CHARGE fresh forecast active

## What this folder contains

- tests/e2e_entity/haeo_01_cheap_grid_charge_fresh_forecast/test_01_cheap_grid_charge_fresh_forecast_active.py
- tests/e2e_entity/haeo_01_cheap_grid_charge_fresh_forecast/scenario_steps.py

## Scenario intent

This is the first HAEO E2E story. It validates the positive path where HAEO data is fresh, forecast payloads are valid, and EMS uses HAEO targets without falling back to local policy.

## Coverage

1. `HORIZON_BY_HAEO` configures HAEO even when `forecast_profile = NONE`.
2. Fresh battery and EV freshness sources make `effective_forecast = HAEO`.
3. `CHEAP_GRID_CHARGE` battery target comes from the HAEO battery forecast.
4. `CHEAP_GRID_CHARGE` EV current comes from the HAEO EV forecast.
5. Surplus dispatch remains inactive and clears surplus state in non-`NET_ZERO` mode.
