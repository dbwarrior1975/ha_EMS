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

Nykyinen koko testisetti ajetaan samalla komennolla:

```bash
pytest -q tests
```

Viimeisin varmennettu tila nykyisessa siivousvaiheessa:

1. `python3 -m pytest -q tests`
2. `python3 -m pytest -q tests/e2e_entity`
3. `python3 -m pytest -q tests/smoke/test_pyscript_ast_compat.py`
4. `python3 -m pytest -q`

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
6. `test_policy_diagnostics.py`

Keskeisia aidosti toteutettuja kohteita ovat myos:

1. `test_battery_controller_edges.py`
2. `test_haeo_horizon.py`

### Skenaariotestit

Hakemistot:

1. `tests/e2e_entity/`
2. `tests/scenarios/test_regressions.py` (kevyt historiallinen regressiopinta)

Keskeinen infrastruktuuri:

1. `tests/e2e_entity/scenario_harness.py`

Kanoninen e2e-kerros on `tests/e2e_entity/`. Se harness simuloi nykyista
tuotantoketjua suoraan tiedostotasolla:

1. `ems_policy_engine.py`
2. `ems_dispatch_state_applier.py`
3. `ems_actuator_writers.py`

`tests/scenarios/` sisaltaa kevyempia regressio-/semantiikkatesteja, mutta ei
ole enaa projektin ensisijainen e2e-pinta.

NET_ZERO raw runtime fixtureiden ja `expect_derived`-kaytannon kuvaus:
`tests/e2e_entity/net_zero_fixture_conventions.md`.

Harness ei tue `__legacy__.*`-derived-input overrideja. Skenaariot seedaavat `grid_power_w`,
`quarter_energy_balance_kwh` ja tarvittaessa `pv_power_w` -runtime-inputit ja production
`derive_net_zero_inputs()` laskee RPNZ/RPC-arvot.

Nykyinen e2e-malli:

1. jokaisella `tests/e2e_entity/<scenario>/` -kansiolla on oma
   `EMS_config.yaml`, joka toimii vain ihmisluettavana fixture-maarittelyna
2. `QuarterScenarioHarness(... scenario_dir=Path(__file__).parent)` materialisoi
   joka ajolla strict schema-v3 `policy_config`, `measurements` ja
   `policy_state` -paketit
3. policy runtime kulkee aina oikeiden `parse_policy_config_cached()`- ja
   `parse_tick_frame_v3()`-parserien kautta; legacy `PolicyContext/CoreConfigView`
   -siltaa ei ole
4. testit ja seed-helperit kayttavat vain `h.ent`- ja
   `h.device_entity(device_id, field)` -pintaa
5. root-tason `EMS_config.yaml` ei saa vaikuttaa e2e-skenaarion device
   registryyn, entity-id -hakuun tai seedaukseen
6. harness kutsuu `ems_policy_engine_loop(trigger_reason='e2e')` ja jatkaa
   oikeaan dispatch-applier -> writer -ketjuun
7. jokainen aktiivinen E2E-step asserttoi
   `runtime_input_contract == direct_tick_frame_v3`
8. `trigger_reason='e2e'` pakottaa `policy_diagnostics`-julkaisun, vaikka
   tuotannon timer-ajossa diagnostiikka olisi throttlatty

Root YAML -kytkenta ja direct-v3-harness on regressiosuojattu testissa
`tests/contract/test_e2e_direct_runtime_contract.py`.

### Smoke-testit

Hakemisto: `tests/smoke/`

Tiedosto `test_top_level_files.py` varmistaa esimerkiksi:

1. etta keskeiset tiedostot ovat olemassa
2. etta `max_solar_charge_w` on kytketty mukaan
3. etta `battery_write_enabled` esiintyy malleissa ja moottorissa

Tiedosto `test_pyscript_ast_compat.py` varmistaa, etta top-level runtime
moduulit pysyvat Pyscript-yhteensopivina.

### Contract-testit

Hakemisto: `tests/contract/`

Keskeiset contract-kohteet:

1. `test_runtime_entity_registry_contract.py`
2. `test_grouped_config_contract.py`
3. `test_e2e_direct_runtime_contract.py`

Kaytannollinen painotus on static config -contractissa, packet-owned runtime-registryssa
ja direct_tick_frame_v3 E2E -pariteetissa.

Grouped-config contract testaa nyt myos sen, etta `runtime.*` on aktiivinen
user-config surface, mutta `policy_outputs` ja `diagnostics_outputs` ovat
kiinteita canonical output-pintoja eika niita saa antaa YAML:ssa.

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

### Writer-semantiiikka

`tests/unit/test_writer_semantics.py` kattaa ainakin:

1. relay release -> actuator off
2. battery writer `MANUAL` hands-off
3. `MANUAL_SAFE` battery clamp writerissa
4. EV strategy `0` -> restore minimum current -polun

