# HAEO in EMS: NET_ZERO combo and power planning

Tama dokumentti kuvaa nykyisen EMS-sisaisen `HAEO + NET_ZERO` -toteutuksen.

Status: toteutettu ensiversio. EMS laskee HAEO NET_ZERO -planin, valitsee combon sisaisesti, sallii surplus-policyn aktiivisessa HAEO NET_ZERO -planissa, kayttaa HAEO battery/EV -tehoja ylarajoina ja tekee combo-vaihdossa eksplisiittisen surplus-state-hygienian.

## Semantiikka

`NET_ZERO`-tilassa HAEO ei ole sitova takuuteho. HAEO:n varttiennuste on strateginen toive surplusin jakaumasta.

EMS:n tulkinta:

1. suuremman HAEO-tehon saanut kohde valitaan `primary`-rooliin
2. toinen kohde valitaan `adjustable_surplus`-rooliin
3. HAEO battery-teho muuttuu akun positiivisen lataustargetin ylarajaksi
4. HAEO EV-teho muuttuu EV-currentin ylarajaksi
5. `NET_ZERO` pysyy ensisijaisena tavoitteena
6. guardit, rampit, device-limitit ja hetkellinen surplus voivat pienentaa toteumaa

Esimerkki 1:

1. HAEO battery `2 kW`
2. HAEO EV `5 kW`
3. EMS valitsee `primary = EV_CHARGER`
4. EMS valitsee `adjustable_surplus = HOME_BATTERY`
5. EV:n HAEO-rajoite on `5 kW`
6. akun HAEO-rajoite on `2 kW`

Esimerkki 2:

1. HAEO battery `3 kW`
2. HAEO EV `1.5 kW`
3. EMS valitsee `primary = HOME_BATTERY`
4. EMS valitsee `adjustable_surplus = EV_CHARGER`
5. akun HAEO-rajoite on `3 kW`
6. EV:n HAEO-rajoite on `1.5 kW`

## Aktivointiehdot

EMS-sisainen HAEO NET_ZERO -plan on aktiivinen vain, kun kaikki ehdot tayttyvat:

1. `control_profile = HORIZON_BY_HAEO`
2. `goal_profile = NET_ZERO`
3. `guard_profile = NORMAL_LIMITS`
4. `configured_forecast = HAEO`
5. `effective_forecast = HAEO`
6. HAEO battery- ja EV-ennusteet ovat luettavissa

Jos jokin ehto ei tayty, plan on inactive ja EMS kayttaa muuta nykyista semantiikkaa:

1. `AUTOMATIC + NET_ZERO + effective_forecast = NONE` kayttaa paikallista NET_ZERO-politiikkaa
2. stale HAEO pudottaa `effective_forecast`-arvon arvoon `NONE`
3. guardit kuten `BATTERY_PROTECT` ja `DEGRADED` ovat vahvempia kuin HAEO-plan

## Toteutetut moduulit

### Domain model

`modules/ems_core/domain/models.py`

Toteutettu dataclass:

```python
@dataclass(frozen=True)
class HaeoNetZeroPlan:
    active: bool
    quarter_key: str = ''
    primary_load: str = ''
    adjustable_surplus_load: str = ''
    battery_limit_w: int = 0
    ev_limit_w: int = 0
    ev_limit_a: int = 0
    reason: str = ''
    changed: bool = False
```

Kentat:

1. `active`: onko HAEO NET_ZERO -plan kaytossa talla policy-kierroksella
2. `quarter_key`: vartin tunniste, nykyisin epoch-pohjainen 15 minuutin aloitushetki merkkijonona
3. `primary_load`: `EV_CHARGER` tai `HOME_BATTERY`
4. `adjustable_surplus_load`: vastakkainen kohde
5. `battery_limit_w`: HAEO battery-kW watteina ja device-rajaan clampattuna
6. `ev_limit_w`: HAEO EV-kW watteina ja EV device-rajaan clampattuna
7. `ev_limit_a`: EV-tehosta johdettu selector-current
8. `reason`: planin valintaselitys
9. `changed`: vaihtuiko vartti tai primary edelliseen traceen verrattuna

### Planner

`modules/ems_core/integrations/haeo_net_zero_plan.py`

Paa-funktio:

```python
compute_haeo_net_zero_plan(
    profiles,
    cfg,
    haeo,
    now_ts,
    previous_quarter_key='',
    previous_primary_load='',
)
```

