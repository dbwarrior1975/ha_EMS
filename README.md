# Home Assistant EMS

Tama repositorio sisaltaa Home Assistant / Pyscript -pohjaisen EMS-ohjauksen, jonka paatarkoitus on ohjata akkua, EV-laturia ja kahta relekuormaa eri energiatavoitteiden mukaan.

Nykyiset tuetut goal-profiilit ovat:

1. `NET_ZERO`
2. `MAX_EXPORT`
3. `CHEAP_GRID_CHARGE`

Tuetut control-profiilit ovat:

1. `MANUAL`
2. `MANUAL_SAFE`
3. `AUTOMATIC`
4. `HORIZON_BY_HAEO`

Tuetut forecast-profiilit ovat:

1. `NONE`
2. `HAEO`

## Paaosat

Top-level tuotantoketju koostuu kolmesta paakomponentista:

1. `ems_policy_engine.py`
2. `ems_dispatch_state_applier.py`
3. `ems_actuator_writers.py`

Vastuut lyhyesti:

1. policy engine laskee akun, EV:n ja releiden policy-ulostulot
2. dispatch state applier muuntaa surplus-dispatch-paatokset sisaisiksi dispatch state-tiloiksi
3. actuator writer loop kirjoittaa lopulliset ohjaukset Home Assistantin aktuaattoreille

Lisadokumentaatio:

1. `arkkitehtuuri.md`
2. `operointi.md`
3. `testausautomaatio.md`
4. `tilakaavio.md`
5. `business_logic_guide.md`

## Nopeat suunnistusdokumentit

Kahdelle katselmoinneissa toistuvalle tarpeelle on omat dokumentit:

1. `tilakaavio.md` kokoaa yhteen guard-tilojen ja surplus-dispatch-statejen siirtymalogiikan.
2. `business_logic_guide.md` kuvaa EMS:n energiastrategian kayttajan nakokulmasta.

## Tuetut semantiikat

### `NET_ZERO`

Paikallinen quarter-balancing -tila.

1. akulle lasketaan net-zero-target
2. surplus-policy aktivoi kohteita prioriteettien mukaan (`ADJUSTABLE`, `RELAY1`, `RELAY2`)
3. `ADJUSTABLE` voi olla EV-laturi tai kotiakku konfiguraation mukaan
4. EV voi menna low-PV-tilanteessa `hard_off`-polkuun nykyisen policy-attribuutin kautta

Surplus-policy voi aktivoitua vain, kun kaikki seuraavat ehdot tayttyvat:

1. `control_profile = AUTOMATIC`
2. `goal_profile = NET_ZERO`
3. `guard_profile = NORMAL_LIMITS`
4. effective forecast on `NONE`

### `MAX_EXPORT`

Export-first -tila.

1. akun paikallinen fallback on `-4000 W`
2. EV policy on `0`
3. EV writer kayttaa `hard_off`-semantiikkaa
4. releet ovat pois paalta

### `CHEAP_GRID_CHARGE`

Latauspainotteinen tila.

1. akun paikallinen fallback on `100 W`
2. EV oletuksena `ev_max_current_a`
3. HAEO voi syottaa battery- ja EV-targetteja, jos forecast on tuore
4. releet ovat pois paalta

HAEO:n rooli on nykykoodissa rajattu:

1. HAEO voi vaikuttaa akkutargettiin `MAX_EXPORT`- ja `CHEAP_GRID_CHARGE`-tiloissa
2. HAEO voi vaikuttaa EV-targettiin `CHEAP_GRID_CHARGE`-tilassa
3. HAEO voi `HORIZON_BY_HAEO + NET_ZERO` -tilassa valita EMS:n sisaisen adjustable-combon ja tehorajat
4. HAEO on tehokkaasti kaytossa vain, jos forecast on konfiguroitu ja freshness-lahteet ovat tuoreita

### HAEO + `NET_ZERO`: EMS:n sisainen plan

`NET_ZERO`-tilassa HAEO:a ei tulkita sitovana takuutehona. Se toimii strategisena varttikohtaisena toiveena, jonka EMS muuntaa sisaiseksi HAEO NET_ZERO -planiksi.

