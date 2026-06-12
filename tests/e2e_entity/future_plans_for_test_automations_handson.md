# Future Plans For Test Automations Hands-On

## 1. Tavoite
Taman dokumentin tarkoitus on antaa seuraavaan sessioon suoraan kaytettava suunnitelma, jolla E2E-testausta laajennetaan business-logiikan katvealueisiin ja nostetaan kattavyytta hallitusti.

Lopputavoite:
- Lisata E2E-skenaarioita niin, etta business-logiikan todellinen branch-kattavuus paranee.
- Pitaa nykyinen vaiheistettu rakenne selkeana ja toistettavana.
- Varmistaa, etta uudet testit ovat itsenaisia ja helposti debugattavia.

## 2. Nykyinen baseline (viimeisin ajo)
Ajo: pytest -q tests/e2e_entity --cov=. --cov-report=term-missing

Kokonaiskattavuus:
- TOTAL 88% (1598 statements, 190 missing)

Business-logiikan avainmoduulit:
- [modules/ems_core/integrations/haeo_horizon.py](modules/ems_core/integrations/haeo_horizon.py): 19%
- [ems_dispatch_state_applier.py](ems_dispatch_state_applier.py): 61%
- [ems_actuator_writers.py](ems_actuator_writers.py): 73%
- [modules/ems_core/net_zero/load_projection.py](modules/ems_core/net_zero/load_projection.py): 70%
- [ems_policy_engine.py](ems_policy_engine.py): 82%
- [modules/ems_core/net_zero/engine.py](modules/ems_core/net_zero/engine.py): 83%
- [modules/ems_core/guard/evaluator.py](modules/ems_core/guard/evaluator.py): 91%
- [modules/ems_core/net_zero/surplus_allocator.py](modules/ems_core/net_zero/surplus_allocator.py): 97%
- [modules/ems_core/net_zero/battery_controller.py](modules/ems_core/net_zero/battery_controller.py): 100%

## 3. Korkean prioriteetin kattavuusgapit
### P1: HAEO integraatiopolku
Kohde: [modules/ems_core/integrations/haeo_horizon.py](modules/ems_core/integrations/haeo_horizon.py)

Miksi:
- Selvasti alin kattavuus.
- Kattaa fallback- ja datan saatavuuspolut, jotka vaikuttavat optimointipaatoksiin.

Tarvittavat uudet skenaariot:
1. Tuore HAEO data, validi forecast, normaali eteneminen ilman fallbackia.
2. Osa datapoluista stale, osa tuoreita, odotettu osittainen fallback kayttaytyminen.
3. Forecast payload rakenteellisesti virheellinen, mutta runtime jatkuu turvallisesti.
4. Rajaarvot stale-timeoutissa (juuri validi vs juuri stale).

### P2: Dispatch-state applier branchit
Kohde: [ems_dispatch_state_applier.py](ems_dispatch_state_applier.py)

Miksi:
- Nykyinen kattavuus kohtalainen, mutta puuttuu useita branch-polkuja.

Tarvittavat uudet skenaariot:
1. CLEAR_ALL, jossa kaikki kolme latchia on paalla alussa, varmista kaikki release-haarat.
2. NOOP + freeze_until jo asetettu, varmista ettei freeze kirjoiteta uudestaan.
3. RELEASE_RELAY2 tilanteessa, jossa relay2 jo pois, varmista already-matching-kayttaytyminen.
4. Poikkeava freeze input (None, unknown, unavailable), varmista turvallinen kasittely.

### P3: Writer edge-branchit
Kohde: [ems_actuator_writers.py](ems_actuator_writers.py)

Miksi:
- Useita state_changed vs already_matching vs policy_skip polkuja.

Tarvittavat uudet skenaariot:
1. EV hard_off kun EV on jo pois paalta, varmista written False ja oikea reason.
2. Relay policy_skip kombinaatio DEGRADED-tilassa molemmille releille.
3. EV restore_min_current tilanteessa, jossa current jo minimi, varmista ei turhaa kirjoitusta.
4. Mixed branch step: relay1 kirjoitetaan, relay2 ei, EV ei, varmista trace-kentat tarkasti.

### P4: Load projection edge-case polut
Kohde: [modules/ems_core/net_zero/load_projection.py](modules/ems_core/net_zero/load_projection.py)

Miksi:
- Tarkeat ennusteeseen liittyvat reunatapaukset eivat nay E2E:ssa tarpeeksi.

