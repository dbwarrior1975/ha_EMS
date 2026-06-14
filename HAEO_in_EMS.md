# HAEO in EMS: NET_ZERO combo and power planning

Tama dokumentti kuvaa suunnitelman, jossa `NET_ZERO`-tilan HAEO-logiikka toteutetaan EMS:n sisalla. Tavoite on, etta EMS valitsee vartin vaihtuessa adjustable-combon ja tuo HAEO-ennusteen mukaiset tehot EMS:n kayttoon ilman erillista Home Assistant -automaatiota.

Status: ensimmainen toteutus on valmis. EMS laskee nyt HAEO NET_ZERO -planin, valitsee combon sisaisesti, sallii surplus-policyn aktiivisessa HAEO NET_ZERO -planissa, kayttaa HAEO battery/EV -tehoja ylarajoina ja tekee combo-vaihdossa eksplisiittisen surplus-state-hygienian.

## Nykytila

Nykykoodissa HAEO luetaan `ems_policy_engine.py`-tiedoston `read_haeo()`-funktiossa.

Nykyinen semantiikka:

1. `configured_forecast()` tekee HAEO:sta konfiguroidun forecastin, jos `forecast_profile = HAEO` tai `control_profile = HORIZON_BY_HAEO`
2. `effective_forecast()` palauttaa `HAEO`, jos forecast on konfiguroitu ja freshness-lahteet ovat tuoreita
3. `CHEAP_GRID_CHARGE` voi kayttaa HAEO battery- ja EV-targetteja suoraan
4. `MAX_EXPORT` voi kayttaa HAEO battery-targettia
5. `NET_ZERO` ei kayta HAEO:a suoraan targettien laskentaan
6. `net_zero_surplus_policy_active()` sallii surplus-policyn vain, kun `effective_forecast = NONE`

Tasta seuraa, etta nykyisessa `NET_ZERO`-tilassa `effective_forecast = HAEO` on lahinna diagnostiikkaa. Se ei viela valitse comboa, ei aseta HAEO-tehoja rajoitteiksi, ja se jopa estaa normaalin surplus-policyn aktivoitumisen.

## Tavoitesemantiikka

Uuden EMS-sisaisen mallin semantiikka:

1. HAEO:n varttiennuste on strateginen toive surplusin jakaumasta
2. EMS tarkistaa vartin vaihtuessa tuoreen HAEO-ennusteen
3. suuremman HAEO-tehon saanut kohde valitaan `primary`-rooliin
4. toinen kohde valitaan `adjustable_surplus`-rooliin
5. HAEO:n ennustetehot tuodaan EMS:n kayttoon kyseisen vartin ohjausrajoitteiksi
6. EMS toteuttaa toivetta vain hetkellisen surplusin, guardien, ramppien ja laiterajojen puitteissa
7. `NET_ZERO` pysyy ensisijaisena tavoitteena

Esimerkki:

1. HAEO battery `2 kW`
2. HAEO EV `5 kW`
3. EMS valitsee `primary = EV_CHARGER`
4. EMS valitsee `adjustable_surplus = HOME_BATTERY`
5. EV:n HAEO-rajoite on noin `5 kW`
6. akun HAEO-rajoite on noin `2 kW`

Vastakkainen esimerkki:

1. HAEO battery `3 kW`
2. HAEO EV `1 kW`
3. EMS valitsee `primary = HOME_BATTERY`
4. EMS valitsee `adjustable_surplus = EV_CHARGER`
5. akun HAEO-rajoite on noin `3 kW`
6. EV:n HAEO-rajoite on noin `1 kW`

## Ehdotettu kayttoehto

EMS-sisainen HAEO-NET_ZERO-combo aktivoituu vain, kun kaikki ehdot tayttyvat:

1. `control_profile = HORIZON_BY_HAEO`
2. `goal_profile = NET_ZERO`
3. `guard_profile = NORMAL_LIMITS`
4. `configured_forecast = HAEO`
5. `effective_forecast = HAEO`
6. battery- ja EV-ennusteet ovat luettavissa

