# HAEO in EMS

Paivays: 2026-06-16

Tama dokumentti kuvaa nykyisen toteutuksen siita, miten HAEO vaikuttaa
`NET_ZERO`-tilassa EMS:n sisalla.

## Nykyinen semantiikka

HAEO ei ole `NET_ZERO`-tilassa suora pakko-ohjaus. Se on strateginen varttikohtainen
suunnitelma, jonka EMS yhdistaa omaan paikalliseen `NET_ZERO`-paattelyyn.

Nykyinen tulkinta:

1. HAEO valitsee vartin combon:
   - `primary`
   - `adjustable_surplus`
2. suuremman HAEO-ennusteen saanut kohde valitaan `primary`-rooliin
3. toinen kohde valitaan `adjustable_surplus`-rooliin
4. HAEO battery toimii akun positiivisen lataustehon ylarajana
5. HAEO EV toimii EV-tehon ylarajana
6. paikallinen `NET_ZERO`, guardit, rampit ja laiterajat voivat edelleen
   pienentaa toteutuvaa ohjausta

## Toteutettu aktivointiehto

HAEO NET_ZERO -plan on aktiivinen vain, kun kaikki seuraavat toteutuvat:

1. `control_profile = HORIZON_BY_HAEO`
2. `goal_profile = NET_ZERO`
3. `guard_profile = NORMAL_LIMITS`
4. `configured_forecast = HAEO`
5. `effective_forecast = HAEO`
6. HAEO battery- ja EV-data ovat tuoreita

Muussa tapauksessa EMS fallbackaa omaan normaaliin paikalliseen logiikkaansa.

## Toteutettu data- ja paatosketju

### 1. Planner

`modules/ems_core/integrations/haeo_net_zero_plan.py`

Planner tuottaa:

- `primary_device_id`
- `adjustable_device_id`
- `device_limits_w`
- `battery_limit_w`
- `ev_limit_w`
- `ev_limit_a`
- `quarter_key`
- `changed`

Oleellinen huomio:

- `device_limits_w` on nyt suunnitelman kanoninen tehorajarakenne
- `ev_limit_a` on edelleen mukana compatibility- ja trace-kayttoon

### 2. Policy engine

`ems_policy_engine.py`

Policy engine:

1. lukee HAEO:n
2. muodostaa `HaeoNetZeroPlan`-olion
3. syottaa sen `compute_net_zero_engine_outputs()`-funktiolle
4. julkaisee trace-attribuutit

### 3. NET_ZERO engine

`modules/ems_core/net_zero/engine.py`

Engine käyttää HAEO-plania seuraavasti:

1. jos plan on aktiivinen, combo otetaan planista eika config-helper-arvoista
2. akun positiivinen tavoite clampataan `battery_limit_w`-arvoon
3. EV:n tehotavoite clampataan `ev_limit_w`-arvoon
4. writerille meneva kanoninen EV device-policy sisaltaa `target_w`-arvon

Tarkeä nykytila:

- EV:n production contract writer-rajaan on wattipohjainen
- `current_a` on edelleen trace-/compatibility-mirror
- writer tekee W -> A -muunnoksen adapteritasolla

## Combo-valinta

Nykyinen toteutettu logiikka:

1. jos battery-ennuste > EV-ennuste -> `primary = HOME_BATTERY`
2. jos EV-ennuste > battery-ennuste -> `primary = EV_CHARGER`
3. tasatilanteessa pidetaan edellinen primary, jos se on tiedossa
4. ilman aiempaa primarya tasatilanne fallbackaa `HOME_BATTERY`-painotteisesti

Esimerkki:

1. battery `2 kW`
2. EV `5 kW`
3. `primary = EV_CHARGER`
4. `adjustable_surplus = HOME_BATTERY`
5. EV:n HAEO-raja = `5 kW`
6. akun HAEO-raja = `2 kW`

## Combo-change hygiene

Jos vartin vaihtuessa combo vaihtuu ja vanhoja surplus-tiloja on aktiivisena,
EMS tekee eksplisiittisen siivouksen.

Toteutettu ehto:

1. HAEO plan on aktiivinen
2. `changed = True`
3. jokin vanha surplus-tila on aktiivinen

Toteutettu seuraus:

1. dispatch-paatos on `CLEAR_ALL`
2. `surplus_freeze_until_ts` asetetaan
3. traceen tulee `surplus_state_clear_reason = HAEO_COMBO_CHANGED`
4. dispatch state applier tyhjentaa aktiiviset surplus-laitteet

## EV:n W/A-vastuuraja

Tama kohta on muuttunut aiemmasta suunnitelmasta.

Nykyinen toteutunut malli:

1. core paattelee EV:n tavoitetta watteina
2. HAEO clampaa EV:ta watteina (`ev_limit_w`)
3. device-policy kuljettaa writerille kanonisesti `target_w`-arvon
4. writer muuntaa `target_w` -> selector `current_a`
5. `current_a` julkaistaan edelleen trace-/compatibility-kayttoon

Tama tarkoittaa, etta dokumentaatiota ei pidä enää lukea niin, että
`ev_limit_a` olisi EV:n ensisijainen tuotantokontrakti. Se on nyt
adapteri-/peilikentta, ei core-sopimuksen ydin.

## Diagnostiikka

Keskeiset trace-kentat:

1. `haeo_nz_plan_active`
2. `haeo_nz_quarter_key`
3. `haeo_nz_combo_changed`
4. `haeo_nz_primary_device_id`
5. `haeo_nz_adjustable_device_id`
6. `haeo_nz_device_limits_w`
7. `haeo_nz_battery_limit_w`
8. `haeo_nz_ev_limit_w`
9. `haeo_nz_ev_limit_a`
10. `surplus_state_clear_reason`
11. `device_policies`
12. `ev_target_w`

Tarkeä tulkinta:

- `haeo_nz_ev_limit_a` on edelleen hyodyllinen diagnostiikassa
- writerin kanoninen syote on silti `device_policies[].target_w`

## Testattu nykytila

Viimeisin varmennettu tila tassa tyopuussa:

- `python3 -m pytest -q tests` -> `207 passed, 1 xfailed`

Keskeiset testialueet:

1. `tests/unit/test_haeo_net_zero_plan.py`
2. `tests/unit/test_engine.py`
3. `tests/unit/test_writer_semantics.py`
4. `tests/e2e_entity/haeo_02_net_zero_homebattery_primary_ev_adjustable/`

## Jäljellä oleva jatkokehitys

Toteutus ei ole viela lopullinen kaikilta osin. Jäljellä on edelleen ainakin:

1. plannerin ja engine-tracen `current_a`-mirrorien mahdollinen kaventaminen
2. mahdollinen `ev_limit_w`-painotteisempi trace-siivous, jos `ev_limit_a`
   halutaan myohemmin puhtaasti adapteritasolle
3. laajempi device-generic abstrahointi, jos saman mallin piiriin tulee uusia
   ohjattavia laitteita

## Yhteenveto

Nykyinen HAEO + NET_ZERO -toteutus tekee taman:

1. valitsee vartin combon EMS:n sisalla
2. käyttää HAEO-tehoja wattipohjaisina ylarajoina
3. pitaa paikallisen `NET_ZERO`-logiikan edelleen ensisijaisena
4. tekee combo-vaihdossa eksplisiittisen surplus-state-hygienian
5. syottaa writerille EV:n kanonisena ohjausarvona `target_w`-tehon
