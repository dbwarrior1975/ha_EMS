# E2E Refactor Handover (Next Session)

## Dokumentin status

Tama on historiallinen handover-dokumentti E2E-refaktoroinnin ajalta. Useat alla mainitut monoliittiset `tests/e2e_entity/test_*.py`-tiedostot on jo poistettu ja korvattu story-kansioilla.

Nykyinen E2E-rakenne löytyy kansioista `tests/e2e_entity/<story>/`, ja jokaisen storyn tarkin kuvaus on sen omassa `scenario_overview.md`-tiedostossa.

## Tavoite
Refaktoroi e2e testit vaiheittain samaan malliin, joka on toteutettu kansiossa:
- tests/e2e_entity/hard_off_on_low_pv/

Tavoitemalli per testitiedosto:
1. Yksi selkeä phase tai rajattu semanttinen tarina per tiedosto.
2. Tiedosto seedaa oman alkutilansa (ei pitkää warmup-ketjua).
3. Stepit ovat kyseisessä tiedostossa, eivät piilotettuna phase helperiin.
4. Yhteinen infra pidetään kevyenä (build_harness + run_steps).

## Nykyinen referenssi
Käytä näitä esimerkkinä:
- tests/e2e_entity/hard_off_on_low_pv/test_01_activation_and_burn.py
- tests/e2e_entity/hard_off_on_low_pv/test_02_release_and_restore_min.py
- tests/e2e_entity/hard_off_on_low_pv/test_03_low_pv_to_hard_off.py
- tests/e2e_entity/hard_off_on_low_pv/test_04_hard_off_persistence_and_relay_release.py
- tests/e2e_entity/hard_off_on_low_pv/test_05_recovery_and_reactivation.py
- tests/e2e_entity/hard_off_on_low_pv/scenario_steps.py
- tests/e2e_entity/hard_off_on_low_pv/scenario_overview.md

## Käytännön refaktorointiohje
1. Valitse yksi pitkä tai monivaiheinen e2e testi.
2. Pilko tarina 2-5 phase tiedostoon, jos hyödyllistä.
3. Lisää joka phase tiedostoon:
- docstring, joka kuvaa phase semantiikan
- explicit h.set_entities alkutila
- tarvittaessa h.set_attrs policy seediin (esim. hard_off state)
- local steps lista, jossa at_s, note, set ja expect_* kentät
4. Aja run_steps(h, steps) tiedoston lopussa.
5. Varmista että vanhat warmup-ketjut poistuvat kyseisestä phase tiedostosta.

## Yhteinen infra
Yhteiseen helperiin jätetään vain:
1. build_harness(project_root)
2. run_steps(h, steps, validate=True)

Vältä lisäämästä phaseX_steps ja step_tX helper-kokoelmia yhteiseen tiedostoon.

## Semantiikan suojaus
1. Älä muuta testin liiketoimintasemantiikkaa ilman näkyvää syytä.
2. Jos seed-alkutila ei ole ilmeinen, varmista policy-attribuutit h.set_attrs kautta.
3. Säilytä expect_policy, expect_dispatch_state, expect_writer_trace, expect_values kattavuus.
4. Jos odotusarvo muuttuu refaktoroinnissa, perustele muutos erikseen.
5. Huomioi kumuloituvat actuator-arvot: jos alkuperäinen tarina etenee setpoint-portain (esim. 200 -> 400 -> 600 ...), phase-seedissä pitää asettaa edellisen phasen loppuarvo eksplisiittisesti.

## Viime session toteutunut refaktorointi (2026-06-12)
Valmistunut kohde:
- tests/e2e_entity/test_battery_protect_min_cell_recovery_quarter2.py

Toteutettu rakenne:
- tests/e2e_entity/battery_protect_min_cell_recovery/scenario_steps.py
- tests/e2e_entity/battery_protect_min_cell_recovery/test_01_baseline_and_trigger.py
- tests/e2e_entity/battery_protect_min_cell_recovery/test_02_recovery_gate_then_restore.py
- tests/e2e_entity/battery_protect_min_cell_recovery/test_03_min_cell_retrigger_and_recovery.py
- tests/e2e_entity/battery_protect_min_cell_recovery/scenario_overview.md

Poistetut/korvatut:
- tests/e2e_entity/test_battery_protect_min_cell_recovery_quarter2.py (poistettu monoliittina)

Validointi:
- pytest -q tests/e2e_entity/battery_protect_min_cell_recovery -q

Tärkeä oppi seuraavaan sessioon:
1. Pelkkä guard/soc/min_cell seedaus ei aina riitä itsenäiseen phaseen.
2. Jos assertit odottavat timeline-kumulatiivista battery_setpoint-arvoa, seedaa myös ENT['actuator_battery_setpoint_w'] phase alkuun.
3. Tässä kohteessa phase-seedit vaativat arvot:
- phase 2 alkuun actuator_battery_setpoint_w=400
- phase 3 alkuun actuator_battery_setpoint_w=800

