# EMS-testausautomaatio

## Tarkoitus

Tama dokumentti kuvaa projektin testirakenteen, kattavuuden painopisteet ja jatkokehitystarpeet.

## Testien kaynnistys

Projektissa on seuraavat testiajoon liittyvat tiedostot:

1. `pytest.ini`
2. `run_pytest.sh`
3. `tests/conftest.py`

`pytest.ini` maarittelee markerit:

1. `unit`
2. `scenario`
3. `smoke`

`run_pytest.sh` ajaa komennon:

```bash
pytest -q tests
```

`tests/conftest.py` asettaa projektijuurena `EMS_PROJECT_ROOT`-ymparistomuuttujan tai paattelee juuren `modules/`-hakemiston perusteella.

## Testikokonaisuuden rakenne

### Yksikkotestit

Hakemisto: `tests/unit/`

Aidosti toteutettuja kohteita:

1. `test_engine.py`
2. `test_load_projection.py`
3. `test_evaluator.py`
4. `test_writer_semantics.py`
5. `test_surplus_allocator.py`
6. `test_decision_trace.py`

Keskeisia aidosti toteutettuja kohteita ovat myos:

1. `test_battery_controller_edges.py`
2. `test_haeo_horizon.py`

### Skenaariotestit

Hakemistot:

1. `tests/e2e_entity/`
2. `tests/scenarios/`

Keskeinen infrastruktuuri:

1. `tests/e2e_entity/scenario_harness.py`

Tama harness simuloi nykyista tuotantoketjua suoraan tiedostotasolla:

1. `ems_policy_engine.py`
2. `ems_dispatch_state_applier.py`
3. `ems_actuator_writers.py`

### Smoke-testit

Hakemisto: `tests/smoke/`

Tiedosto `test_top_level_files.py` varmistaa esimerkiksi:

1. etta keskeiset tiedostot ovat olemassa
2. etta `max_solar_charge_w` on kytketty mukaan
3. etta `battery_write_enabled` esiintyy malleissa ja moottorissa

### Contract-testit

Hakemisto: `tests/contract/`

Tiedosto `test_entity_map_contract.py` varmistaa perustason entity-map-sopimusta.

## Mita on oikeasti testattu

### Guard-logiikka

`tests/unit/test_evaluator.py` kattaa ainakin:

1. `STRICT_LIMITS`-tilan ei-overridaamisen
2. stale/invalid data -> `DEGRADED`
3. SOC-only battery protect
4. min-cell-only battery protect
5. molempien ehtojen battery protect
6. palautumisen vaatiman kaksinkertaisen ehdon

### Engine

`tests/unit/test_engine.py` kattaa ainakin:

1. `MANUAL` akun hands-off-semantiiikan
2. `MANUAL_SAFE` ilman clampia
3. `MANUAL_SAFE` + `BATTERY_PROTECT` clampin
4. `max_solar_charge_w`-rajoituksen `NET_ZERO`-tilassa
5. `battery_write_enabled`-attribuutin olemassaolon
6. `CHEAP_GRID_CHARGE`- ja `MAX_EXPORT`-battery fallbackit ja selitteet
7. HAEO-avusteiset battery-targetit `CHEAP_GRID_CHARGE`- ja `MAX_EXPORT`-tiloissa

### Load projection

`tests/unit/test_load_projection.py` kattaa ainakin:

1. `MANUAL` EV force-current -polun
2. `MANUAL_SAFE` EV force-current -polun
3. `DEGRADED` EV skip -polun
4. `NET_ZERO` force-current floor -polun
5. `CHEAP_GRID_CHARGE` EV-polut
6. relay-komentojen perussemantiikan

### Writer-semantiiikka

`tests/unit/test_writer_semantics.py` kattaa ainakin:

1. relay release -> actuator off
2. battery writer `MANUAL` hands-off
3. `MANUAL_SAFE` battery clamp writerissa
4. EV strategy `0` -> restore minimum current -polun

### Surplus allocator

`tests/unit/test_surplus_allocator.py` kattaa ainakin:

1. aktivointijarjestyksen prioriteetin mukaan
2. vapautusjarjestyksen kanteisprioriteetin mukaan
3. `active_stack()`-jarjestyksen
4. `policy inactive -> clear all`
5. `freeze`-estologikan
6. aktiivisen mutta ei-enää-kelvollisen kohteen vapautuksen

### Decision trace

`tests/unit/test_decision_trace.py` tarkistaa, etta keskeiset kentat ja `battery_write_enabled` valittyvat trace-attribuutteihin.

### Quarter-skenaariot

Aidosti toteutettuja e2e/skenaariotesteja ovat ainakin:

1. `test_non_net_zero_modes_quarter.py`
2. `test_goal_transition_net_zero_to_max_export.py`
3. `test_net_zero_quarter_datadriven.py`
4. `test_net_zero_priority_order_quarter.py`
5. `test_net_zero_ev_release_min_restore_quarter.py`
6. `test_net_zero_quarter_with_internal_latches.py`
7. `test_battery_protect_min_cell_recovery_quarter.py`
8. `test_battery_protect_min_cell_recovery_quarter2.py`
9. `tests/scenarios/test_net_zero_priority_squence_e2e.py`
10. `tests/scenarios/test_regressions.py`

Nama muodostavat projektin todellisen regressiosuojan rungon.

## Testikattavuuden puutteet

### Battery controller

Nykyiset testit kattavat esimerkiksi:

1. deadbandin tarkkoja rajoja
2. ramppiklippausta
3. 100 W kvantisointia
4. minimi-floor-kayttaytymista

### HAEO-integraatio

`haeo_horizon.py`-tiedostolle on perustason testit forecast-parsinnasta, aikavyohykkeista ja fallback-kayttaytymisesta. Lisaakattavuudelle on silti tilaa esimerkiksi laajemmissa payload- ja aikavyohykeskenaarioissa.

### Contract-kattavuus

`entity_map`-sopimustesteilla on perustason kattavuus. Lisaakattavuudelle on silti tilaa esimerkiksi:

1. etta kaikki tarvittavat entityt ovat mapissa
2. ettei ID-konflikteja ole
3. etta tuntemattomat tilat kasitellaan sovitusti

### DEGRADED- ja anti-flap-kattavuus

Lisaaregressiosuoja voisi edelleen olla hyodyllinen esimerkiksi:

1. stale-data safe mode -ketjulle e2e-tasolla
2. hysteresis- ja anti-flap-kayttaytymiselle

## Suositeltu korjausjarjestys testien kehitykselle

1. Arvioi tarvitaanko erillinen `SAFE_OFF`- tai `PAUSED`-tila ja lisaa sille testit vain jos sellainen otetaan myohemmin kayttoon.
2. Lisaa writerille eksplisiittinen testi, joka erottaa:
   `NET_ZERO` release-to-min-current
   ja `MAX_EXPORT` hard-off -semantiikan.

## Avoimet kysymykset / jatkokehitys

1. Ovatko puuttuvat HAEO- ja Home Assistant -konfiguraatiot toisessa repossa, jolloin osa testikattavuudesta kuuluu sinne?
2. Pitaako quarter-harnessiin lisata aidot HAEO-skenaariot ja `DEGRADED`-e2e-skenaariot?
3. Tarvitaanko lisaa contract- tai e2e-kattavuutta ennen ensimmaista releasea?