EMS:n sisainen HAEO NET_ZERO -plan aktivoituu, kun:

1. EMS ajetaan tilassa `control_profile = HORIZON_BY_HAEO`
2. EMS ajetaan tilassa `goal_profile = NET_ZERO`
3. HAEO on konfiguroitu joko `forecast_profile = HAEO` -arvolla tai `HORIZON_BY_HAEO`-control-profiilin kautta
4. HAEO battery- ja EV-freshness-lahteet ovat tuoreita
5. guard on `NORMAL_LIMITS`

Tassa tilassa EMS laskee joka policy-kierroksella nykyisen vartin HAEO-planin:

1. suuremman HAEO-tehon saanut kohde asetetaan `primary`-rooliin
2. toinen kohde asetetaan `adjustable_surplus`-rooliin
3. HAEO battery-teho muutetaan akun positiivisen lataustargetin ylarajaksi
4. HAEO EV-teho muutetaan EV-current-ylarajaksi
5. normaali `NET_ZERO` surplus-policy saa toimia, vaikka `effective_forecast = HAEO`

Varttikohtainen semantiikka:

1. HAEO:n ennuste on toiveellinen jakauma surplusille, ei takuuteho
2. suurempi HAEO-teho voidaan tulkita korkeamman prioriteetin merkiksi, jos HAEO:lla oletetaan olevan riittava taustadata
3. EMS:n sisainen plan ohittaa runtime-laskennassa `adjustable_primary_load`- ja `adjustable_surplus_load`-helperien combon
4. EMS ei kirjoita combo-helperien arvoja takaisin Home Assistantiin
5. EMS toteuttaa valintaa vain silta osin kuin hetkellinen surplus, guardit, rampit ja laiterajat sallivat

Esimerkki:

1. HAEO ennustaa EV:lle `5 kW` ja akulle `2 kW`
2. EMS:n sisainen HAEO-plan asettaa `primary = EV_CHARGER`
3. EMS:n sisainen HAEO-plan asettaa `adjustable_surplus = HOME_BATTERY`
4. EMS yrittaa kayttaa surplusia taman prioriteetin mukaan, mutta pitaa edelleen `NET_ZERO`-tavoitteen ja turvarajat ensisijaisina

Jos halutaan pitaa HAEO-combo-valinta kokonaan Home Assistant -automaation puolella, vaihtoehtoinen malli on ajaa EMS tilassa `AUTOMATIC + NET_ZERO + forecast_profile = NONE` ja kirjoittaa combo-helperit HA-automaatiosta. Talloin EMS:n nakokulmasta `effective_forecast` jaa arvoon `NONE`.

Nykyinen ensitoteutus kattaa EMS-sisaisen combon valinnan, HAEO-tehorajat ja combo-vaihdon surplus-state-hygienian. Jos combo vaihtuu vanhojen surplus-statejen ollessa aktiivisia, policy tuottaa `CLEAR_ALL`, asettaa lyhyen freeze-jakson ja raportoi syyn `surplus_state_clear_reason = HAEO_COMBO_CHANGED`.

## Tarkeat entiteetit

README kuvaa EMS:n kayttorajapinnan ensisijaisesti EMS-avaimilla.
Home Assistant -entity_id-mappaus loytyy tiedostosta `modules/ems_adapter/entity_map.py`.

Nopea mappausperiaate:

1. dokumentaatio ja operointi = EMS-avaimet
2. runtime-integraatio = entity_mapin HA entity_id:t

Keskeiset profiiliavaimet (EMS):

1. `control_profile`
2. `goal_profile`
3. `forecast_profile`
4. `guard_profile`

Keskeiset mittausavaimet (EMS):

1. `soc`
2. `min_cell_voltage_v`
3. `battery_heartbeat`
4. `grid_power_w`
5. `current_battery_sp`
6. `hourly_energy_balance`
7. `charger_control`
8. `charger_current`
9. `required_power_consumption_kw`
10. `rpnz_w`
11. `pv_power_kw`

Keskeiset config-avaimet (EMS):

