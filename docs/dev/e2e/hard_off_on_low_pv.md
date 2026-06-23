# Story: NET_ZERO EV hard-off on low PV

## Mitä tässä kansiossa on
- [tests/e2e_entity/hard_off_on_low_pv/test_01_activation_and_burn.py](tests/e2e_entity/hard_off_on_low_pv/test_01_activation_and_burn.py)
- [tests/e2e_entity/hard_off_on_low_pv/test_02_release_and_restore_min.py](tests/e2e_entity/hard_off_on_low_pv/test_02_release_and_restore_min.py)
- [tests/e2e_entity/hard_off_on_low_pv/test_03_low_pv_to_hard_off.py](tests/e2e_entity/hard_off_on_low_pv/test_03_low_pv_to_hard_off.py)
- [tests/e2e_entity/hard_off_on_low_pv/test_04_hard_off_persistence_and_relay_release.py](tests/e2e_entity/hard_off_on_low_pv/test_04_hard_off_persistence_and_relay_release.py)
- [tests/e2e_entity/hard_off_on_low_pv/test_05_recovery_and_reactivation.py](tests/e2e_entity/hard_off_on_low_pv/test_05_recovery_and_reactivation.py)
- [tests/e2e_entity/hard_off_on_low_pv/scenario_steps.py](tests/e2e_entity/hard_off_on_low_pv/scenario_steps.py)

## Vaihejako
1. Phase 1 (t0, t30, t46, t60): RELAY1 -> ADJUSTABLE -> EV burn stabilointi.
2. Phase 2 (t90, t95): RELEASE_ADJUSTABLE ja EV min-current restore.
3. Phase 3 (t120): toinen low-PV sykli laukaisee hard_off.
4. Phase 4 (t180, t210): hard_off pysyy ja RELAY1 release-polku näkyy.
5. Phase 5 (t224, t238, t240, t270): palautuminen, freeze-ikkuna, ADJUSTABLE odotus, EV burn palautuu.

## Toteutusperiaate
1. Jokainen phase-tiedosto on itsenäinen: tiedosto seedaa oman alkutilan.
2. Jokaisen tiedoston stepit ovat kyseisessä tiedostossa.
3. Yhteinen infra [tests/e2e_entity/hard_off_on_low_pv/scenario_steps.py](tests/e2e_entity/hard_off_on_low_pv/scenario_steps.py):
- build_harness
- run_steps

## Miksi tämä rakenne
1. Regressio paikantuu yleensä yksittäiseen phase-tiedostoon.
2. Tarina on luettavissa tiedosto kerrallaan ilman pitkää warmup-ketjua.
