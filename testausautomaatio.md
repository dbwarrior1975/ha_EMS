# EMS-testausautomaatio

## Tarkoitus

Tama dokumentti kuvaa projektin nykyisen testirakenteen, havaittavat kattavuudet, ristiriidat ja teknisen velan suoraan testikoodista.

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

## Testiajon tila tassa analyysissa

Tassa dokumenttipaivityksessa testejä ei ajettu. Kuvaus perustuu testikoodin ja tuotantokoodin lukemiseen.

Projektissa on kuitenkin suora testiajon entrypoint `run_pytest.sh`, joka ajaa komennon:

```bash
pytest -q tests
```

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

Placeholder-tyyppisia tiedostoja:

1. `test_battery_controller_edges.py`
2. `test_haeo_horizon.py`

### Skenaariotestit

Hakemistot:

1. `tests/e2e_entity/`
2. `tests/scenarios/`

Keskeinen infrastruktuuri:

1. `tests/e2e_entity/scenario_harness.py`

Tama harness simuloi nykyista tuotantoketjua suoraan tiedostotasolla:

1. `ems_net_zero_shadow.py`
2. `ems_surplus_latches.py`
3. `ems_actuator_writers.py`

### Smoke-testit

Hakemisto: `tests/smoke/`

Tiedosto `test_top_level_files.py` varmistaa esimerkiksi:

1. etta keskeiset tiedostot ovat olemassa
2. etta `max_solar_charge_w` on kytketty mukaan
3. etta `battery_write_enabled` esiintyy malleissa ja moottorissa

### Contract-testit

Hakemisto: `tests/contract/`

Tiedosto `test_entity_map_contract.py` on nykytilassa placeholder.

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

Tarkeaa: yksikkotestit on jo paivitetty nykyiseen `MAX_EXPORT -> EV off` -semantiikkaan. Vanhentuneita kuvauksia loytyy edelleen joistakin e2e-testien nimista ja docstringeista, ks. erillinen kohta alla.

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

## Havaitut ristiriidat testien ja koodin valilla

### 1. `MAX_EXPORT`-EV-semantiikka: yksikkotestit on jo paivitetty

Tiedosto: `tests/unit/test_load_projection.py`

Nykyiset yksikkotestit ovat linjassa tuotantokoodin kanssa:

1. `test_max_export_default_ev_is_off`
2. `test_max_export_force_current_ignored_and_ev_is_off`

Ne odottavat samaa kuin tuotantokoodi: `MAX_EXPORT` palauttaa EV-policyksi `0`.

### 2. Goal transition -testi on paivitetty nykyiseen hard-off-semantiiikkaan

Tiedosto: `tests/e2e_entity/test_goal_transition_net_zero_to_max_export.py`

Testi odottaa nykyista EV off -kayttaytymista:

1. `policy_ev_current_a == 0`
2. `actuator_ev_enabled == False`
3. `actuator_ev_current_a == 0`

Testin nimi, docstring ja assertit ovat nyt linjassa nykyisen tavoitesemantiikan kanssa.

### 3. Non-net-zero -testin docstringit on paivitetty

Tiedosto: `tests/e2e_entity/test_non_net_zero_modes_quarter.py`

`CHEAP_GRID_CHARGE`- ja `MAX_EXPORT`-skenaarioiden docstringit vastaavat nyt nykyista tuotantosemantiikkaa.

### 4. Writerin `strategy 0` -semantiikka vastaan `hard_off`-semantiikka

Tiedosto: `ems_actuator_writers.py`

Writer tulkitsee EV-strategian `0` kahdella eri tavalla:

1. ilman attribuuttia kyse on release-semantiiikasta ja virta palautetaan minimiin, jos laturi on paalla
2. attribuutilla `ev_policy_mode=hard_off` kyse on hard-off -semantiikasta ja laturi sammutetaan

Toteutuksellinen ristiriita ei siis ole enaa yleinen `MAX_EXPORT`-ongelma. Jaljella on ennen kaikkea testien nimien ja docstringien vanhentuneisuus.

## Aiemmat placeholder-testit

Seuraavat tiedostot olivat aiemmin placeholder-tasolla, mutta niihin on nyt toteutettu oikeat testit:

1. `tests/unit/test_battery_controller_edges.py`
2. `tests/unit/test_haeo_horizon.py`
3. `tests/contract/test_entity_map_contract.py`
4. `tests/e2e_entity/test_hysteresis_anti_flap.py`
5. `tests/e2e_entity/test_optimizer_degraded_fallback.py`
6. `tests/e2e_entity/test_system_degraded_safe_mode.py`

## Testikattavuuden puutteet

### Battery controller

Vaikka `modules/ems_core/net_zero/battery_controller.py` sisaltaa aidon laskentalogiikan, lisakattavuudelle on yha tarvetta. Nykyiset testit kattavat esimerkiksi:

1. deadbandin raja- ja sisapuolen
2. ramppiklippauksen
3. 100 W kvantisoinnin
4. minimi-floor-kayttaytymisen

Jatkossa lisaarvoa toisi esimerkiksi:

1. deadbandin tarkkoja rajoja
2. ramppiklippausta
3. 100 W kvantisointia
4. minimi-floor-kayttaytymista

### HAEO-integraatio

`haeo_horizon.py`-tiedostolle on nyt perustason testit forecast-parsinnasta, aikavyohykkeista ja fallback-kayttaytymisesta. Lisaakattavuudelle on silti tilaa esimerkiksi laajemmissa payload- ja aikavyohykeskenaarioissa.

### Contract-kattavuus

`entity_map`-sopimustesteilla on nyt perustason kattavuus. Lisaakattavuudelle on silti tilaa esimerkiksi:

1. etta kaikki tarvittavat entityt ovat mapissa
2. ettei ID-konflikteja ole
3. etta tuntemattomat tilat kasitellaan sovitusti

### DEGRADED- ja anti-flap-kattavuus

Nimetyt tiedostot eivat ole enaa placeholder-tasolla. Talla hetkella lisaaregressiosuoja voisi edelleen olla hyodyllinen esimerkiksi:

1. stale-data safe mode -ketjulle e2e-tasolla
2. hysteresis- ja anti-flap-kayttaytymiselle

## Vanha terminologia testeissa

Testeista on siivottu vanhaa `shadow_*`-terminologiaa, jotta ne vastaavat paremmin projektin nykyista `actuator_*`- ja `surplus_*`-paatermistoa.

## Suositeltu korjausjarjestys testien kehitykselle

1. Arvioi tarvitaanko erillinen `SAFE_OFF`- tai `PAUSED`-tila ja lisaa sille testit vain jos sellainen otetaan myohemmin kayttoon.
2. Lisaa writerille eksplisiittinen testi, joka erottaa:
   `NET_ZERO` release-to-min-current
   ja `MAX_EXPORT` hard-off -semantiikan.

## Vanhoja artefakteja repossa

Testauksen nakokulmasta havaittuja vanhoja artefakteja:

1. useita `__pycache__`-hakemistoja
2. useita `.pyc`-tiedostoja

Naita ei tulisi kayttaa testitulosten tai nykytilan totuuslahteena.

## Avoimet kysymykset / jatkokehitys

1. Ovatko puuttuvat HAEO- ja Home Assistant -konfiguraatiot toisessa repossa, jolloin osa testikattavuudesta kuuluu sinne?
2. Pitaako quarter-harnessiin lisata aidot HAEO-skenaariot ja `DEGRADED`-e2e-skenaariot?
3. Tarvitaanko lisaa contract- tai e2e-kattavuutta ennen ensimmaista releasea?
