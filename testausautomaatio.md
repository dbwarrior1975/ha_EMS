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

Testien ajoa yritettiin suorittaa projektin juuressa komennolla `pytest -q`.

Tulos:

1. `pytest` ei ollut saatavilla PATH:ssa
2. `python`-komento osoitti Windows Store -aliasiin, ei kaytettavaan Python-asennukseen
3. `py`-launcheria ei ollut saatavilla
4. projektissa ei nayttanyt olevan omaa `.venv`- tai `venv`-hakemistoa

Johtopaatos: testejä ei voitu ajaa taman istunnon ymparistossa. Tama dokumentti perustuu testikoodin analyysiin, ei onnistuneeseen testiajoon.

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

Tarkeaa: tiedostossa on myos ristiriitaisia, vanhentuneita `MAX_EXPORT`-odotuksia, ks. erillinen kohta alla.

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

### 1. `MAX_EXPORT`-EV-semantiikka: yksikkotestit vastaan tuotantokoodi

Tiedosto: `tests/unit/test_load_projection.py`

Seuraavat testit ovat ristiriidassa nykyisen tuotantokoodin kanssa:

1. `test_max_export_default_ev_is_min_current`
2. `test_max_export_force_current_respected`

Ristiriidan syy:

1. tuotantokoodi `modules/ems_core/net_zero/load_projection.py` palauttaa `MAX_EXPORT`-tilassa aina `0`
2. testit odottavat min-currentia tai force-currentin kunnioittamista

Tama on selva nykytilan ristiriita ja tulee kasitella teknisena velkana tai regressiovaarana.

### 2. Goal transition -testin docstring on vanhentunut

Tiedosto: `tests/e2e_entity/test_goal_transition_net_zero_to_max_export.py`

Docstring sanoo, etta `MAX_EXPORT EV policy is ev_min_current_a, not EV off`, mutta testin assertit odottavat nykyista EV off -kayttaytymista:

1. `policy_ev_current_a == 0`
2. `actuator_ev_enabled == False`
3. `actuator_ev_current_a == 0`

Testin varsinainen odotus on siis linjassa nykyisen tavoitesemantiikan kanssa, mutta dokumentoiva teksti on vanhentunut.

### 3. Non-net-zero -testin ensimmaisen docstringin virhe

Tiedosto: `tests/e2e_entity/test_non_net_zero_modes_quarter.py`

Ensimmainen testi koskee `CHEAP_GRID_CHARGE`-tilaa, mutta docstring alkaa tekstilla `Quarter scenario for MAX_EXPORT without forecast`.

Kyse on dokumentaatiovirheesta testissa.

### 4. Writerin `strategy 0` -semantiikka vastaan `MAX_EXPORT`-off-tavoite

Tiedosto: `ems_actuator_writers.py`

Writer tulkitsee EV-strategian `0` yleisesti "release surplus command" -tapauksena ja palauttaa virran minimiin, jos laturi on paalla.

Samaan aikaan osa e2e-skenaarioista dokumentoi ja odottaa, etta `MAX_EXPORT` sammuttaa EV-latauksen kokonaan.

Tama on nykyinen toteutuksellinen ristiriita koodissa, ei pelkka testivirhe.

## Placeholder-testit teknisena velkana

Seuraavat tiedostot sisaltavat placeholder-testeja, jotka kaytannossa eivat varmista toiminnallisuutta:

1. `tests/unit/test_battery_controller_edges.py`
2. `tests/unit/test_haeo_horizon.py`
3. `tests/contract/test_entity_map_contract.py`
4. `tests/e2e_entity/test_hysteresis_anti_flap.py`
5. `tests/e2e_entity/test_optimizer_degraded_fallback.py`
6. `tests/e2e_entity/test_system_degraded_safe_mode.py`

Nama tulee kasitella teknisena velkana. Nykytilassa ne vain palauttavat `assert True`.

## Testikattavuuden puutteet

### Battery controller

Vaikka `modules/ems_core/net_zero/battery_controller.py` sisaltaa aidon laskentalogiikan, sen varsinainen edge-case-kattavuus puuttuu. Placeholder-tiedosto ei varmista esimerkiksi:

1. deadbandin tarkkoja rajoja
2. ramppiklippausta
3. 100 W kvantisointia
4. minimi-floor-kayttaytymista

### HAEO-integraatio

`haeo_horizon.py`-tiedostolle ei ole nykytilassa oikeita toteutettuja testejä forecast-parsinnasta, aikavyohykkeista tai stale-detektiosta.

### Contract-kattavuus

`entity_map`-sopimustestit ovat placeholder-tasolla, joten nykyinen testipaketti ei oikeasti varmista:

1. etta kaikki tarvittavat entityt ovat mapissa
2. ettei ID-konflikteja ole
3. etta tuntemattomat tilat kasitellaan sovitusti

### DEGRADED- ja anti-flap-kattavuus

Nimetyt tiedostot ovat olemassa, mutta niiden testit ovat placeholder-tasolla. Talla hetkella puuttuu oikea regressiosuoja esimerkiksi:

1. stale-data safe mode -ketjulle e2e-tasolla
2. hysteresis- ja anti-flap-kayttaytymiselle

## Vanha terminologia testeissa

Testeissa on edelleen vanhaa `shadow_*`-terminologiaa, erityisesti writer-testien fake-entiteeteissa:

1. `input_number.shadow_victron`
2. `input_number.shadow_ev_current`

Tama ei vastaa projektin nykyista paatermistöa, jossa kaytetaan `actuator_*`- ja `surplus_*`-käsitteita.

## Suositeltu korjausjarjestys testien kehitykselle

1. Korjaa `MAX_EXPORT`-EV-semantiikan ristiriita ensin joko koodissa tai vanhentuneissa yksikkotesteissa.
2. Korvaa placeholder-testit oikeilla testeilla tiedostoissa:
   `test_battery_controller_edges.py`, `test_haeo_horizon.py`, `test_entity_map_contract.py`, `test_hysteresis_anti_flap.py`, `test_optimizer_degraded_fallback.py`, `test_system_degraded_safe_mode.py`.
3. Lisaa erilliset testit `IDLE`-tilalle.
4. Lisaa writerille eksplisiittinen testi, joka erottaa:
   `NET_ZERO` release-to-min-current
   ja `MAX_EXPORT` hard-off -semantiikan.

## Vanhoja artefakteja repossa

Testauksen nakokulmasta havaittuja vanhoja artefakteja:

1. useita `__pycache__`-hakemistoja
2. useita `.pyc`-tiedostoja

Naita ei tulisi kayttaa testitulosten tai nykytilan totuuslahteena.

## Avoimet kysymykset / jatkokehitys

1. Onko tarkoitus, etta `MAX_EXPORT`-tilassa EV sammuu aina kovasti pois, vai saako writerin restore-min -polku edelleen elaa joissain tapauksissa?
2. Ovatko puuttuvat HAEO- ja Home Assistant -konfiguraatiot toisessa repossa, jolloin osa testikattavuudesta kuuluu sinne?
3. Pitaako quarter-harnessiin lisata aidot HAEO-skenaariot ja `DEGRADED`-e2e-skenaariot?
4. Pitaako vanhat `shadow_*`-testitermit siivota, jotta testi- ja tuotantoterminologia vastaavat toisiaan?