Plannerin vastuut:

1. tarkistaa aktivointiehdot
2. laskea 15 minuutin `quarter_key`
3. muuntaa HAEO battery- ja EV-kW-arvot watteihin
4. clampata battery `0 ... max_solar_charge_w`
5. clampata EV `0 ... ev_max_current_a * phases * 230`
6. muuntaa EV-teho selector-currentiksi `ev_kw_to_selector_current_a()`-funktiolla
7. valita combo suuremman HAEO-tehon mukaan
8. kasitella tasatilanne deterministisesti
9. raportoida muuttuiko vartti tai primary

Tasatilanteen semantiikka:

1. jos battery ja EV ovat yhtasuuret, pida edellinen primary jos se on tiedossa
2. jos edellista ei ole, kayta `HOME_BATTERY`
3. syy raportoidaan arvoilla kuten `tie_keep_previous` tai `tie_default_home_battery`

### Policy engine

`ems_policy_engine.py`

Policy loop:

1. lukee HAEO:n `read_haeo()`-funktiolla
2. lukee edellisen `haeo_nz_quarter_key`- ja `haeo_nz_primary_load`-attribuutin `policy_decision_trace`-sensorista
3. laskee uuden `HaeoNetZeroPlan`-olion
4. valittaa planin `compute_net_zero_engine_outputs()`-funktiolle

EMS ei kirjoita `adjustable_primary_load`- tai `adjustable_surplus_load`-helper-arvoja takaisin Home Assistantiin. HAEO-plan ohittaa ne vain runtime-laskennassa.

### NET_ZERO engine

`modules/ems_core/net_zero/engine.py`

Toteutettu kayttaytyminen:

1. jos `haeo_nz_plan.active`, combo otetaan planista eika config-helpereista
2. traceen kirjoitetaan `primary_surplus_combo_source = HAEO_NET_ZERO_PLAN`
3. `net_zero_surplus_policy_active()` sallii surplus-policyn myos aktiivisessa `HORIZON_BY_HAEO + NET_ZERO + HAEO plan` -tilassa
4. battery positive target clampataan `haeo_nz_plan.battery_limit_w`-arvoon
5. EV current clampataan `haeo_nz_plan.ev_limit_a`-arvoon
6. selitteeksi tulee `HAEO net zero plan active`

Tama on tietoinen muutos vanhaan semantiikkaan, jossa `effective_forecast = HAEO` esti `NET_ZERO` surplus-policyn.

## Combo-change hygiene

Combo-vaihdossa vanha `surplus_adjustable_active` voi tarkoittaa eri fyysista kohdetta kuin uudessa combossa.

Esimerkki:

1. edellinen vartti: `adjustable_surplus = EV_CHARGER`
2. `surplus_adjustable_active = True`
3. uusi vartti: `adjustable_surplus = HOME_BATTERY`
4. sama boolean ei saa kantaa yli uuteen fyysiseen merkitykseen

Toteutettu hygiene-ehto:

1. HAEO NET_ZERO -plan on aktiivinen
2. `haeo_nz_plan.changed = True`
3. jokin vanha surplus-state on aktiivinen:
   - `surplus_adjustable_active`
   - `surplus_r1_active`
   - `surplus_r2_active`

Kun ehto tayttyy, engine:

1. tuottaa `surplus_dispatch_decision = CLEAR_ALL`
2. asettaa `surplus_freeze_until_ts = now_ts + surplus_freeze_s`
3. raportoi `surplus_state_clear_reason = HAEO_COMBO_CHANGED`
4. estaa samalla policy-kierroksella EV burnin
5. antaa dispatch state applierin tyhjentaa surplus-stateit

Ensimmainen HAEO-planin muodostuminen ei yksin riita `CLEAR_ALL`-paatokseen, jos vanhoja aktiivisia surplus-stateja ei ole.

## HAEO-tehojen kasittely

HAEO-tehoja ei tulkita pakottaviksi targeteiksi.

Toteutettu tulkinta:

1. `battery_limit_w` on positiivisen akkulatauksen ylaraja
2. `ev_limit_w` on EV-tehoraja watteina
3. `ev_limit_a` on EV writerille sopiva selector-current ylarajana
4. paikallinen `NET_ZERO`-laskenta saa edelleen pienentaa targetteja
5. guardit saavat edelleen leikata targetteja
6. writerin rampit ja EV:n enable/disable-semanttiikka sailyvat voimassa