Jos jokin ehto ei tayty, EMS palaa nykyiseen paikalliseen `NET_ZERO`-semantiikkaan.

Tama erottaa uuden toimintatilan nykyisesta `AUTOMATIC + NET_ZERO + forecast_profile = NONE` -polusta.

## Tarvittavat core-muutokset

### 1. Uusi HAEO planning -malli

Lisataan domain-malleihin uusi dataclass esimerkiksi `HaeoNetZeroPlan`.

Ehdotettu sisalto:

```python
@dataclass(frozen=True)
class HaeoNetZeroPlan:
    active: bool
    quarter_key: str
    primary_load: str
    adjustable_surplus_load: str
    battery_limit_w: int
    ev_limit_w: int
    ev_limit_a: int
    reason: str
    changed: bool = False
```

Selitteet:

1. `active`: onko HAEO-NET_ZERO-plan kaytossa talla kierroksella
2. `quarter_key`: vartin tunniste, esimerkiksi `2026-06-14T12:15`
3. `primary_load`: `EV_CHARGER` tai `HOME_BATTERY`
4. `adjustable_surplus_load`: vastakkainen kohde
5. `battery_limit_w`: HAEO battery-kW muunnettuna watteihin ja clampattuna
6. `ev_limit_w`: HAEO EV-kW muunnettuna watteihin ja clampattuna
7. `ev_limit_a`: EV-tehosta johdettu selector-current
8. `reason`: diagnostiikka
9. `changed`: vaihtuiko vartti tai combo edellisesta

### 2. Uusi planning-funktio

Lisataan uusi moduuli esimerkiksi:

```text
modules/ems_core/integrations/haeo_net_zero_plan.py
```

Puhdas core-funktio:

```python
def compute_haeo_net_zero_plan(profiles, cfg, haeo, now_ts, previous_quarter_key=None, previous_primary=None):
    ...
```

Vastuut:

1. tarkista, onko HAEO-NET_ZERO-plan aktiivinen
2. muodosta nykyinen varttiavain
3. muunna HAEO battery- ja EV-kW watteihin
4. clampaa battery `0 ... max_solar_charge_w`
5. clampaa EV `0 ... ev_max_current_a * phases * 230`
6. muunna EV-teho selector-currentiksi `ev_kw_to_selector_current_a()`-funktiolla
7. valitse combo suuremman HAEO-tehon mukaan
8. kasittele tasatilanne deterministisesti
9. palauta tieto, muuttuiko vartti tai combo

Tasatilannesuositus:

1. jos battery ja EV ovat yhtasuuret, pida edellinen primary jos se on tiedossa
2. jos edellista ei ole, kayta eksplisiittista oletusta `HOME_BATTERY`
3. raportoi syy traceen, esimerkiksi `tie_keep_previous` tai `tie_default_home_battery`

### 3. Vartin vaihteen tunnistus

EMS policy loop ajetaan nykyisin 30 sekunnin valein. Vartin vaihteen logiikka voidaan toteuttaa puhtaasti laskemalla `quarter_key` nykyisesta ajasta.

Ehdotettu kvarttiavain:

```python
quarter_start_ts = int(now_ts // 900) * 900
quarter_key = datetime.fromtimestamp(quarter_start_ts).strftime('%Y-%m-%dT%H:%M')
```

EMS ei tarvitse erillista ajastinta vartin vaihteelle, jos policy loop:

1. laskee joka kierroksella nykyisen `quarter_key`-arvon
2. vertaa sita edelliseen trace-attribuuttiin
3. tekee combon uudelleen, jos `quarter_key` vaihtuu

Tama sopii nykyiseen Pyscript-looppiin.

### 4. Edellisen HAEO-planin muistaminen

Edellinen tila voidaan lukea `policy_decision_trace`-attribuuteista:

1. `haeo_nz_quarter_key`
2. `haeo_nz_primary_load`
3. `haeo_nz_adjustable_surplus_load`
4. `haeo_nz_battery_limit_w`
5. `haeo_nz_ev_limit_w`
6. `haeo_nz_ev_limit_a`