1. `deadband_w`
2. `ramp_max_w`
3. `strict_limits_max_w`
4. `max_battery_discharge_w`
5. `max_solar_charge_w`
6. `battery_protect_soc`
7. `battery_protect_soc_recovery_margin`
8. `battery_protect_min_cell_voltage_v`
9. `battery_protect_charge_floor_w`
10. `ev_min_current_a`
11. `ev_max_current_a`
12. `ev_charger_phases`
13. `ev_force_current_a`
14. `ev_hard_off_pv_threshold_kw`
15. `ev_hard_off_low_pv_cycles`
16. `ev_hard_off_release_cycles`
17. `ev_current_step_a`
18. `nz_battery_floor_default_w`
19. `nz_battery_floor_ev_active_w`
20. `adjustable_surplus_load`
21. `adjustable_primary_load`
22. `adjustable_surplus_activation`
23. `adjustable_surplus_load_priority`
24. `relay1_power_kw`
25. `relay2_power_kw`
26. `relay1_priority`
27. `relay2_priority`
28. `ev_priority`
29. `surplus_freeze_s`
30. `haeo_stale_timeout_s`

Keskeiset surplus-state-avaimet (EMS):

1. `surplus_freeze_until`
2. `surplus_adjustable_active`
3. `surplus_r1_active`
4. `surplus_r2_active`

Keskeiset releiden override- ja sallinta-avaimet (EMS):

1. `relay1_surplus_allowed`
2. `relay2_surplus_allowed`
3. `relay1_force_on`
4. `relay2_force_on`

Keskeiset HAEO-avaimet (EMS):

1. `haeo_battery_power_active`
2. `haeo_ev_battery_power_active`
3. `haeo_battery_active_power_fresh_source`
4. `haeo_ev_active_power_fresh_source`

HAEO freshness arvioidaan seka battery- etta EV-freshness-lahteiden iasta. Molempien tulee olla alle `haeo_stale_timeout_s`, jotta effective forecast voi olla `HAEO`.

Keskeiset policy-ulostuloavaimet (EMS):

1. `policy_battery_target_w`
2. `policy_ev_current_a`
3. `policy_relay1_command`
4. `policy_relay2_command`
5. `policy_decision_trace`
6. `surplus_policy_active_pys`
7. `surplus_next_target_pys`
8. `surplus_next_threshold_pys`
9. `surplus_release_candidate_pys`
10. `surplus_explanation_pys`
11. `surplus_dispatch_decision_pys`

Keskeiset actuator-avaimet (EMS):

1. `actuator_battery_setpoint_w`
2. `actuator_ev_enabled`
3. `actuator_ev_current_a`
4. `actuator_relay1`
5. `actuator_relay2`

Adjustable-combo: suositus ja runtime-oletukset

Suositus uudelle kayttoonotolle:

1. aseta aina eksplisiittisesti:
	- `adjustable_surplus_load`
	- `adjustable_primary_load`
2. kayta ristiinkytkettya kombinaatiota
3. suositeltu oletus:
	- `adjustable_surplus_load = EV_CHARGER`
	- `adjustable_primary_load = HOME_BATTERY`

Tuetut kombinaatiot:

1. `adjustable_primary_load = HOME_BATTERY` ja `adjustable_surplus_load = EV_CHARGER`
2. `adjustable_primary_load = EV_CHARGER` ja `adjustable_surplus_load = HOME_BATTERY`

Nykyinen runtime-yhteensopivuus:

1. jos `adjustable_primary_load` puuttuu/tyhja, runtime kayttaa legacy-oletusta (`implicit_legacy_default`), jossa primary asetetaan samaksi kuin `adjustable_surplus_load`
2. trace raportoi taman syylla `primary_surplus_combo_reason = implicit_legacy_default`
3. tata ei suositella uudessa kayttoonotossa

### NET_ZERO floor-semanttiikka

1. `nz_battery_floor_default_w` on akun yleinen minimi-floor.
2. Kun `adjustable_primary_load = EV_CHARGER`, akun floor tulee arvosta `nz_battery_floor_ev_active_w`.
3. EV-primary-polussa `nz_battery_floor_ev_active_w` korvaa default-floorin.

