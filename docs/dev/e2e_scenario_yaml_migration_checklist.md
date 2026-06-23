# E2E scenario YAML migration checklist

Paivays: 2026-06-23

## Vaihe 0 kartoitus

Skenaariot, joilla on oma `EMS_config.yaml`:

- `battery_protect_min_cell_recovery`
- `custom_device_ids_selected_single_ev`
- `goal_transition_net_zero_to_max_export`
- `haeo_01_cheap_grid_charge_fresh_forecast`
- `haeo_02_net_zero_homebattery_primary_ev_adjustable`
- `hard_off_on_low_pv`
- `net_zero_ev_adjustable_load`
- `net_zero_force_on_battery_support`
- `net_zero_homebattery_adjustable_load`
- `net_zero_no_ev_relays_only`
- `net_zero_no_relays_ev_only`
- `net_zero_priority_order_quarter`
- `net_zero_priority_order_quarter_3_relays`
- `net_zero_two_ev_one_relay`
- `optimizer_degraded_fallback`
- `system_degraded_safe_mode`

Skenaariot, joilla ei viela ole omaa `EMS_config.yaml`:

- ei poikkeuksia

Root `ENT` -riippuvuudet `tests/e2e_entity/`-puolella:

- testit ja scenario-stepit importtaavat edelleen `tests.entity_ids.ENT` laajasti
- harness kaytti globaalia `ENT`:a seedauksessa ja moduloiden injektoinnissa
- `tests/e2e_entity/refactored_runner.py` kaytti globaalia `ENT`:a device-lookupissa ja aktiivisten laitteiden seedauksessa
- `tests/e2e_entity/net_zero_priority_order_quarter_3_relays/scenario_steps.py` sisaltaa paikallisen `RELAY3`-workaroundin

Muutoskohteet vaiheille 1-3:

- `tests/e2e_entity/scenario_harness.py`
- `tests/e2e_entity/refactored_runner.py`
- regressiotestit kolmen releen scenario-YAML:lle

## Vaihe 5 regressiosuoja

Toteutettu root YAML isolation -regressiotesti:

- `tests/contract/test_grouped_config_runtime_parity.py::test_scenario_harness_registry_is_isolated_from_root_ent`
- testi todistaa, etta root `tests.entity_ids.ENT` ei sisalla `RELAY3`:a mutta
  `QuarterScenarioHarness(... scenario_dir=...)` loytaa `RELAY3`:n skenaarion
  omasta `EMS_config.yaml`:sta

## Vaihe 6 globaali ENT pois e2e-polusta

Toteutettu:

- e2e-testit ja `scenario_steps.py`-tiedostot eivat enaa importtaa `tests.entity_ids.ENT`:a
- e2e-assertit ja seedaus kayttavat `h.ent`-registrya
- `tests/e2e_entity/refactored_runner.py` ei fallbackaa root `ENT`:iin

Jaljelle jaa sallitusti vain:

- dokumentaatio-osumat
- `QuarterScenarioHarness.device_entity(...)` yhteensopivuuspinta itse harnessissa

## Vaihe 7 scenario YAML pakolliseksi

Toteutettu:

- jokaisessa `tests/e2e_entity/<scenario>/`-kansiossa on nyt oma `EMS_config.yaml`
- `QuarterScenarioHarness(... scenario_dir=...)` failaa, jos kansiosta puuttuu
  nimenomaan `EMS_config.yaml`
- infra-testi varmistaa, ettei poikkeuslistaa ole

## Vaihe 8 dokumentaatio ja workaroundien poisto

Toteutettu:

- `docs/dev/testausautomaatio.md` kuvaa nyt scenario-YAML -mallin valmiina
  infrastruktuurina eika tulevana migraatiotavoitteena
- `tests/e2e_entity/e2e_refactoring.md` dokumentoi `h.ent`- ja
  `h.device_entity(...)` -pinnan e2e-polun ainoana entity-hakuna
- `docs/user/config_examples.md` kertoo, etta e2e-skenaarion config kuuluu
  skenaariokansion omaan `EMS_config.yaml`:iin
- skenaariokohtaiset paikalliset entity-id workaroundit, kuten `RELAY3_ENT`,
  eivat enaa kuulu e2e-polkuun
- root `ENT` -fallbackit on poistettu e2e-helperien ja scenario-stepien
  kaytosta; root-config on sallittu vain eksplisiittisissa contract- ja
  compatibility-testeissa