Nain ei tarvita uutta Home Assistant helper-entiteettia pelkan muistin takia.

Jos halutaan operoitavampi ratkaisu, voidaan myohemmin lisata erilliset diagnostiikkasensorit. Ensivaiheessa trace-attribuutit riittavat.

## Muutokset policy engineen

### 1. `read_haeo()` saa jaada ennallaan

Nykyinen `read_haeo()` lukee:

1. HAEO battery forecast
2. HAEO EV forecast
3. freshness-lahteet
4. `configured_forecast`
5. `effective_forecast`

Tama riittaa uuden planin syotteeksi.

### 2. `ems_policy_engine_loop()` lukee edellisen planin

Ennen `compute_net_zero_engine_outputs()`-kutsua luetaan edelliset HAEO-plan attribuutit:

1. `previous_haeo_nz_quarter_key`
2. `previous_haeo_nz_primary_load`

Naista muodostetaan uusi `HaeoNetZeroPlan`.

### 3. `compute_net_zero_engine_outputs()` saa uuden parametrin

Ehdotettu uusi optioparametri:

```python
haeo_nz_plan=None
```

Core engine kayttaa plania vain, jos:

1. `haeo_nz_plan is not None`
2. `haeo_nz_plan.active is True`
3. `profiles.goal == NET_ZERO`
4. `profiles.control == HORIZON_BY_HAEO`
5. `profiles.guard == NORMAL_LIMITS`

## Muutokset NET_ZERO-laskentaan

### 1. Combo ei tule config-helperista aktiivisessa HAEO-planissa

Nykyisin combo johdetaan `cfg.adjustable_primary_load`- ja `cfg.adjustable_surplus_load`-arvoista.

Uudessa HAEO-NET_ZERO-polussa:

1. jos `haeo_nz_plan.active`, kayta `haeo_nz_plan.primary_load`
2. jos `haeo_nz_plan.active`, kayta `haeo_nz_plan.adjustable_surplus_load`
3. muuten kayta nykyista config-helper semantiikkaa

Traceen lisataan:

1. `primary_surplus_combo_source = HAEO_NET_ZERO_PLAN` tai `CONFIG`
2. `haeo_nz_primary_load`
3. `haeo_nz_adjustable_surplus_load`

### 2. Surplus-policy aktiiviseksi HAEO-NET_ZERO-polussa

Nykyinen ehto estaa surplus-policyn, jos `effective_forecast = HAEO`.

Tarvittava muutos:

```python
def net_zero_surplus_policy_active(profiles, effective_fc, haeo_nz_plan_active=False):
    return (
        profiles.control == ControlProfile.AUTOMATIC
        and profiles.goal == GoalProfile.NET_ZERO
        and profiles.guard == GuardProfile.NORMAL_LIMITS
        and effective_fc == ForecastProfile.NONE
    ) or (
        profiles.control == ControlProfile.HORIZON_BY_HAEO
        and profiles.goal == GoalProfile.NET_ZERO
        and profiles.guard == GuardProfile.NORMAL_LIMITS
        and haeo_nz_plan_active
    )
```

Talla erotetaan:

1. nykyinen paikallinen `AUTOMATIC + NET_ZERO + NONE`
2. uusi `HORIZON_BY_HAEO + NET_ZERO + HAEO plan`

### 3. HAEO-tehot rajoitteiksi

HAEO-tehoja ei tule tulkita takuukaskyiksi. Ne ovat ylarajoja tai tavoite-enveloppeja.

Ehdotettu tulkinta:

1. primary EV: EV:n jatkuva primary-polku saa maksimiksi `haeo_nz_plan.ev_limit_a`
2. adjustable EV: surplus-aktivointi saa EV:n kayttamaan enintaan `haeo_nz_plan.ev_limit_a`
3. primary battery: akun net-zero target clampataan ylarajalla `haeo_nz_plan.battery_limit_w`
4. adjustable battery: `adjustable_surplus_activation`-tyyppinen aktivoitu battery target clampataan arvoon `haeo_nz_plan.battery_limit_w`

