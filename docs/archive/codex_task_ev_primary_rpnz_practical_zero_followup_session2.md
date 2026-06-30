# Codex Task: EV-primary RPNZ practical-zero follow-up

## Tavoite

Tee rajattu jatkomuutos auditin `codex_task_audit_ev_primary_rpnz_deadband_and_docs.md` pohjalta.

Tavoite on:

1. arvioida ja korjata EV-primary-polun jäljellä oleva strict-zero RPNZ-logiikka
2. jakaa sama `10 W` practical-zero-semanttiikka ilman duplikaattiliteraaleja
3. lisätä focused unit-testit EV-primary edge-caseille
4. korjata stale dokumentaatio, jossa surplus-release kuvataan vielä muodossa `rpnz_w <= 0`

Älä tee laajaa business-logiikan refaktorointia. Muutosalueen pitää pysyä `engine.py`, RPNZ/deadband-vakioissa, focused testeissä ja dokumentaatiossa.

## Nykytilan arvio

Auditin strict-zero-kohta löytyy tiedostosta:

```text
modules/ems_core/net_zero/engine.py
```

Funktio:

```text
_battery_target_and_authority(...)
```

Business-polku:

```python
if (
    use_ev_primary_mode
    and ev_burn_active
    and float(nz.rpnz_w) <= 0.0
    and (not ev_release_pending)
):
    adjustable_surplus_active_next = False
    raw = int(round(min_charge_floor_w))
```

Tämä ei ole generic surplus allocator -release, vaan EV-primary / battery target authority -polku. Se vaikuttaa siihen, milloin EV-primary-tilassa battery-adjustable state puretaan ja akun target palautetaan EV-active flooriin.

Luokitus auditin vaihtoehdoista:

```text
B. EV-primary target authority / battery target override
```

Se ei ole hard-off release counter eikä suoraan `compute_surplus_device_dispatch`-allokaattorin release-päätös.

## Tärkeä toteutusriski

Älä korjaa vain ehtoa:

```diff
- float(nz.rpnz_w) <= 0.0
+ float(nz.rpnz_w) <= SURPLUS_RELEASE_DEADBAND_W
```

Se ei riitä, koska sama funktio haarautuu aiemmin näin:

```python
ev_primary_positive_rpnz = bool(use_ev_primary_mode) and float(nz.rpnz_w) > 0.0
...
if ev_primary_positive_rpnz:
    raw = int(round(min_charge_floor_w))
else:
    ...
```

Nykykoodissa `rpnz_w = +4 W` menee positive-haaraan eikä koskaan päädy strict-zero-ehtoon. Jos EV-primaryn pitää kohdella `+4 W` ja `+10 W` käytännön nollana, positive-haaran raja täytyy muuttaa samaksi practical-zero-rajaksi.

## Suositeltu päätös

Käytä EV-primary-polussa samaa `10 W` practical-zero-rajaa kuin active surplus release käyttää.

Perustelu:

1. Auditissa kuvattu ongelma on sama fysikaalinen reunatapaus: vartin alun pieni positiivinen RPNZ, esimerkiksi `+4 W`, ei saa pitää kW-luokan kulutuspolkua latchattuna.
2. EV-primary target authority käyttää ehtoa purettaessa / normalisoitaessa aktiivista burn-tilaa, joten `+1...+10 W` on tässäkin käytännön nolla eikä merkittävä lisäkulutustarve.
3. Strict-zero jäisi muuten epäjohdonmukaiseksi suhteessa surplus allocatoriin ja vaatisi erillisen business-perustelun, jota nykykoodista tai dokumentaatiosta ei löydy.

Jos toteuttaja löytää testillä tai business-analyysillä syyn pitää EV-primary strict-zero, muutos pitää jättää tekemättä ja lisätä koodikommentti sekä testit strict-zero-semanttiikalle. Oletuslinja tälle sessiolle on kuitenkin practical-zero.