### Surplus allocator

`tests/unit/test_engine.py` ja `tests/unit/test_surplus_device_targets.py` kattavat ainakin:

1. aktivointijarjestyksen prioriteetin mukaan
2. vapautusjarjestyksen kanteisprioriteetin mukaan
3. device-stack-jarjestyksen trace- ja payload-polkujen kautta
4. `policy inactive -> clear all`
5. `freeze`-estologikan
6. aktiivisen mutta ei-enää-kelvollisen kohteen vapautuksen

`tests/unit/test_surplus_allocator.py` kattaa lisaksi:

1. `rpnz_w = 4 W` -> release deadbandin sisalla
2. `rpnz_w = 10 W` -> release deadbandin rajalla
3. `rpnz_w = 11 W` -> ei releasea taman saannon perusteella
4. `rpnz_w = 0 W` ja `-1 W` -> release edelleen tapahtuu

### Policy diagnostics

`tests/unit/test_policy_diagnostics.py` tarkistaa, etta keskeiset kentat ja
`battery_write_enabled` valittyvat diagnostiikka-attribuutteihin.

`tests/unit/test_policy_engine_timer.py` lukitsee timer-gaten:

1. kiintea `@time_trigger('period(now, 2s)')`
2. ei raw runtime `@state_trigger` -entityja
3. interval-gaten counter- ja elapsed-semantiiikka
4. skip-polku ei lue runtime-contextia eika julkaise sensoreita
5. `policy_diagnostics` throttlautuu timer-ajossa, mutta manual/e2e-ajot
   julkaisevat sen aina

### Quarter-skenaariot

Nykyiset e2e-tarinat on splitattu kansioihin. Toteutettuja tarinoita ovat:

1. `tests/e2e_entity/battery_protect_min_cell_recovery/`
2. `tests/e2e_entity/goal_transition_net_zero_to_max_export/`
3. `tests/e2e_entity/haeo_01_cheap_grid_charge_fresh_forecast/`
4. `tests/e2e_entity/haeo_02_net_zero_homebattery_primary_ev_adjustable/` (EMS-sisainen HAEO `NET_ZERO` combo-valinta)
5. `tests/e2e_entity/hard_off_on_low_pv/`
6. `tests/e2e_entity/net_zero_ev_adjustable_load/`
7. `tests/e2e_entity/net_zero_force_on_battery_support/`
8. `tests/e2e_entity/net_zero_homebattery_adjustable_load/`
9. `tests/e2e_entity/net_zero_priority_order_quarter/`
10. `tests/e2e_entity/optimizer_degraded_fallback/`
11. `tests/e2e_entity/system_degraded_safe_mode/`
12. `tests/scenarios/test_regressions.py`

Jokaisessa splitatussa e2e-kansiossa on oma `EMS_config.yaml`. Vaihejako ja
tarinakuvaus loytyvat itse testitiedostoista, scenario-helperista seka
`docs/dev/e2e_tests_stories.md`:sta.

Nama muodostavat projektin todellisen regressiosuojan rungon.

### FORCE_ON- ja feedback-protection -regressiot

Pakollinen regressioketju kattaa nyt seuraavat tapaukset:

1. `net_zero_force_on_battery_support/test_05_ev_force_on_writer_chain.py` todistaa
   runtime FORCE_ON -> `surplus_candidates.force_on` -> positiivinen EV
   `DevicePolicy` -> writer `enable_and_set_current` -> EV actuator entity
2. sama E2E ajetaan low-PV + negatiivinen battery setpoint -olosuhteessa ja
   todistaa, ettei ei-HARD_OFF FORCE_ON huku yleiseen heuristiikkaan
3. `net_zero_ev_adjustable_load/test_04_primary_residual_feedback_protection.py`
   todistaa primary absorber + eri producing residual -topologian, generic
   diagnostics-kentan ja lifecycle-progression HARD_OFFiin
4. unit-testit todistavat, ettei feedback-suojaus aktivoidu ilman residual-tuotantoa,
   kun primary ja residual ovat sama laite, tai eksplisiittisen FORCE_ON-pyynnon aikana
5. `hard_off_on_low_pv/test_07_force_on_bypasses_hard_off.py` todistaa, etta
   FORCE_ON ohittaa jo latched HARD_OFFin writerille asti mutta lifecycle-state sailyy;
   FORCE_ONin poistuessa sama HARD_OFF saa heti uudelleen auktoriteetin
6. unit-testi todistaa, etta FORCE_ON ohittaa `surplus_allowed=false` optimizer-gaten
7. relay FORCE_ON -E2E:t sailyvat ennallaan
8. capability/ownership-semanttiikka testataan synteettisilla
   `PRIMARY_ABSORBER` / `RESIDUAL_PRODUCER` -konteksteilla ilman production-adapteria