Tarkeaa:

1. guardit saavat edelleen leikata targetteja
2. battery writerin ramp saa edelleen hidastaa toteumaa
3. EV selector quantization saa edelleen pyoristaa virran sallittuihin arvoihin
4. jos HAEO-teho on alle laitteen minimin, kohde voi kaytannossa jaada pois

### 4. Battery-targetin kasittely

Nykyinen `candidate_sp_net_zero()` tuottaa paikallisen akkutargetin RPNZ:n, gridin, deadbandin ja rampin perusteella.

HAEO-NET_ZERO-polussa ei kannata korvata tata suoraan HAEO:n wattiluvulla, koska se rikkoisi `NET_ZERO`-ajatuksen.

Ehdotettu semantiikka:

1. laske ensin paikallinen net-zero battery target kuten nykyisin
2. jos battery on HAEO-planin primary tai adjustable target, clampaa positiivinen latauspuoli HAEO battery limitiin
3. negatiivinen discharge-polku ja battery-protect guard pysyvat nykyisen logiikan ohjauksessa

Esimerkki:

1. paikallinen laskenta haluaisi akkua `3000 W`
2. HAEO battery limit on `2000 W`
3. lopullinen akun policy target ennen writeria on enintaan `2000 W`

### 5. EV-currentin kasittely

EV:n kohdalla HAEO-teho muutetaan selector-currentiksi.

Ehdotettu semantiikka:

1. `ev_limit_a = ev_kw_to_selector_current_a(haeo.ev_target_kw, cfg.ev_charger_phases, cfg.ev_max_current_a)`
2. jos EV on primary, primary EV -polun current clampataan arvoon `ev_limit_a`
3. jos EV on adjustable, surplus EV -polun current clampataan arvoon `ev_limit_a`
4. jos `ev_limit_a < ev_min_current_a`, EV ei aktivoidu HAEO-planin perusteella

Talla HAEO ei pakota EV:ta paalle, jos ennuste on kaytannossa liian pieni laitteen minimivirralle.

## State hygiene combon vaihtuessa

Kun combo vaihtuu, vanhat surplus-stateit voivat tarkoittaa eri fyysista kuormaa kuin edellisessa vartissa.

Esimerkki:

1. edellinen vartti: `adjustable_surplus = EV_CHARGER`
2. `surplus_adjustable_active = True`
3. uusi vartti: `adjustable_surplus = HOME_BATTERY`
4. sama boolean tarkoittaisi nyt eri kohdetta

Tarvittava muutos:

1. engine laskee `haeo_nz_combo_changed`
2. jos combo vaihtui, policy output tuottaa uuden dispatch-paatoksen `CLEAR_ALL` tai uuden attribuutin `clear_surplus_state_reason = HAEO_COMBO_CHANGED`
3. dispatch state applier tyhjentaa `surplus_adjustable_active`, `surplus_r1_active`, `surplus_r2_active`
4. `surplus_freeze_until` joko tyhjennetaan tai asetetaan lyhyeen uuteen freezeen

Suositus ensivaiheeseen:

1. combo-vaihdossa tee `CLEAR_ALL`
2. aseta `surplus_freeze_until_ts = now_ts + surplus_freeze_s`
3. seuraava policy-kierros saa aktivoida uuden combon puhtaalta pohjalta

Tama voi aiheuttaa korkeintaan yhden policy-kierroksen viiveen, mutta se estaa vaaratulkinnan.

## Diagnostiikka

Lisattavat trace-attribuutit:

1. `haeo_nz_plan_active`
2. `haeo_nz_quarter_key`
3. `haeo_nz_combo_changed`
4. `haeo_nz_primary_load`
5. `haeo_nz_adjustable_surplus_load`
6. `haeo_nz_battery_limit_w`
7. `haeo_nz_ev_limit_w`
8. `haeo_nz_ev_limit_a`
9. `haeo_nz_combo_reason`
10. `primary_surplus_combo_source`
11. `surplus_state_clear_reason`

