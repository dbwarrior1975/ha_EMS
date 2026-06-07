# Home Assistant EMS

Tama repositorio sisaltaa Home Assistant / Pyscript -pohjaisen EMS-ohjauksen, jonka paatarkoitus on ohjata akkua, EV-laturia ja kahta relekuormaa eri energiatavoitteiden mukaan.

Nykyiset tuetut goal-profiilit ovat:

1. `NET_ZERO`
2. `MAX_EXPORT`
3. `CHEAP_GRID_CHARGE`

## Paaosat

Top-level tuotantoketju koostuu kolmesta paakomponentista:

1. `ems_policy_engine.py`
2. `ems_dispatch_state_applier.py`
3. `ems_actuator_writers.py`

Vastuut lyhyesti:

1. policy engine laskee akun, EV:n ja releiden policy-ulostulot
2. dispatch state applier muuntaa surplus-dispatch-paatokset sisaisiksi dispatch state-tiloiksi
3. actuator applier kirjoittaa lopulliset ohjaukset Home Assistantin aktuaattoreille

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
2. surplus-policy voi aktivoida releita ja EV:n prioriteettien mukaan
3. EV voi menna low-PV-tilanteessa `hard_off`-polkuun nykyisen policy-attribuutin kautta

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

## Tarkeat entiteetit

Nykyinen mappaus on tiedostossa `modules/ems_adapter/entity_map.py`.

Keskeiset profiilit:

1. `input_select.ems_control_profile`
2. `input_select.ems_goal_profile`
3. `input_select.ems_forecast_profile`
4. `input_select.ems_guard_profile`

Keskeiset mittaukset:

1. `sensor.victron_mqtt_b827eb48c929_system_0_system_dc_battery_soc`
2. `sensor.victron_mqtt_b827eb48c929_battery_1_battery_min_cell_voltage`
3. `sensor.victron_mqtt_b827eb48c929_battery_1_battery_power`
4. `sensor.average_active_power_2`
5. `sensor.hourly_energy_balance`
6. `sensor.required_power_consumption`
7. `sensor.ems_calculated_required_power_for_net_zero`
8. `sensor.pv_instant_power_2`

Keskeiset config-entiteetit:

1. `input_number.ems_deadband_w`
2. `input_number.ems_ramp_max_w`
3. `input_number.ems_strict_limits_max_w`
4. `input_number.victron_maksimi_auringon_latausteho`
5. `input_number.ems_battery_protect_soc`
6. `input_number.ems_battery_protect_soc_recovery_margin`
7. `input_number.ems_battery_protect_min_cell_voltage_v`
8. `input_number.ems_ev_min_current_a`
9. `input_number.ems_ev_max_current_a`
10. `input_number.ems_ev_charger_phases`
11. `input_number.ems_ev_force_current_a`
12. `input_number.ems_ev_hard_off_pv_threshold_kw`
13. `input_number.ems_ev_hard_off_low_pv_cycles`
14. `input_number.ems_haeo_stale_timeout_s`
15. `input_number.ems_relay1_power_kw`
16. `input_number.ems_relay2_power_kw`
17. `input_number.ems_surplus_relay1_priority`
18. `input_number.ems_surplus_relay2_priority`
19. `input_number.ems_surplus_ev_priority`

Surplus- ja aktuaattoritilat:

1. `input_datetime.ems_surplus_freeze_until`
2. `input_boolean.ems_surplus_ev_active`
3. `input_boolean.ems_surplus_relay1_active`
4. `input_boolean.ems_surplus_relay2_active`
5. `switch.charger_control`
6. `number.charger_current_level`
7. `switch.relay_1_2`
8. `switch.relay_2_2`
9. `number.victron_mqtt_b827eb48c929_system_0_system_ac_power_set_point`

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

Projektin testikomento:

```bash
pytest -q tests
```

WSL-esimerkki:

```bash
cd "/mnt/c/Users/virtamik/OneDrive - Accountor Holding Oy/HA/EMS/ha_EMS"
pytest -q
```

Jos WSL:ssa halutaan oma Linux-venv, suositeltu tapa on:

```bash
python3 -m venv .venv-wsl
source .venv-wsl/bin/activate
pip install -U pip pytest
pytest -q
```

## Kayttoonotto

Tama repositorio ei sisalla koko Home Assistant -ympariston konfiguraatiota, vaan EMS olettaa etta vaaditut entityt ovat jo olemassa Home Assistantissa.

Ennen kayttoonottoa varmista ainakin:

1. kaikki `entity_map.py`-mappauksen vaatimukset on provisioitu
2. Pyscript on saatavilla ja top-level scriptit voidaan suorittaa
3. goal- ja control-profiilien arvot vastaavat projektin tukemia tiloja
4. HAEO-entiteetit ovat olemassa, jos forecast-kayttoa halutaan
5. diagnostiikkaentiteetit ovat seurattavissa Home Assistantissa

Suositeltu ensikayttoonottojarjestys:

1. varmista mittausentiteetit
2. varmista config-entiteetit ja oletusarvot
3. kaynnista policy engine
4. kaynnista dispatch state applier
5. kaynnista actuator applier
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