Tarvittavat uudet skenaariot:
1. Puuttuva tai nolla data syotteissa, varmista fallback-arvot.
2. Epajohdonmukainen mittausdata useassa perakkaisessa stepissa.
3. Raja-arvot kuorman muutoksessa, jotka vaikuttavat seuraavaan dispatch targetiin.

## 4. Suositeltu uusi kansiorakenne
Uudet tarinat kannattaa lisata samaan malliin kuin nykyiset splitatut tarinat [tests/e2e_entity](tests/e2e_entity)-kansiossa:

- tests/e2e_entity/<story_name>/__init__.py
- tests/e2e_entity/<story_name>/scenario_steps.py
- tests/e2e_entity/<story_name>/test_01_*.py
- tests/e2e_entity/<story_name>/test_02_*.py
- tests/e2e_entity/<story_name>/test_03_*.py
- tests/e2e_entity/<story_name>/scenario_overview.md

Vertailupohjat:
- [tests/e2e_entity/hard_off_on_low_pv/scenario_steps.py](tests/e2e_entity/hard_off_on_low_pv/scenario_steps.py)
- [tests/e2e_entity/net_zero_force_on_battery_support/scenario_steps.py](tests/e2e_entity/net_zero_force_on_battery_support/scenario_steps.py)
- [tests/e2e_entity/goal_transition_net_zero_to_max_export/scenario_steps.py](tests/e2e_entity/goal_transition_net_zero_to_max_export/scenario_steps.py)

## 5. Toteutusmalli per uusi tarina
1. Luo story-kansio ja scenario_steps helper.
2. Tee 2-4 phase/scenario testitiedostoa, joista jokainen on itsenainen.
3. Seedaa jokaisen tiedoston alkuun kaikki kriittiset policy ja actuator alkuarvot.
4. Aja vaihekohtainen testi heti tiedoston luonnin jalkeen.
5. Lisaa scenario_overview dokumentoimaan phasejako ja tarkoitus.

Pakolliset assertion-ryhmat jokaisessa vaiheessa:
- expect_policy
- expect_policy_values
- expect_dispatch_state
- expect_values
- expect_writer_trace, jos writer branchia tavoitellaan

## 6. Seedays checklist (yleisimmat virhelahteet)
Ennen step-ajojen aloitusta tarkista aina:
1. goal_profile, forecast_profile, control_profile, guard_profile
2. surplus latchit: surplus_r1_active, surplus_adjustable_active, surplus_r2_active
3. actuator tilat: actuator_relay1, actuator_relay2, actuator_ev_enabled, actuator_ev_current_a
4. policy peilit: policy_relay1_command, policy_relay2_command, policy_ev_current_a, policy_battery_target_w
5. freeze tila: surplus_freeze_until ja policy trace attrs tarvittaessa
6. stale-tilat integraatiossa: heartbeat ja freshness source -entiteetit

## 7. Ehdotettu toteutusjarjestys seuraavaan sessioon
1. Luo uusi story: haeo_path_resilience
2. Luo uusi story: dispatch_state_branch_matrix
3. Luo uusi story: writer_branch_matrix_degraded
4. Luo uusi story: load_projection_edge_paths
5. Aja ensin storykohtaiset testit, sitten koko E2E coverage

## 8. Definition of Done seuraavalle sessiolle
Tarina on valmis kun:
1. Kaikki tarinan testit menevat lapi yksin ajettuna.
2. Koko tests/e2e_entity menee lapi.
3. Kattavuusraportissa kohdemoduulin prosentti nousee tai branch-lista supistuu.
4. scenario_overview.md paivitetty ja kertoo phasejaon.
5. Ei riippuvuuksia toisten testitiedostojen warmup-ajoihin.

## 9. Suositellut komennot
Yksittainen tarina:
- pytest -q tests/e2e_entity/<story_name>

Koko E2E + coverage:
- pytest -q tests/e2e_entity --cov=. --cov-report=term-missing

Kohdemoduulien nopea tarkastus raportista:
- grep -E 'haeo_horizon.py|ems_dispatch_state_applier.py|ems_actuator_writers.py|load_projection.py' /tmp/cov_e2e_all.txt

## 10. Huomiot seuraavaa sessiota varten
- Pida splitatut testit lyhyina ja intentionaalisina: yksi selkea tavoite per phase/scenario tiedosto.
- Varmista aina, etta odotus kohdistuu oikeaan kerrokseen: policy paatos, dispatch state vai writerin nakyva vaikutus.
- Jos kattavuus ei nouse odotetusti, tarkista ensin puuttuvat seedattavat policy attrs ja freeze-aikaleimat.