Lisaksi nykyiset attribuutit sailyvat:

1. `configured_forecast`
2. `effective_forecast`
3. `dominant_limitation`
4. `surplus_dispatch_decision`
5. `ev_policy_mode`

## Entity-muutokset

Minimimuutos ei vaadi uusia ohjaus-helper-entiteetteja.

Nykyiset HAEO-entiteetit riittavat:

1. `haeo_battery_power_active`
2. `haeo_ev_battery_power_active`
3. `haeo_battery_active_power_fresh_source`
4. `haeo_ev_active_power_fresh_source`

Nykyiset combo-helperit jaavat edelleen manuaalista/config-polkua varten:

1. `adjustable_primary_load`
2. `adjustable_surplus_load`
3. `adjustable_surplus_activation`

Uudessa HAEO-NET_ZERO-polussa EMS ei kirjoita naita helper-arvoja, vaan ohittaa ne sisaisella planilla. Talla valtytaan silta, etta EMS alkaisi muuttaa omaa configiaan runtime-paatoksen perusteella.

Mahdolliset uudet diagnostiikkasensorit myohemmin:

1. `sensor.ems_haeo_net_zero_plan`
2. `sensor.ems_haeo_net_zero_primary_load`
3. `sensor.ems_haeo_net_zero_adjustable_load`

Ensivaiheessa trace-attribuutit ovat kuitenkin riittavat.

## Testausautomaatio

EMS-sisainen toteutus kannattaa testata kolmella tasolla.

### Unit-testit

Uusi testitiedosto:

```text
tests/unit/test_haeo_net_zero_plan.py
```

Testit:

1. EV suurempi kuin battery -> `primary = EV_CHARGER`, `adjustable = HOME_BATTERY`
2. battery suurempi kuin EV -> `primary = HOME_BATTERY`, `adjustable = EV_CHARGER`
3. tasatilanne pitaa edellisen primaryn
4. tasatilanne ilman edellista kayttaa oletusta
5. stale forecast -> plan inactive
6. wrong goal -> plan inactive
7. wrong guard -> plan inactive
8. EV kW muunnetaan oikein selector-currentiksi
9. battery kW clampataan `max_solar_charge_w`-rajaan
10. negatiivinen EV ennuste clampataan nollaan

### Engine-testit

Laajennetaan `tests/unit/test_engine.py` tai lisataan uusi:

```text
tests/unit/test_engine_haeo_net_zero.py
```

Testit:

1. `HORIZON_BY_HAEO + NET_ZERO + fresh HAEO` aktivoi surplus-policyn
2. HAEO-plan ohittaa config-helper combon
3. EV-primary polku clampaa virran HAEO EV limit -arvoon
4. battery-primary polku clampaa akun positiivisen targetin HAEO battery limit -arvoon
5. combo change tuottaa `CLEAR_ALL` ja freeze-attribuutin
6. stale HAEO palaa paikalliseen fallbackiin
7. `DEGRADED` estaa HAEO-planin
8. `BATTERY_PROTECT` estaa haitallisen akun purun myos HAEO-planissa

### E2E-testit

Uusi alikansio:

```text
tests/e2e_entity/haeo_03_net_zero_internal_combo_selection/
```

Ehdotetut testit:

1. `test_01_ev_larger_forecast_selects_ev_primary.py`
	- HAEO EV `5 kW`, battery `2 kW`
	- odotus: primary `EV_CHARGER`, adjustable `HOME_BATTERY`
	- odotus: EV current clampataan HAEO EV limitin mukaan
	- odotus: battery positive target clampataan HAEO battery limitin mukaan

2. `test_02_battery_larger_forecast_selects_battery_primary.py`
	- HAEO battery `3 kW`, EV `1 kW`
	- odotus: primary `HOME_BATTERY`, adjustable `EV_CHARGER`
	- odotus: EV ei aktivoidu, jos HAEO EV limit alittaa minimivirran

