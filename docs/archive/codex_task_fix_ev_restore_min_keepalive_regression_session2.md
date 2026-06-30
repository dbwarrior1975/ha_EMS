# Codex Task Session 2: Fix EV Restore-Min Keepalive Regression

## Tavoite

Korjaa EV restore-min / hard_off -regressio niin, etta ennen varsinaista hard_offia EMS palauttaa jo paalla olevan EV-laturin current-selectorin minimiin mutta ei sammuta laturin switchia.

Nykyinen regressio on writerissa:

```text
target_current_a == 0 -> disable charger -> set current selector to derived_min_a
```

Tama on oikein `hard_off`-tilassa, mutta vaarin `restore_min`-tilassa.

Korjauksen jalkeen:

```text
restore_min + charger_on=true:
  actuator_ev_enabled pysyy True
  actuator_ev_current_a -> derived_min_a
  writer reason -> restore_min tai restore_min_current

restore_min + charger_on=false:
  actuator_ev_enabled pysyy False
  actuator_ev_current_a -> derived_min_a jos selector ei ole jo minimissa
  writer ei kaynnista laturia

hard_off:
  actuator_ev_enabled -> False
  actuator_ev_current_a -> derived_min_a
  writer reason -> hard_off

release / eksplisiittinen off:
  actuator_ev_enabled -> False
  actuator_ev_current_a -> derived_min_a
  writer reason -> target_zero_disable tai release
```

## Tarkeat loydot edellisesta sessiosta

1. Alkuperaisen taskin writer-polku on vanhentunut. Nykyinen writer on repojuuressa:

```text
ems_actuator_writers.py
```

ei:

```text
modules/ems_adapter/ems_actuator_writers.py
```

2. Regressiokohta on funktiossa:

```text
ems_actuator_writers.py::_write_ev_actuator()
```

Nykyinen nollavirran haara tekee `set_boolean(enabled_entity, False)` ennen kuin se erottaa `hard_off`-tilan muista nollatiloista.

3. Regressiota kuvaava e2e-testi on:

```text
tests/e2e_entity/hard_off_on_low_pv/test_02_release_and_restore_min.py
```

Sen t95-step odottaa nyt virheellisesti:

```text
EV_CHARGER.enabled = False
writer reason = target_zero_disable
actuator_ev_enabled = False
actuator_ev_current_a = 8
```

Se pitaa palauttaa odottamaan keepalive-semanttiikkaa:

```text
EV_CHARGER.enabled = True
writer reason = restore_min tai restore_min_current
actuator_ev_enabled = True
actuator_ev_current_a = 8
```

4. Varsinainen hard_off-testi on:

```text
tests/e2e_entity/hard_off_on_low_pv/test_03_low_pv_to_hard_off.py
```

Sita ei saa heikentaa. Sen pitaa edelleen odottaa:

```text
EV_CHARGER.enabled = False
writer reason = hard_off
actuator_ev_enabled = False
actuator_ev_current_a = 8
```

5. Engine tuottaa kyseisessa e2e-polussa restore-minin nollatehona, koska scenario on EV adjustable / home battery primary:

```text
tests/e2e_entity/hard_off_on_low_pv/scenario_steps.py
adjustable_surplus_load = EV_CHARGER
adjustable_primary_load = HOME_BATTERY
```

Tama tekee writerin mode-erottelusta pakollisen. Alkuperaisen taskin vaihtoehto `restore_min target_w = min_absorb_w` koskee paremmin EV-primary-polkuja, ei tata e2e-regressiota.

## Vaihe 1: Korjaa writerin mode-haara

Muokkaa:

```text
ems_actuator_writers.py
```

Funktiossa:

```text
_write_ev_actuator(device_id='EV_CHARGER', entities=None)
```

Rakenna nollavirran kasittely selkeasti mode-pohjaiseksi.

Suositeltu rakenne:

```python
if target_current_a > 0:
    # nykyinen enable_and_set_current-haara ennallaan
    ...

if ev_policy_mode == 'restore_min':
    enabled_changed = False
    current_changed = False
    if current_level != derived_min_a:
        set_number(current_entity, derived_min_a)
        current_changed = True
    return {
        'target': 'ev',
        'action': 'restore_min_current',
        'reason': capability_reason or 'restore_min',
        'written': current_changed,
        'policy_target_w': target_w,
        'target_current_a': derived_min_a,
        'enabled_changed': False,
        'current_changed': current_changed,
        'policy_source': policy_source,
    }

if ev_policy_mode == 'hard_off':
    # disable + restore min
    ...

# release / explicit zero fallback
# disable + restore min
...
```

Tarkeaa:

1. `restore_min` ei saa kutsua `set_boolean(enabled_entity, False)`.
2. `restore_min` ei saa kutsua `set_boolean(enabled_entity, True)`.
3. `restore_min` saa kirjoittaa current-selectorin minimiin riippumatta switchin nykytilasta.
4. `hard_off` sailyy eksplisiittisena disable-polku­na.
5. `release` ja muu eksplisiittinen zero/off fallback saavat edelleen sammuttaa laturin.

Huomio `written`-kentasta:

Jos laturi oli paalla ja current muuttuu 28 A -> 8 A, `written=True`.
Jos laturi oli paalla ja current oli jo 8 A, `written=False` on ok, kunhan `actuator_ev_enabled` pysyy True ja trace reason ei valehtele disableksi.

## Vaihe 2: Paivita writer-yksikkotestit

Muokkaa:

```text
tests/unit/test_writer_semantics.py
```

Sailyta nykyinen testi:

```text
test_writer_loop_disables_ev_and_restores_min_current_when_target_w_is_zero
```

mutta varmista, etta se testaa eksplisiittista release/off-semanttiikkaa, ei restore-minia. Nykyinen policy kayttaa jo:

```text
mode = release
```

joten testi voi jaada disable-odotukselle.

Lisa uusi testi:

```text
test_writer_restore_min_keeps_enabled_charger_alive
```

Skenaario:

```text
policy:
  device_id = EV_CHARGER
  target_w = 0
  enabled = True
  mode = restore_min

initial state:
  actuator_ev_enabled = True
  actuator_ev_current_a = 16
  ev_current_step_a = 1
  ev_charger_phases = 1
  ev_voltage_v = 230

expect:
  result['reason'] in {'restore_min', 'restore_min_current'}
  result['target_current_a'] == 6
  actuator_ev_enabled is True
  actuator_ev_current_a == 6
```

Lisa toinen testi:

```text
test_writer_restore_min_does_not_start_disabled_charger
```

Skenaario:

```text
policy:
  device_id = EV_CHARGER
  target_w = 0
  enabled = True tai False
  mode = restore_min

initial state:
  actuator_ev_enabled = False
  actuator_ev_current_a = 16

expect:
  actuator_ev_enabled is False
  actuator_ev_current_a == 6
  enabled_changed is False
  no enable call semantics in trace/result
```

Pidä nykyinen testi ennallaan:

```text
test_writer_hard_off_disables_ev_and_sets_current_to_derived_min
```

Sen pitaa edelleen todistaa hard_off-disable.

## Vaihe 3: Paivita e2e-regressiotesti

Muokkaa:

```text
tests/e2e_entity/hard_off_on_low_pv/test_02_release_and_restore_min.py
```

t95-stepin odotukset:

```text
expect_device_policies:
  EV_CHARGER:
    enabled: True
    mode: restore_min

expect_writer_trace:
  EV_CHARGER:
    reason: restore_min tai restore_min_current
    written: True
    target_current_a: 8

expect_values:
  actuator_ev_enabled: True
  actuator_ev_current_a: 8
```

Jos scenario-runner ei tue `mode`-odotusta `expect_device_policies`-rakenteessa, lisaa se vain jos nykyinen helper tukee kentan. Muuten tarkista `enabled=True` ja writer trace reason.

Alkuarvo on jo oikea:

```text
seed_active_surplus_devices(... actuator_ev_enabled=True, actuator_ev_current_a=28)
```

Siksi t95 on juuri keepalive-regressiotapaus.

## Vaihe 4: Varmista hard_off-polku

Tarkista, ettei muutos riko:

```text
tests/e2e_entity/hard_off_on_low_pv/test_03_low_pv_to_hard_off.py
```

Odotusten tulee pysya:

```text
EV_CHARGER.enabled = False
reason = hard_off
actuator_ev_enabled = False
actuator_ev_current_a = 8
```

Jos testi alkaa odottaa `restore_min`-kaytosta, korjaus on liian lavea.

## Vaihe 5: Dokumentoi aktiivinen semantiikka

Paivita vahintaan:

```text
docs/dev/arkkitehtuuri.md
```

Kohta:

```text
## Nykyinen EV 0 A -semantiikka
```

Korvaa nykyinen epatarkka kohta:

```text
ilman hard_off-attribuuttia -> writer tulkitsee tilanteen surplus release -polkuna
```

selkealla mode-erottelulla:

```text
ev_policy_mode=restore_min:
  jo paalla oleva laturi pidetaan paalla ja current-selector palautetaan minimiin
  pois paalla olevaa laturia ei kaynnisteta

ev_policy_mode=hard_off:
  laturi sammutetaan ja current-selector palautetaan minimiin

release/off:
  laturi sammutetaan ja current-selector palautetaan minimiin
```

Tarkista myos:

```text
docs/user/operointi.md
README.md
docs/dev/e2e/hard_off_on_low_pv.md
```

Paivita vain kohdat, jotka vaittavat tai implikoivat, etta restore-min/release aina sammuttaa laturin.

## Vaihe 6: Aja kohdennetut testit

Minimitestit:

```bash
pytest tests/unit/test_writer_semantics.py -q
pytest tests/e2e_entity/hard_off_on_low_pv/test_02_release_and_restore_min.py -q
pytest tests/e2e_entity/hard_off_on_low_pv/test_03_low_pv_to_hard_off.py -q
```

Jos aikaa:

```bash
pytest tests/e2e_entity/hard_off_on_low_pv -q
pytest tests/unit/test_engine.py -q
```

## Vaihe 7: Regressiohaku ennen lopetusta

Aja:

```bash
rg -n "target_zero_disable|restore_min_current|restore_min|hard_off|target_current_a == 0|target_w <= 0" ems_actuator_writers.py tests docs README.md
```

Varmista:

1. `restore_min` ei ole missaan disable-synonyymi.
2. `hard_off` on edelleen eksplisiittinen disable.
3. `target_zero_disable` ja release/off eivat ime restore-min-tapauksia mukaansa.
4. E2E hard_off phase 2 odottaa keepalivea ja phase 3 odottaa disablea.

## Hyvaksymiskriteerit

1. `restore_min` ei sammuta jo paalla olevaa EV-laturia.
2. `restore_min` palauttaa current-selectorin johdettuun minimiin.
3. `restore_min` ei kaynnista pois paalla olevaa EV-laturia.
4. `hard_off` sammuttaa EV-laturin ja palauttaa current-selectorin minimiin.
5. `release` / eksplisiittinen zero-off jatkaa disable-polulla.
6. `tests/e2e_entity/hard_off_on_low_pv/test_02_release_and_restore_min.py` odottaa t95-kohdassa `actuator_ev_enabled=True`.
7. `tests/e2e_entity/hard_off_on_low_pv/test_03_low_pv_to_hard_off.py` odottaa edelleen `actuator_ev_enabled=False`.
8. Kohdennetut unit- ja e2e-testit menevat lapi.

## Ei kuulu tahan korjaukseen

1. Ala palauta vanhoja amp-policy config -kenttia:

```text
force_current_a
current_min_a
current_max_a
ev_force_current_a
ev_min_current_a
ev_max_current_a
```

2. Ala muuta EV:n kanonista writer-sopimusta takaisin ampeeripohjaiseksi. `DevicePolicy.target_w` pysyy kanonisena syotteena.
3. Ala muuta enginea tuottamaan min-watt targetia tahan e2e-polkuun, ellei writer-korjaus yksin osoittaudu mahdottomaksi. Taman regression ydin on writerin mode-erottelu.
4. Ala heikenna MAX_EXPORT- tai hard_off-disable-semanttiikkaa.
