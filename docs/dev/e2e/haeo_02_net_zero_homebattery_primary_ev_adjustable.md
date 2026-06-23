# Story: HAEO 02 NET_ZERO internal HAEO plan, home-battery primary

## What this folder contains

- tests/e2e_entity/haeo_02_net_zero_homebattery_primary_ev_adjustable/test_01_internal_plan_homebattery_primary_ev_adjustable.py
- tests/e2e_entity/haeo_02_net_zero_homebattery_primary_ev_adjustable/scenario_steps.py

## Scenario intent

This story validates the first implemented EMS-internal HAEO + `NET_ZERO` path.

The first quarter uses the following HAEO forecast:

1. battery `3.0 kW`
2. EV `1.5 kW`

Because the battery forecast is larger, the planned EMS semantics should select:

1. `adjustable_primary_load = HOME_BATTERY`
2. `adjustable_surplus_load = EV_CHARGER`

The config helpers are deliberately seeded with the opposite combo. The expected future behavior is that the EMS-internal HAEO plan overrides the helper combo for this quarter without writing those helper values back to Home Assistant.

The test proves that current EMS code creates `haeo_nz_plan_*` trace attributes, selects the combo internally, and allows `NET_ZERO` surplus-policy while the HAEO NET_ZERO plan is active.

The scenario also includes a second quarter at `t=900s`:

1. battery `1.0 kW`
2. EV `5.0 kW`

This should flip the internal plan to:

1. `primary = EV_CHARGER`
2. `adjustable_surplus = HOME_BATTERY`

Because `surplus_adjustable_active` was true for the old EV-adjustable combo, the expected next behavior is explicit combo-change hygiene: `CLEAR_ALL`, a short freeze, and `surplus_state_clear_reason = HAEO_COMBO_CHANGED`. This part is intentionally ahead of the current implementation if the hygiene layer has not yet been added.

## Coverage

1. `HORIZON_BY_HAEO` configures HAEO even when `forecast_profile = NONE`.
2. Fresh HAEO sources make `effective_forecast = HAEO`.
3. EMS-internal HAEO plan selects the larger-forecast target as primary.
4. HOME_BATTERY becomes primary and EV_CHARGER becomes adjustable surplus.
5. Battery positive target is capped by the HAEO battery limit.
6. EV adjustable current is capped by the HAEO EV limit.
7. The first cycle activates adjustable state; the next policy cycle writes EV current after `surplus_adjustable_active` is true.
8. Quarter change can flip the combo from HOME_BATTERY-primary to EV-primary.
9. Combo change must clear old surplus state before the new physical meaning of `ADJUSTABLE` is used.