EV:n ampeerimuunnos tehdaan viela core-polussa funktiolla:

```python
ev_kw_to_selector_current_a(kw, phases, max_a, min_a=4, step_a=4)
```

Tama funktio muodostaa sallitut selector-current-arvot `min_a ... max_a` valilla `step_a`-askeleella ja valitsee HAEO-tehosta lasketulle raakavirralle lahimman sallitun arvon.

Arkkitehtuurisesti on jatkossa arvioitava, kannattaako EV:n ampeerimuunnos siirtaa lahemmaksi writer-/adapter-tasoa ja pitaa core-logiikka nykyista vahvemmin watteina.

## Diagnostiikka

Trace-attribuutit:

1. `configured_forecast`
2. `effective_forecast`
3. `haeo_nz_plan_active`
4. `haeo_nz_quarter_key`
5. `haeo_nz_combo_changed`
6. `haeo_nz_primary_load`
7. `haeo_nz_adjustable_surplus_load`
8. `haeo_nz_battery_limit_w`
9. `haeo_nz_ev_limit_w`
10. `haeo_nz_ev_limit_a`
11. `haeo_nz_combo_reason`
12. `primary_surplus_combo_source`
13. `surplus_state_clear_reason`
14. `surplus_dispatch_decision`
15. `surplus_freeze_until_ts`
16. `ev_policy_mode`

Hyodyllisia arvoja normaalissa HAEO NET_ZERO -tilassa:

1. `primary_surplus_combo_source = HAEO_NET_ZERO_PLAN`
2. `haeo_nz_plan_active = True`
3. `surplus_policy_active = True`
4. `explanation = HAEO net zero plan active`

## Testaus

Toteutettu testikattavuus:

1. `tests/unit/test_haeo_net_zero_plan.py`
2. `tests/unit/test_engine.py`
3. `tests/e2e_entity/haeo_02_net_zero_homebattery_primary_ev_adjustable/`

Keskeiset testatut tapaukset:

1. EV forecast suurempi kuin battery -> `primary = EV_CHARGER`
2. battery forecast suurempi kuin EV -> `primary = HOME_BATTERY`
3. tasatilanne pitaa edellisen primaryn
4. stale forecast -> plan inactive
5. wrong guard -> plan inactive
6. nollaennuste -> plan inactive
7. battery- ja EV-limitit clampataan device-rajoihin
8. `HORIZON_BY_HAEO + NET_ZERO + fresh HAEO` aktivoi surplus-policyn
9. HAEO-plan ohittaa config-helper combon
10. battery target clampataan HAEO battery -rajaan
11. EV current clampataan HAEO EV -rajaan
12. vartin vaihtuessa combo voi vaihtua
13. combo-vaihto vanhan aktiivisen surplus-staten aikana tuottaa `CLEAR_ALL`, freeze-attribuutin ja `HAEO_COMBO_CHANGED`-syyn

Viimeisin koko testiajo tassa tyopuussa:

```bash
pytest -q tests
```

Tulos:

```text
130 passed
```

## Ei toteutettu viela

Seuraavat asiat ovat edelleen mahdollisia jatkokehityksia:

1. EV:n W/A-muunnoksen siirto lahemmaksi writer-/adapter-tasoa
2. yhteismitallisempi `policy_ev_target_w` / `policy_ev_limit_w` -trace ja mahdollinen policy-output
3. erilliset diagnostiikkasensorit kuten `sensor.ems_haeo_net_zero_plan`
4. laajempi yleinen flexible-load-abstraktio, jos akku/EV/releet alkavat jakaa enemman samaa core-semanttiikkaa

## Yhteenveto

Nykyinen toteutus tekee HAEO:sta `NET_ZERO`-tilassa strategisen EMS-sisaisen planin:

1. HAEO valitsee vartin combon ja tehorajat
2. NET_ZERO-engine toteuttaa plania paikallisen surplusin mukaan
3. guardit, rampit ja laiterajat sailyvat vahvempina kuin HAEO
4. combo-vaihdossa vanhat surplus-stateit tyhjennetaan hallitusti
5. koko paatosketju nakyy trace-attribuuteissa ja on E2E-testattu