## Guardit ja turvallisuuskayttaytyminen

Tuetut guard-profiilit:

1. `NORMAL_LIMITS`
2. `STRICT_LIMITS`
3. `BATTERY_PROTECT`
4. `DEGRADED`

Tarkeat huomiot:

1. `DEGRADED` aktivoituu stale/invalid battery inverter- tai SOC-datasta
2. `BATTERY_PROTECT` estaa haitallisen akun purun
3. `STRICT_LIMITS` on kayttajan pakottama tila

Nykyinen `DEGRADED`-kayttaytyminen:

1. akun policy clampataan `0`:aan
2. EV policy menee `-1`:een
3. relepolicyt menevat `-1`:een
4. surplus-stateit voivat clearantua
5. writer skiptaa olemassa olevat EV- ja relay-actuatorit, jos policy on `-1`

Tama kohta on syyta ymmartaa ennen tuotantokayttoa, koska `DEGRADED` ei nykysemantiikassa pakota kaikkia jo paalla olevia aktuaattoreita pois paalta.

## Testaus

Projektissa on yksikko-, scenario-, smoke- ja contract-testeja.

Pytest-markerit:

1. `unit`
2. `scenario`
3. `smoke`

Huomio contract-testeista:

1. `contract` ei ole erillinen marker `pytest.ini`:ssa
2. contract-testit ovat kansiossa `tests/contract/` (esim. `tests/contract/test_entity_map_contract.py`)
3. aja contract-testit suoraan polulla tai `-k contract`-suodatuksella

Projektin testikomento:

```bash
pytest -q tests
```



## Kayttoonotto

Tama repositorio ei sisalla koko Home Assistant -ympariston konfiguraatiota, vaan EMS olettaa etta vaaditut entityt ovat jo olemassa Home Assistantissa.

Ennen kayttoonottoa varmista ainakin:

1. kaikki `entity_map.py`-mappauksen vaatimukset on provisioitu
2. Pyscript on saatavilla ja top-level scriptit voidaan suorittaa
3. goal-, control-, forecast- ja guard-profiilien arvot vastaavat projektin tukemia tiloja
4. HAEO forecast- ja freshness-entiteetit ovat olemassa, jos forecast-kayttoa halutaan
5. diagnostiikkaentiteetit ovat seurattavissa Home Assistantissa

Suositeltu ensikayttoonottojarjestys:

1. varmista mittausentiteetit
2. varmista config-entiteetit ja oletusarvot
3. kaynnista policy engine
4. kaynnista dispatch state applier
5. kaynnista actuator writer loop
6. seuraa trace-entiteetteja ennen kuin luotat aktuaattorikirjoituksiin

## Diagnostiikka

Tarkeimmat seurattavat entiteetit:

1. `sensor.ems_policy_decision_trace_pyscript`
2. `sensor.ems_dispatch_state_applier_trace`
3. `sensor.ems_actuator_writer_trace`

Erityisen hyodyllisia attribuutteja:

1. `guard`
2. `guard_reason`
3. `dominant_limitation`
4. `effective_forecast`
5. `battery_write_enabled`
6. `surplus_dispatch_decision`
7. `ev_policy_mode`

## Tunnetut rajoitteet

1. EMS tukee nyt kovakoodatusti akkua, EV:ta ja kahta relekuormaa
2. `DEGRADED` ei pakota kaikkia jo paalla olevia aktuaattoreita pois paalta
3. goal-switchauksen automatiikkaa ei ole dokumentoitu taman repon sisalla
4. projekti ei sisalla valmista Home Assistant YAML -kokoonpanoa

## Rollback / disable

Jos EMS:n vaikutus halutaan poistaa nopeasti:

1. pysayta tai disabloi top-level komponentit
2. vaihda `control_profile` manuaalitilaan
3. aseta akku, EV ja releet haluttuihin turvallisiin manuaaliasetuksiin Home Assistantista

Jos tulevaisuudessa tarvitaan yksi eksplisiittinen safe-off-kayttotila, se kannattaa toteuttaa erillisena operointitilana eika goal-profiilina.
