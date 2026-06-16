# EMS-operointi

## Tarkoitus

Tama dokumentti kuvaa projektin kayttoa, valvontaa ja vianetsintaa.

## Kanoninen runtime-pinta

Nykyisen tuotantopolun ensisijainen totuus ei ole enaa yksittaisissa
`policy_*`- tai `surplus_*_active`-entiteeteissa, vaan naissa pinoissa:

1. `sensor.ems_policy_decision_trace_pyscript`
2. `sensor.ems_device_policies_pyscript`
3. `sensor.ems_active_surplus_devices`
4. `sensor.ems_previous_device_state`

Kaytannollinen tulkinta:

1. `policy_decision_trace` kertoo miksi EMS paatti niin kuin paatti
2. `device_policies` kertoo mita writerille pyydetaan kanonisessa muodossa
3. `active_surplus_devices` kertoo mitka surplus-kohteet ovat kanonisesti aktiivisia
4. `previous_device_state` kantaa yli syklien erityisesti EV:n edellisen moodin muistia

Poistetut legacy-peilit:

1. `sensor.ems_policy_battery_target_w_pyscript`
2. `sensor.ems_policy_ev_current_a_pyscript`
3. `sensor.ems_policy_relay1_command_pyscript`
4. `sensor.ems_policy_relay2_command_pyscript`
5. `input_boolean.ems_surplus_adjustable_active`
6. `input_boolean.ems_surplus_relay1_active`
7. `input_boolean.ems_surplus_relay2_active`

Jos HA:ssa on viela automaatioita tai dashboardeja, jotka lukevat naita, ne
pitää paivittaa kayttamaan kanonisia entityja.

## Operoinnin ohjauspisteet

Keskeiset profiilientiteetit:

1. `input_select.ems_control_profile`
2. `input_select.ems_goal_profile`
3. `input_select.ems_forecast_profile`
4. `input_select.ems_guard_profile`

Tuetut profiiliarvot:

1. control: `MANUAL`, `MANUAL_SAFE`, `AUTOMATIC`, `HORIZON_BY_HAEO`
2. goal: `NET_ZERO`, `MAX_EXPORT`, `CHEAP_GRID_CHARGE`
3. forecast: `NONE`, `HAEO`
4. guard: `NORMAL_LIMITS`, `STRICT_LIMITS`, `BATTERY_PROTECT`, `DEGRADED`

Keskeiset konfiguraatioentiteetit:

1. `input_number.ems_deadband_w`
2. `input_number.ems_ramp_max_w`
3. `input_number.ems_strict_limits_max_w`
4. `input_number.ems_max_battery_discharge_w`
5. `input_number.ems_max_battery_charge_w`
6. `input_number.ems_battery_protect_soc`
7. `input_number.ems_battery_protect_soc_recovery_margin`
8. `input_number.ems_battery_protect_min_cell_voltage_v`
9. `input_number.ems_ev_min_current_a`
10. `input_number.ems_ev_max_current_a`
11. `input_number.ems_ev_charger_phases`
12. `input_number.ems_ev_force_current_a`
13. `input_number.ems_ev_hard_off_pv_threshold_kw`
14. `input_number.ems_ev_hard_off_low_pv_cycles`
15. `input_number.ems_ev_hard_off_release_cycles`
16. `input_number.ems_ev_current_step_a`
17. `input_number.ems_haeo_stale_timeout_s`
18. `input_number.ems_relay1_power_kw`
19. `input_number.ems_relay2_power_kw`
20. `input_number.ems_nz_battery_floor_default_w`
21. `input_number.ems_nz_battery_floor_ev_active_w`
22. `input_select.ems_adjustable_surplus_load`
23. `input_select.ems_adjustable_primary_load`
24. `input_number.ems_adjustable_surplus_activation_w`
25. `input_number.ems_adjustable_surplus_load_priority`
26. prioriteettientiteetit relay1:lle, relay2:lle ja EV:lle

Floor-semanttiikka NET_ZEROssa:

1. `ems_nz_battery_floor_default_w` on yleinen akun minimi-floor.
2. jos `adjustable_primary_load = EV_CHARGER`, akun floor tulee arvosta `ems_nz_battery_floor_ev_active_w`.
3. EV-primary-polussa `ems_nz_battery_floor_ev_active_w` korvaa default-floorin.