Regressioissa ei saa palauttaa `battery_to_ev_loop_risk`-kenttaa. Diagnostiikan
policy-syy on `primary_residual_feedback_protection`.

## Testikattavuuden puutteet

### Battery controller

Nykyiset testit kattavat esimerkiksi:

1. deadbandin tarkkoja rajoja
2. ramppiklippausta
3. kvantisointia
4. konfiguroitavan minimi-floorin kayttaytymista (`nz_battery_floor_default_w`)

### HAEO-integraatio

`modules/ems_core/integrations/haeo_horizon.py`-tiedostolle on perustason testit forecast-parsinnasta, aikavyohykkeista ja fallback-kayttaytymisesta. EV selector current -muunnos ei kuulu enaa HAEO-integraatioon. Lisaakattavuudelle on silti tilaa esimerkiksi laajemmissa payload- ja aikavyohykeskenaarioissa.

`tests/unit/test_ev_power.py` kattaa EV-domainin wattipohjaisen teho-virta-kvantisoinnin, rajojen johtamisen ja askelkoon validoinnin.

### Contract-kattavuus

Static config-, packet registry- ja direct-v3 E2E -testeilla on nyt perustason kattavuus. Lisaakattavuudelle on silti tilaa esimerkiksi:

1. etta static configin kaikki pakolliset device-pinnat on validoitu
2. ettei runtime-entity-id -konflikteja ole
3. etta template -> packet -> parser -round-trip katetaan aidolla HA-template-renderoinnilla

### DEGRADED- ja anti-flap-kattavuus

Lisaaregressiosuoja voisi edelleen olla hyodyllinen esimerkiksi:

1. stale-data safe mode -ketjun lisabranchit e2e-tasolla
2. hysteresis- ja anti-flap-kayttaytymisen reunatapaukset

## Suositeltu korjausjarjestys testien kehitykselle

1. Arvioi tarvitaanko erillinen `SAFE_OFF`- tai `PAUSED`-tila ja lisaa sille testit vain jos sellainen otetaan myohemmin kayttoon.
2. Lisaa writerille tarvittaessa lisaedge-testeja, jotka erottavat:
   `NET_ZERO` release-to-min-current
   ja `MAX_EXPORT` hard-off -semantiikan.
3. Pida `tests/e2e_entity/` tiukasti scenario-YAML -pohjaisena:
   uudet testit rakentavat harnessin `scenario_dir`-parametrilla eivatka saa
   lukea root `EMS_config.yaml`:n entity registrya implisiittisesti.

## Avoimet kysymykset / jatkokehitys

1. Ovatko puuttuvat HAEO- ja Home Assistant -konfiguraatiot toisessa repossa, jolloin osa testikattavuudesta kuuluu sinne?
2. Pitaako quarter-harnessiin lisata aidot HAEO-skenaariot ja `DEGRADED`-e2e-skenaariot?
3. Tarvitaanko lisaa contract- tai e2e-kattavuutta ennen ensimmaista releasea?

## Surplus candidate pool -regressiokattavuus

Refaktoroinnin pakollinen regressiopinta kattaa seuraavat sopimukset:

1. grouped-config ja direct-v2 parseri hyvaksyvat vain strict boolean
   `surplus_allowed` -arvot ja hylkaavat poistetun `activation_threshold_w`-kentän
2. activation threshold johdetaan `capabilities.max_absorb_w`:sta ja
   `surplus_dispatch_mode` hyvaksyy vain `max_absorb` ja `fixed`
3. `EV_A`, `EV_B` ja `RELAY1` voivat olla samassa kandidaattipoolissa
4. EV-vs-EV ja EV-vs-relay ordering kayttavat device-owned prioritya
5. device-kohtaiset `max_absorb_w`-kynnykset ja force-on-tilat eivat vuoda laitteiden valilla
6. hard-off state ja release-ready-counter etenevat/nollautuvat EV-kohtaisesti
7. toinen EV voi aktivoitua ilman selected-single-rajaa ja molemmat EV:t saavat
   omat `DevicePolicy`-tulokset
8. neutral synthetic absorb-candidate todistaa builderin kind-agnostisuuden ilman
   uuden production-adapterin lisaamista
9. EV-primary stepped regulation, HOME_BATTERY primary/residual, relays ja writer
10. A1a multi-BATTERY v3 boundary: every static device must exist in `policy_config.devices`; only the explicit v3 battery-channel owner may receive the scalar battery target and other BATTERY devices fail closed
   sailyvat regressiotesteissa

Kanoninen multi-EV E2E on
`tests/e2e_entity/net_zero_two_ev_one_relay/`. Se todistaa poolin
`EV_GARAGE > EV_CHARGER > RELAY1`, itsenaiset kynnykset ja molempien EV:iden
per-device writer-mappauksen.