3. `test_03_quarter_change_clears_old_surplus_state.py`
	- edellinen vartti: adjustable EV aktiivinen
	- uusi vartti: adjustable battery
	- odotus: `CLEAR_ALL`, freeze asetetaan, vanha adjustable-state ei kanna yli fyysisesti eri kuormalle

4. `test_04_stale_forecast_falls_back_to_local_net_zero.py`
	- HAEO configured mutta freshness stale
	- odotus: `effective_forecast = NONE`
	- odotus: paikallinen NET_ZERO toimii nykysemantiikan mukaan

## Toteutusjarjestys

Suositeltu jarjestys:

1. lisaa `HaeoNetZeroPlan` domain-malleihin
2. toteuta puhdas `compute_haeo_net_zero_plan()` unit-testeineen
3. lisaa trace-attribuutit ilman varsinaista ohjausvaikutusta
4. muuta engine kayttamaan planin comboa `NET_ZERO`-tilassa
5. muuta `net_zero_surplus_policy_active()` sallimaan HAEO-NET_ZERO-plan
6. lisaa EV- ja battery-limit clampit
7. lisaa combo-change state hygiene
8. lisaa E2E-tarinat
9. paivita README, operointi ja testausautomaatio dokumentit vastaamaan uutta tuotantosemantiikkaa

## Riskit ja avoimet paatokset

### 1. Onko HAEO-teho ylaraja vai tavoite?

Suositus: tulkitaan ylarajaksi/tavoite-envelopeksi, ei pakottavaksi targetiksi.

Perustelu: `NET_ZERO` tarvitsee edelleen paikallisen mittauksen. Jos HAEO-teho pakotetaan suoraan targetiksi, EMS voi ostaa tai vieda verkkoon vastoin `NET_ZERO`-tavoitetta.

### 2. Mita tehdaan, jos toinen HAEO-teho on nolla?

Suositus:

1. jos EV `0 kW` ja battery positiivinen, battery primary
2. jos battery `0 kW` ja EV positiivinen, EV primary
3. jos molemmat ovat nolla, plan inactive tai local fallback

Suositeltu ensivaihe: molemmat nolla -> plan inactive.

### 3. Miten tasatilanne ratkaistaan?

Suositus:

1. pida edellinen primary saman vartin aikana
2. vartin vaihtuessa pida edellinen primary, jos molemmat ovat edelleen tasan
3. jos edellista ei ole, kayta `HOME_BATTERY`

Tama vahentaa turhaa combon vaihtelua.

### 4. Pitaisiko EMS kirjoittaa combo-helperit?

Suositus: ei.

EMS:n sisainen plan saa ohittaa config-helperit runtime-laskennassa, mutta sen ei kannata kirjoittaa config-helper-arvoja. Muuten runtime-paatos ja kayttajan asetus sekoittuvat.

### 5. Pitaisiko `HORIZON_BY_HAEO` olla ainoa ohjausprofiili talle?

Suositus: kylla ensivaiheessa.

Tama tekee kayttajan intentiosta selkean:

1. `AUTOMATIC + NET_ZERO` = paikallinen NET_ZERO
2. `HORIZON_BY_HAEO + NET_ZERO` = EMS-sisainen HAEO-combo NET_ZERO

## Yhteenveto

EMS-sisainen HAEO-NET_ZERO-toteutus kannattaa rakentaa erilliseksi plan-kerrokseksi, ei nykyisen config-helper combon paalle kirjoittamalla.

Keskeinen arkkitehtuuripaatos:

1. HAEO-plan valitsee vartin strategisen combon ja tehorajat
2. NET_ZERO-engine toteuttaa combon paikallisen surplusin mukaan
3. guardit, rampit ja laiterajat sailyvat vahvempina kuin HAEO
4. combo-vaihdossa surplus-state tyhjennetaan hallitusti
5. koko paatosketju tuodaan traceen ja E2E-testataan