## Viime session toteutunut refaktorointi (2026-06-12, jatko)
Valmistunut kohde:
- tests/e2e_entity/test_net_zero_priority_order_quarter.py

Toteutettu rakenne:
- tests/e2e_entity/net_zero_priority_order_quarter/scenario_steps.py
- tests/e2e_entity/net_zero_priority_order_quarter/test_01_activation_chain.py
- tests/e2e_entity/net_zero_priority_order_quarter/test_02_release_relay2_then_adjustable.py
- tests/e2e_entity/net_zero_priority_order_quarter/test_03_release_relay1_then_restart.py
- tests/e2e_entity/net_zero_priority_order_quarter/scenario_overview.md

Poistetut/korvatut:
- tests/e2e_entity/test_net_zero_priority_order_quarter.py (poistettu monoliittina)

Validointi:
- pytest -q tests/e2e_entity/net_zero_priority_order_quarter -q

Tärkeä oppi seuraavaan sessioon:
1. Jos phasen ensimmäinen askel odottaa aiemman jäädytysikkunan näkyvän policy-traceen, seedaa myös ENT['surplus_freeze_until'] (esim. 75.0).
2. Pelkkä active-flagien seedaus (surplus_r1_active/surplus_adjustable_active/surplus_r2_active) ei yksin riitä freeze-assertteihin.

## Viime session toteutunut refaktorointi (2026-06-12, force-on)
Valmistunut kohde:
- tests/e2e_entity/test_net_zero_force_on_battery_support.py

Toteutettu rakenne:
- tests/e2e_entity/net_zero_force_on_battery_support/scenario_steps.py
- tests/e2e_entity/net_zero_force_on_battery_support/test_01_force_rising_edge_freeze_hygiene.py
- tests/e2e_entity/net_zero_force_on_battery_support/test_02_relay1_on_then_release_under_force.py
- tests/e2e_entity/net_zero_force_on_battery_support/test_03_unforce_then_reactivate_relay2.py
- tests/e2e_entity/net_zero_force_on_battery_support/test_04_relay1_reactivation_after_relay2_freeze.py
- tests/e2e_entity/net_zero_force_on_battery_support/scenario_overview.md

Poistetut/korvatut:
- tests/e2e_entity/test_net_zero_force_on_battery_support.py (poistettu monoliittina)

Validointi:
- pytest -q tests/e2e_entity/net_zero_force_on_battery_support -q

Tärkeä oppi seuraavaan sessioon:
1. Force-on skenaarioissa phase-seed voi vaatia policy trace -attribuuttien alustuksen (h.set_attrs(ENT['policy_decision_trace'], ...))
	jotta prev_relay*_force_on-kentät eivät laukaise keinotekoista force rising-edge freezeä phasen alussa.
2. Jos vaihe alkaa force-jälkitilasta, seedaa sekä relay*_force_on että surplus_freeze_until tarvittaessa yhdessä.

## Viime session toteutunut refaktorointi (2026-06-12, homebattery adjustable)
Valmistunut kohde:
- tests/e2e_entity/test_net_zero_homebattery__is_adjustable_load.py

Toteutettu rakenne:
- tests/e2e_entity/net_zero_homebattery_adjustable_load/scenario_steps.py
- tests/e2e_entity/net_zero_homebattery_adjustable_load/test_01_baseline_to_adjustable_activation.py
- tests/e2e_entity/net_zero_homebattery_adjustable_load/test_02_release_and_low_pv_hard_off_path.py
- tests/e2e_entity/net_zero_homebattery_adjustable_load/test_03_recovery_and_reactivation.py
- tests/e2e_entity/net_zero_homebattery_adjustable_load/scenario_overview.md

Poistetut/korvatut:
- tests/e2e_entity/test_net_zero_homebattery__is_adjustable_load.py (poistettu monoliittina)

Validointi:
- pytest -q tests/e2e_entity/net_zero_homebattery_adjustable_load -q

Tärkeä oppi seuraavaan sessioon:
1. Pitkässä low-PV/hard-off tarinassa phase-jako vaatii usein EV policy -attribuuttien seedauksen (`ev_policy_mode`, `ev_low_pv_cycles`, `ev_hard_off_active`) vaiheiden rajalla, jotta hard-off jatkuvuus ei katkea.
2. Kun ensimmäinen askel odottaa aiemmin aktivoitua ADJUSTABLE-tilaa, seedaa sekä `surplus_adjustable_active` että tarvittaessa `surplus_freeze_until` ja actuator-tila (`actuator_ev_enabled`, `actuator_ev_current_a`).

## Viime session toteutunut refaktorointi (2026-06-12, ev adjustable)
Valmistunut kohde:
- tests/e2e_entity/test_net_zero_ev_is_adjustable_load.py