## Kaytossa olevat komponentit

Nykyisen tuotantoketjun jarjestys on:

1. `ems_policy_engine.py`
2. `ems_dispatch_state_applier.py`
3. `ems_actuator_writers.py`

Kaikki kolme komponenttia kaynnistyvat 30 sekunnin periodilla ja osa myos tilamuutoksista.

## Goal-profile-valinta

Nykyinen EMS lukee goal-profiilin entiteetista `input_select.ems_goal_profile`.

## Tarkeimmat seurattavat entiteetit

### Mittaukset

1. `sensor.victron_mqtt_b827eb48c929_system_0_system_dc_battery_soc`
2. `sensor.victron_mqtt_b827eb48c929_battery_1_battery_min_cell_voltage`
3. `sensor.victron_mqtt_b827eb48c929_battery_1_battery_power`
4. `sensor.average_active_power_2`
5. `number.victron_mqtt_b827eb48c929_system_0_system_ac_power_set_point`
6. `sensor.hourly_energy_balance`
7. `switch.charger_control`
8. `number.charger_current_level`
9. `sensor.required_power_consumption`
10. `sensor.ems_calculated_required_power_for_net_zero`
11. `sensor.pv_instant_power_2`

### Releiden override- ja sallintaentiteetit

1. `input_boolean.ems_relay1_enabled_import_zero`
2. `input_boolean.ems_relay2_enabled_import_zero`
3. `input_boolean.ems_relay1_force_on`
4. `input_boolean.ems_relay2_force_on`

### HAEO-entiteetit

1. `sensor.haeo_battery_power_active`
2. `sensor.haeo_ev_battery_power_active`
3. `sensor.battery_active_power`
4. `sensor.ev_akut_active_power`

HAEO on effective vain, jos se on konfiguroitu ja molemmat freshness-lahteet ovat alle `ems_haeo_stale_timeout_s` -rajan.

### Kanoniset policy-ulostulot

1. `sensor.ems_policy_decision_trace_pyscript`
2. `sensor.ems_device_policies_pyscript`
3. `sensor.ems_previous_device_state`

### Kanoniset surplus-tilat

1. `input_datetime.ems_surplus_freeze_until`
2. `sensor.ems_active_surplus_devices`

### Poistetut legacy-peilit

1. `sensor.ems_policy_battery_target_w_pyscript`
2. `sensor.ems_policy_ev_current_a_pyscript`
3. `sensor.ems_policy_relay1_command_pyscript`
4. `sensor.ems_policy_relay2_command_pyscript`
5. `input_boolean.ems_surplus_adjustable_active`
6. `input_boolean.ems_surplus_relay1_active`
7. `input_boolean.ems_surplus_relay2_active`

### Aktuaattorit

1. `number.victron_mqtt_b827eb48c929_system_0_system_ac_power_set_point`
2. `switch.charger_control`
3. `number.charger_current_level`
4. `switch.relay_1_2`
5. `switch.relay_2_2`

### Diagnostiikka

1. `sensor.ems_policy_decision_trace_pyscript`
2. `sensor.ems_actuator_writer_trace`
3. `sensor.ems_dispatch_state_applier_trace`

## Operatiivinen kayttaytyminen profiileittain

### `AUTOMATIC + NET_ZERO`

Tama on koodin perusteella varsinainen paikallinen neljannesbalanssin optimointitila.

Kayttaytyminen:

1. akun setpoint lasketaan `candidate_sp_net_zero()`-funktion kautta
2. surplus policy voi aktivoitua vain, jos guard on `NORMAL_LIMITS` ja effective forecast on `NONE`
3. surplus-kohteiden aktivointi noudattaa prioriteetteja
4. surplus-kohteiden vapautus tapahtuu kanteisjarjestyksessa

### `MAX_EXPORT`

Nykyisen tuotantokoodin policy-tason semantiikka:

1. akun paikallinen fallback-target on `-4000` W, ellei HAEO syota muuta targetia
2. EV policy current on `0`
3. relekomennot ovat `0`

Yllapitajan kannalta taman tilan nykyinen tavoitesemantiikka on dokumentoitava muodossa:

1. EV policy current `0`
2. charger disabled
3. current `0`
4. relays off