## Suositeltu koodimuutos

Tiedosto:

```text
modules/ems_core/net_zero/surplus_allocator.py
```

Muuta nykyinen vakio näin, jotta termi ei ole liian kapea EV-primary-käyttöön:

```python
RPNZ_PRACTICAL_ZERO_W = 10.0
SURPLUS_RELEASE_DEADBAND_W = RPNZ_PRACTICAL_ZERO_W
```

Säilytä `SURPLUS_RELEASE_DEADBAND_W`, jotta nykyiset surplus allocator -testit ja domain-termi pysyvät yhteensopivina.

Tiedosto:

```text
modules/ems_core/net_zero/engine.py
```

Tuo uusi vakio importtiin:

```python
from ems_core.net_zero.surplus_allocator import (
    RPNZ_PRACTICAL_ZERO_W,
    active_device_stack,
    compute_surplus_device_dispatch,
    next_device_target,
    release_device_target,
)
```

Muuta EV-primary positive-luokitus practical-zeroa vasten:

```python
ev_primary_material_positive_rpnz = (
    bool(use_ev_primary_mode)
    and float(nz.rpnz_w) > RPNZ_PRACTICAL_ZERO_W
)
```

Käytä uutta muuttujaa nykyisen `ev_primary_positive_rpnz`-muuttujan tilalla tässä funktiossa.

Muuta strict-zero-ehto:

```python
and float(nz.rpnz_w) <= RPNZ_PRACTICAL_ZERO_W
```

Suositeltu muuttujanimi on `ev_primary_material_positive_rpnz`, koska `> 0` ei enää pidä paikkaansa. Jos käytät lyhyempää nimeä, älä jätä vanhaa `positive_rpnz`-nimeä harhaanjohtavaksi.

## Testit

Lisää focused unit-testit tiedostoon:

```text
tests/unit/test_engine.py
```

Hyvä paikka on nykyisten EV-primary-testien lähellä:

```text
test_engine_ev_primary_restore_min_allows_battery_discharge_when_charger_off
test_engine_ev_primary_restore_min_holds_battery_floor_when_charger_on
```

Lisää parametrisoitu business-testi:

```python
@pytest.mark.unit
@pytest.mark.parametrize(
    ('rpnz_w', 'expected_floor_hold'),
    [
        (4.0, True),
        (10.0, True),
        (11.0, False),
        (0.0, True),
        (-1.0, True),
    ],
)
def test_engine_ev_primary_treats_tiny_positive_rpnz_as_practical_zero_for_battery_authority(rpnz_w, expected_floor_hold):
    ...
```

Testin asetelma:

1. `profiles = AUTOMATIC / NET_ZERO`
2. `cfg = make_cfg(adjustable_surplus_load='HOME_BATTERY', adjustable_primary_load='EV_CHARGER')`
3. `m = make_m(current_battery_setpoint_w=-1000, grid_power_w=2900.0, ev_states={'EV_CHARGER': ev_state(enabled=True, current_a=cfg_ev_min_a(cfg))})`
4. `nz = make_nz(rpnz_w=rpnz_w, required_power_consumption_kw=0.5)`
5. kutsu `compute_net_zero_engine_outputs(..., adjustable_surplus_active=True, pv_power_kw=1.7, ev_hard_off_active=False, ev_low_pv_cycles=0)`

Odotus practical-zero-linjalla:

```text
rpnz_w <= 10 W -> battery_target_w == nz_battery_floor_ev_active_w, oletus testeissä 0
rpnz_w > 10 W  -> battery_target_w == nz_battery_floor_ev_active_w myös positive-haarassa, mutta erota käyttäytyminen attrsilla:
                 out.attrs['surplus_adjustable_active'] on False practical-zero-tapauksissa ja True material-positive-tapauksessa
```

Jos yllä oleva asetelma ei erottele `+10 W` ja `+11 W` riittävästi akun targetilla, asserttoi nimenomaan:

```python
assert out.attrs['surplus_adjustable_active'] is (not expected_floor_hold)
```

Tämä osuu suoraan `_battery_target_and_authority`-funktion muuttuvaan stateen.

Pidä vanhat hard-off-testit ennallaan. Erityisesti nykyinen testi

```text
test_engine_ev_primary_home_battery_small_positive_rpnz_does_not_release_hard_off
```

koskee hard-off release counteria eikä ole sama asia kuin EV-primary battery authority practical-zero.

## Dokumentaatio

Korjaa ainakin:

```text
docs/dev/arkkitehtuuri.md
```

Nykyinen ristiriita:

1. rivien noin 340 ympärillä dokumentti kuvaa jo `rpnz_w <= 10 W` practical-zero-deadbandin
2. Surplus-allokaatio-osiossa rivien noin 460 ympärillä listassa on edelleen `jos rpnz_w <= 0`

Muuta stale kohta:

```text
jos `rpnz_w <= SURPLUS_RELEASE_DEADBAND_W` ja aktiivisia kohteita on -> vapauta alin prioriteetti ensin
```

Lisää EV-primary-poikkeukseen lyhyt täsmennys:

```text
EV-primary battery-authority käyttää samaa `RPNZ_PRACTICAL_ZERO_W = 10 W` käytännön nollaa erottaakseen pienen positiivisen RPNZ:n aidosta lisäkulutustarpeesta.
```

Älä muuta historiallisia archive-dokumentteja, ellei aktiivinen haku osoita niihin viittaavaa release-dokumentaatiota. Aktiiviset dokumentit ovat ensisijaisesti `README.md`, `docs/dev/*` ja `docs/user/*`.

## Tarkistushaut

Aja ennen ja jälkeen:

```bash
rg -n "float\\(nz\\.rpnz_w\\) <= 0\\.0|rpnz_w\\) <= 0|rpnz_w <= 0|ev_primary_positive_rpnz" modules tests docs/dev README.md docs/user
```

Hyväksyttävä lopputila:

1. aktiivisessa koodissa ei ole selittämätöntä EV-primary `rpnz_w <= 0` -ehtoa
2. `ev_primary_positive_rpnz`-nimi ei jää käyttöön, jos raja ei ole enää `> 0`
3. aktiivinen dokumentaatio ei väitä surplus release -ehtoa muodossa `rpnz_w <= 0`
4. archive-osumat voi jättää rauhaan, jos ne ovat selvästi historiallisia

## Testikomennot

Kohdennetut:

```bash
pytest -q tests/unit/test_engine.py -k "ev_primary and rpnz"
pytest -q tests/unit/test_surplus_allocator.py
```

Laajempi sanity:

```bash
pytest -q tests/unit/test_engine.py tests/unit/test_surplus_allocator.py
pytest -q tests/e2e_entity/net_zero_ev_adjustable_load tests/e2e_entity/net_zero_homebattery_adjustable_load
```

Jos e2e-setti on hidas, aja vähintään unit-testit ja ne e2e-skenaariot, joiden odotukset muuttuvat tai joiden EV-primary/home-battery-combo osuu muutettuun polkuun.

## Hyväksymiskriteerit

1. `+4 W`, `+10 W`, `0 W` ja `-1 W` käsitellään EV-primary battery-authorityssa practical-zero-tapauksina.
2. `+11 W` käsitellään aidosti positiivisena RPNZ:nä.
3. `10.0` ei esiinny uutena anonyyminä literaalina engine-logiikassa.
4. `SURPLUS_RELEASE_DEADBAND_W` säilyy surplus allocator -domainissa tai aliasina.
5. `docs/dev/arkkitehtuuri.md` ei enää sisällä aktiivisen surplus-release-säännön stale-muotoa `rpnz_w <= 0`.
6. Kohdennetut unit-testit menevät läpi.