Toteutettu rakenne:
- tests/e2e_entity/net_zero_ev_adjustable_load/scenario_steps.py
- tests/e2e_entity/net_zero_ev_adjustable_load/test_01_ev_primary_ramp_and_adjustable_activation.py
- tests/e2e_entity/net_zero_ev_adjustable_load/test_02_release_and_hard_off_hold.py
- tests/e2e_entity/net_zero_ev_adjustable_load/test_03_post_hard_off_recovery.py
- tests/e2e_entity/net_zero_ev_adjustable_load/scenario_overview.md

Poistetut/korvatut:
- tests/e2e_entity/test_net_zero_ev_is_adjustable_load.py (poistettu monoliittina)

Validointi:
- pytest -q tests/e2e_entity/net_zero_ev_adjustable_load -q

Tärkeä oppi seuraavaan sessioon:
1. EV-primary + HOME_BATTERY adjustable -tarinassa phase-2 alun odotukset riippuvat usein siitä, että phase-1 lopun `surplus_freeze_until` ja relay/adjustable active-tilat on seedattu yhtä aikaa.
2. Hard-off jälkitilasta alkava phase tarvitsee `policy_ev_current_a` attribuuttiseedauksen (`ev_policy_mode=hard_off`, `ev_low_pv_cycles`, `ev_hard_off_active`) tai release-ready käyttäytyminen voi muuttua.

## Suositeltu työjärjestys
1. Refaktoroi yksi kohdetiedosto tai yksi vaihe kerrallaan.
2. Aja ensin kohdetesti:
- pytest -q tests/e2e_entity/<kohde>.py -q
3. Aja lopuksi koko e2e_entity alikansio tai relevantti subset:
- pytest -q tests/e2e_entity -q

## Nykytila candidate-listan sijaan

Alkuperainen seuraavan aallon kandidaattilista on vanhentunut. Nykyiset refaktoroidut E2E-storyt ovat:

1. `tests/e2e_entity/battery_protect_min_cell_recovery/`
2. `tests/e2e_entity/goal_transition_net_zero_to_max_export/`
3. `tests/e2e_entity/hard_off_on_low_pv/`
4. `tests/e2e_entity/net_zero_ev_adjustable_load/`
5. `tests/e2e_entity/net_zero_force_on_battery_support/`
6. `tests/e2e_entity/net_zero_homebattery_adjustable_load/`
7. `tests/e2e_entity/net_zero_priority_order_quarter/`
8. `tests/e2e_entity/optimizer_degraded_fallback/`
9. `tests/e2e_entity/system_degraded_safe_mode/`

## Refaktorointi-runbook (copy-paste)
1. Valitse kohde ja nimeä uusi kansio:
- tests/e2e_entity/<story_name>/
2. Luo tiedostot:
- __init__.py
- scenario_steps.py
- test_01_<phase_name>.py
- test_02_<phase_name>.py
- test_03_<phase_name>.py (vain jos tarpeen)
- scenario_overview.md
3. Lisää scenario_steps.py:
- build_harness(project_root)
- run_steps(h, steps)
- ei phase-kohtaisia step-helper-kokoelmia
4. Siirrä stepit phase-tiedostoihin:
- jokaisessa tiedostossa oma local steps-lista
- jokaisessa tiedostossa docstring, joka kertoo phasen semantiikan
5. Seedaa phase-alkutila eksplisiittisesti:
- h.set_entities(...) aina, kun vaihe riippuu edeltävästä tilasta
- h.set_attrs(...) jos policy-trace state tarvitsee seedauksen
- muista kumuloituvat actuator-arvot (esim. actuator_battery_setpoint_w)
6. Poista monoliittitesti, kun phase-testit ovat vihreänä.
7. Päivitä scenario_overview.md:
- phase-jako
- mitä kukin phase varmistaa
8. Aja validointi:
- pytest -q tests/e2e_entity/<story_name> -q
- pytest -q tests/e2e_entity/<relevant_subset> -q
9. Päivitä tämä handover:
- mitä refaktoroitiin
- mikä poistettiin
- mitä opittiin seedauksesta
- seuraavat candidate-kohteet

Nopea tarkistuslista ennen commitia:
1. Jokainen phase-testi menee läpi yksin.
2. Ei hidden warmup -ketjuja.
3. expect_* kattavuus ei heikentynyt.
4. scenario_overview vastaa toteutusta.
5. Handover sisältää uuden deltan seuraavaa sessiota varten.

## Definition of Done per kohde
1. Phase tiedostot ovat luettavia ilman ulkoista warmup-ketjua.
2. Jokainen phase testi menee läpi yksin.
3. Koko kohdekansio menee läpi.
4. scenario_overview.md (tai vastaava) päivitetty vastaamaan toteutunutta rakennetta.