Nykyinen writer-koodi tukee tata semantiikkaa `ev_policy_mode=hard_off` -attribuutilla. Tahan liittyva e2e-goal transition -testi odottaa EV off -lopputulosta `MAX_EXPORT`-tilassa.

### `CHEAP_GRID_CHARGE`

Nykyinen kayttaytyminen:

1. akun paikallinen fallback-target on `100` W
2. EV oletuksena `ev_max_current_a`
3. jos `ev_force_current_a > 0`, sita kunnioitetaan
4. jos HAEO on voimassa, EV-current voidaan johtaa HAEO-targetista
5. releet pysyvat pois paalta

### `MANUAL`

Nykyinen kayttaytyminen:

1. akkuun ei kirjoiteta writerissa
2. moottori raportoi `battery_write_enabled=False`
3. EV-virta tulee `ev_force_current_a`:sta, jos se on yli nollan
4. muuten EV skipataan
5. releet seuraavat vain `force_on`-tilaa

### `MANUAL_SAFE`

Nykyinen kayttaytyminen:

1. akkua ei normaalisti muuteta automaattisesti
2. guard voi kuitenkin clampata akun targetia turvalliseen suuntaan
3. writerissa on fallback-logiikka, joka sallii kirjoituksen guard-clamp-testausta varten, jos policy-attribuutti ei ole saatavilla
4. EV kayttaytyy kayttajan nakokulmasta kuten `MANUAL`
5. releet seuraavat `force_on`-tilaa

## Guard-tilojen operatiivinen merkitys

### `BATTERY_PROTECT`

Aktivoituu, jos:

1. SOC alittaa rajan
2. tai min-cell voltage alittaa rajan
3. tai molemmat alittavat rajansa

Operatiivinen vaikutus:

1. akun target clampataan ei-negatiiviseksi
2. purku estetaan kaytannossa
3. palautuminen vaatii seka SOC recovery marginin etta min-cell thresholdin tayttymisen

### `DEGRADED`

Aktivoituu stale/invalid battery inverter- tai SOC-datasta.

Operatiivinen vaikutus:

1. akun target menee arvoon `0`
2. EV strategy palauttaa `-1`
3. relay strategy palauttaa `-1`
4. `dominant_limitation` on `SYSTEM_DEGRADED`
5. dispatch state applier voi clearata aktiiviset surplus-stateit, mutta actuator writer loop skiptaa olemassa olevat EV- ja relay-actuatorit, jos policy on `-1`

### `STRICT_LIMITS`

Tama on kayttajan pakottama guard-tila. EMS ei overridea sita evaluatorissa.

Operatiivinen vaikutus:

1. akun target clampataan `strict_limits_max_w`-rajan sisaan

## HAEO:n nykyinen operatiivinen rooli

HAEO:n nykyinen rooli on rajattu. Koodin perusteella se tekee seuraavaa:

1. tuo akkutargetin `MAX_EXPORT`- ja `CHEAP_GRID_CHARGE`-tiloihin, jos forecast on tuore
2. tuo EV-targetin `CHEAP_GRID_CHARGE`-tilaan, jos forecast on tuore
3. `HORIZON_BY_HAEO + NET_ZERO` voi muodostaa EMS:n sisaisen varttikohtaisen HAEO-planin
4. `HORIZON_BY_HAEO` voi pakottaa HAEO-ennusteen konfiguroiduksi, vaikka forecast-profile olisi `NONE`

## Surplus-kuormien operointi

Nykyinen kohdejoukko on:

1. EV
2. RELAY1
3. RELAY2

Aktivointi- ja vapautusjarjestys riippuu prioriteeteista. Quarter-harnessin oletusasetuksissa prioriteetit ovat:

1. `RELAY1 = 3`
2. `EV = 2`
3. `RELAY2 = 1`

Talla asetuksella aktivointijarjestys on:

1. RELAY1
2. EV
3. RELAY2

Ja vapautusjarjestys on:

1. RELAY2
2. EV
3. RELAY1

## Tarkeimmat diagnostiset tarkastukset

Kun halutaan ymmartaa EMS:n paatos, tarkasta ensiksi `policy_decision_trace`-attribuutit:

1. `guard`
2. `guard_reason`
3. `dominant_limitation`
4. `effective_forecast`
5. `battery_write_enabled`
6. `surplus_policy_active`
7. `surplus_device_dispatch_decision`
8. `surplus_explanation`
9. `surplus_freeze_until_ts`
10. `config_source`
11. `config_grouped_production_ready`
12. `device_policies`

Sen jalkeen tarkasta:

1. `sensor.ems_dispatch_state_applier_trace`
2. `sensor.ems_actuator_writer_trace`

## Vianetsintaohjeet

### EV ei kaynnisty

Tarkista jarjestyksessa:

1. `goal_profile`
2. `guard`
3. `sensor.ems_device_policies_pyscript` / `device_policies`
4. `sensor.ems_active_surplus_devices`
5. `actuator_writer_trace.ev`

Tulkitse:

1. jos `EV_CHARGER.enabled = false` ja `target_w = 0`, EV:ta ei pyydeta aktiiviseksi
2. jos `EV_CHARGER.enabled = true` ja `target_w > 0`, writer muuntaa pyynnon ampeereiksi
3. writer-tracen `reason` kertoo, kirjoitettiinko oikeasti vai oliko tila jo valmiiksi oikea

### EV jaa vaaraan virtaan

Tarkista:

1. `ev_force_current_a`
2. `goal_profile`
3. `sensor.ems_device_policies_pyscript`
4. `actuator_writer_trace.ev.reason`

Tyypillinen selitys nykykoodissa:

1. NET_ZERO release -polussa writer palauttaa currentin minimiin
2. `hard_off`-polussa writer sammuttaa laturin mutta jattaa selectorin minimiin

Restore_min-haaran tarkennus (EV-primary + HOME_BATTERY):

1. jos `ev_policy_mode = restore_min` ja `charger_on = false`, battery-target voi jatkaa normaalia NET_ZERO-saatoa (purku sallittu)
2. jos `ev_policy_mode = restore_min` ja `charger_on = true`, battery floor-hold voi aktivoitua ja battery-target lukittuu flooriin
3. tarkista aina yhdessa: `ev_policy_mode`, `EV_CHARGER.target_w`, `switch.charger_control` (`charger_on`) ja `battery_min_floor_reason`

### Releet eivat aktivoidu

Tarkista:

1. `relay*_surplus_allowed`
2. `relay*_force_on`
3. `sensor.ems_active_surplus_devices`
4. `device_policies`
5. `actuator_writer_trace.relay*`

### Akku ei reagoi

Tarkista:

1. `battery_write_enabled`
2. `control_profile`
3. `guard`
4. `device_policies`
5. `actuator_battery_setpoint_w`
6. writerin deadband- ja ramp-arvot

Jos `battery_write_enabled=False`, writer ei kirjoita akulle.

### Järjestelma putoaa `DEGRADED`-tilaan

Tarkista:

1. battery inverter heartbeatin ika
2. SOC:n saatavuus ja validius
3. `guard_reason`

Koodin perusteella `DEGRADED` tulee stale/invalid battery inverter- tai SOC-datasta.

### HAEO ei vaikuta

Tarkista:

1. `forecast_profile`
2. `control_profile`
3. `configured_forecast`
4. `effective_forecast`
5. HAEO freshness-lahteiden paivitysajat

Jos `effective_forecast=NONE`, EMS on paikallisessa fallbackissa, vaikka HAEO olisi konfiguroitu.

## Tunnetut ristiriidat ja riskit

1. Goal-profile-valinnan automatiikkaa ei loytynyt taman repon sisalta.
2. `DEGRADED`-tilassa writer skiptaa rele- ja EV-actuatorien aktiivisen pakottamisen, vaikka latchit clearataan. Tama kannattaa huomioida turvallisuusriskina ja erillisena tuotantopaatoksena.

## Avoimet kysymykset / jatkokehitys

1. Missa mahdollinen automaattinen goal switcher sijaitsee, jos sellainen on tuotannossa kaytossa?
2. Tarvitaanko erillinen health-check tai dashboard `guard_reason`, `battery_write_enabled`, `ev_policy_mode` ja HAEO freshness -seurantaan?
3. Pitaako vanhat `__pycache__`- ja `.pyc`-artefaktit poistaa reposta?
