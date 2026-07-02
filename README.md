# Home Assistant EMS

Tama repositorio sisaltaa Home Assistant / Pyscript -pohjaisen EMS-ohjauksen.
EMS ohjaa yhta `HOME_BATTERY`-akkua, `0-n` `kind: RELAY` -laitetta ja
`0-n` `kind: EV_CHARGER` -laturia eri energiatavoitteiden mukaan.

Releiden dispatch ja writer-pinta ovat device-id-pohjaisia. EV-latureiden
nykyinen tuotantoraja on selected-single boundary: useampi EV voi olla
konfiguroituna, mutta yksi EV valitaan aktiiviseksi adjustable-laitteeksi
kerrallaan. Multi-EV simultaneous power split, EV-round-robin ja usean
`HOME_BATTERY`-akun tuki eivat kuulu tahan releaseen.

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

1. policy engine laskee device-id-pohjaiset policy-ulostulot akulle, valitulle EV:lle ja releille
2. dispatch state applier muuntaa surplus-dispatch-paatokset sisaisiksi dispatch state-tiloiksi
3. actuator writer loop kirjoittaa lopulliset ohjaukset Home Assistantin aktuaattoreille

Lisadokumentaatio:

1. `docs/dev/arkkitehtuuri.md`
2. `docs/user/operointi.md`
3. `docs/dev/testausautomaatio.md`
4. `docs/dev/tilakaavio.md`
5. `docs/user/business_logic_guide.md`
6. `docs/user/EMS_parametrointi_guide.md`

## Konfiguraatio

Nykyinen kanoninen tuotantokonfiguraatio on grouped YAML -tiedosto:

- `EMS_config.yaml`

EMS olettaa tuotannossa oletuksena, etta tiedosto loytyy Home Assistantin
`/config/`-hakemistosta talla tarkalla nimella:

- `/config/EMS_config.yaml`

Kaytannossa:

1. kopioi repon `EMS_config.yaml` Home Assistantin `/config/`-hakemistoon
2. sailyta tiedoston nimi `EMS_config.yaml`
3. paivita tiedoston sisaiset entity-id:t vastaamaan omaa HA-ymparistoasi

Oletuspolku tulee suoraan runtime-koodista:

- `modules/ems_adapter/runtime_context.py`
- `_DEFAULT_GROUPED_CONFIG_PATH = '/config/EMS_config.yaml'`

`EMS_GROUPED_CONFIG_PATH` voi edelleen overrideata polun, mutta normaalissa
tuotantokaytossa sita ei tarvita.

Tarkeä rajaus:

1. grouped `EMS_config.yaml` on nykyinen kanoninen konfiguraatio
2. tuotantoruntime rakentaa `CoreConfig`-mallin `runtime_context`-kerroksen kautta
3. `read_config()` palauttaa `CoreConfig`-instanssin ilman erillista
   rinnakkaista config-viewta aktiivisessa runtime-polussa
4. vanha flat entity-map -tiedosto ei kuulu enaa aktiiviseen tuotanto- tai testipintaan
5. `EMS_config.yaml` on pakollinen; puuttuva tai virheellinen tiedosto on kova
   kaynnistys-/runtime-virhe eika fallbackaa vanhoihin defaultteihin
6. device capability -booleanit ovat kovia runtime-rajoja:
   `can_absorb_w=false` estaa positiivisen `target_w`:n ja `can_produce_w=false`
   estaa negatiivisen `target_w`:n

## Config examples and test fixtures

Kayttajan ensisijainen lahtopohja on root-tason `example_EMS_config.yaml`.
Se nayttaa grouped YAML -rakenteen ja oletuslaitteet, mutta sita tulee sovittaa
oman Home Assistant -ympariston entity-id:ihin ennen tuotantoa.

Lisaksi `tests/e2e_entity/*/EMS_config.yaml` -tiedostot ovat testattuja
skenaariokohtaisia esimerkkeja eri kardinaliteettirajoille:

1. `tests/e2e_entity/net_zero_no_relays_ev_only/EMS_config.yaml` kuvaa 0 relay -tapauksen
2. `tests/e2e_entity/net_zero_no_ev_relays_only/EMS_config.yaml` kuvaa 0 EV -tapauksen
3. `tests/e2e_entity/net_zero_priority_order_quarter_3_relays/EMS_config.yaml` kuvaa 3 reletta
4. `tests/e2e_entity/net_zero_two_ev_one_relay/EMS_config.yaml` kuvaa 2 EV + selected-single -rajan
5. `tests/e2e_entity/custom_device_ids_selected_single_ev/EMS_config.yaml` kuvaa custom device-id:t

Fixtureja voi kayttaa lisareferenssina, mutta tuotantoon kayttajan tulee
kopioida ja sovittaa root example tai `docs/user/config_examples.md`:n
minimiesimerkki. Root example ei tarkoita, etta vain sen laitemaara olisi tuettu.

## Nopeat suunnistusdokumentit

Kahdelle katselmoinneissa toistuvalle tarpeelle on omat dokumentit:

1. `docs/dev/tilakaavio.md` kokoaa yhteen guard-tilojen ja surplus-dispatch-statejen siirtymalogiikan.
2. `docs/user/business_logic_guide.md` kuvaa EMS:n energiastrategian kayttajan nakokulmasta.

## Tuetut semantiikat

### `NET_ZERO`

Paikallinen quarter-balancing -tila.

1. akulle lasketaan net-zero-target
2. surplus-policy aktivoi absorboivia deviceja device-id-pohjaisessa priority orderissa
3. selected-single EV tai kotiakku voi toimia adjustable-surplus-roolissa konfiguraation mukaan
4. EV voi menna low-PV-tilanteessa `hard_off`-polkuun nykyisen policy-attribuutin kautta

Canonical command/state -integraatiopinta on device-id-pohjainen:

1. `sensor.ems_device_policies_pyscript`
2. `sensor.ems_active_surplus_devices`
3. `sensor.ems_surplus_dispatch_command_pyscript`

Diagnostiikka- ja selityspinnat:

1. `sensor.ems_policy_decision_trace_pyscript`
2. `sensor.ems_dispatch_state_applier_trace`
3. `sensor.ems_actuator_writer_trace` ja sen `devices`-map

Decision-tracessa voi nakya nimiarvoja kuten `RELAY1`, `RELAY2`,
`EV_CHARGER` ja `ADJUSTABLE`, mutta uudet dashboardit ja automaatiot kannattaa
sitouttaa `device_policies`-, `dispatch_command`- ja
`active_surplus_devices`-payload-kenttiin.

Surplus-policy voi aktivoitua vain, kun kaikki seuraavat ehdot tayttyvat:

1. `control_profile = AUTOMATIC`
2. `goal_profile = NET_ZERO`
3. `guard_profile = NORMAL_LIMITS`
4. effective forecast on `NONE`

Quarter-balance semantiikka:

1. EMS:n kanoninen runtime-termi on `quarter_energy_balance_kwh`
2. se kuvaa nykyisen vartin energiataseen, vaikka ulkoinen HA-entity voi edelleen olla `sensor.hourly_energy_balance`
3. `rpnz_w` johdetaan EMS:n sisalla kvartaalitaseesta ja jaljella olevasta varttiajasta
4. aktiivisen surplus-kuorman release kayttaa `10 W` practical-zero deadbandia
5. jos `rpnz_w <= 10 W`, alin prioriteetti aktiivisista surplus-kohteista voidaan vapauttaa

### `MAX_EXPORT`

Export-first -tila.

1. akun paikallinen fallback on `-4000 W`
2. EV policy on `0`
3. EV writer kayttaa `hard_off`-semantiikkaa
4. releet ovat pois paalta

### `CHEAP_GRID_CHARGE`

Latauspainotteinen tila.

1. akun paikallinen fallback on `100 W`
2. EV oletuksena `capabilities.max_absorb_w`
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
Nykyinen tuotantopolku rakentaa Home Assistant -entity_id:t ensisijaisesti
grouped `EMS_config.yaml` -tiedostosta `runtime_context`-kerroksen kautta.

Keskeiset tiedostot:

1. `EMS_config.yaml`
2. `modules/ems_adapter/runtime_context.py`

Nopea mappausperiaate:

1. dokumentaatio ja operointi = EMS-avaimet
2. runtime-integraatio = `EMS_config.yaml`-tiedoston HA entity_id:t

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
6. `quarter_energy_balance_kwh`
7. `charger_control`
8. `charger_current`
9. `pv_power_w`

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
10. `ev_min_absorb_w`
11. `ev_max_absorb_w`
12. `ev_charger_phases`
13. `ev_force_on`
14. `ev_hard_off_pv_threshold_kw`
15. `ev_hard_off_low_pv_cycles`
16. `ev_hard_off_release_cycles`
17. `ev_current_step_a`
18. `ev_voltage_v`
19. `nz_battery_floor_default_w`
19. `nz_battery_floor_ev_active_w`
20. `adjustable_surplus_load`
21. `adjustable_primary_load`
22. `adjustable_surplus_activation`
23. `adjustable_surplus_load_priority`
24. relekohtaiset power/priority-avaimet device-id:n mukaan
25. EV-kohtaiset power/priority-avaimet device-id:n mukaan
26. adapteri-/debug-polussa voi yha nakya `relay1_*`, `relay2_*` ja `ev_*` -avaimia
27. `surplus_freeze_s`
28. `haeo_stale_timeout_s`

Keskeiset surplus-state-avaimet (EMS):

1. `surplus_freeze_until`
2. `active_surplus_devices`
3. `previous_device_state`

Keskeiset releiden override- ja sallinta-avaimet (EMS):

1. canonical grouped configissa releilla on device-id-kohtaiset `policy.surplus_allowed` -entityt
2. canonical grouped configissa releilla on device-id-kohtaiset `policy.force_on` -entityt
3. top-level `relay1_*`- ja `relay2_*`-business-aliakset eivat kuulu enaa
   runtime-sopimukseen; override- ja sallintatieto luetaan laitteen omista
   `policy.*`-entityista

Keskeiset HAEO-avaimet (EMS):

1. `haeo_battery_power_active`
2. `haeo_ev_battery_power_active`
3. `haeo_battery_active_power_fresh_source`
4. `haeo_ev_active_power_fresh_source`

HAEO freshness arvioidaan seka battery- etta EV-freshness-lahteiden iasta. Molempien tulee olla alle `haeo_stale_timeout_s`, jotta effective forecast voi olla `HAEO`.

Keskeiset policy-ulostuloavaimet (EMS):

1. `device_policies`
2. `dispatch_command`
3. `active_surplus_devices`
4. `previous_device_state`
5. `policy_decision_trace` (diagnostiikkapeili)

Oleellinen tulkinta:

1. `device_policies` on writerin kanoninen ohjausrajapinta
2. `dispatch_command` on dispatch state applierin kanoninen komentorajapinta
3. `policy_decision_trace` on diagnostiikka- ja selityspinta, ei writerin tai
   dispatch-applierin kanoninen command/state-lahde
4. EV:n ampeerit eivat kuulu `device_policies`-sopimukseen, vaan writerin
   actuator-rajan `target_current_a`-kenttiin
5. `policy_decision_trace`-kentista johdetut yksittaisjulkaisut eivat ole
   release-contractin osa

Capability-semantiiikka:

1. `can_absorb_w=false` estaa laitteen kayton lataus-/kulutussuuntaan
2. `can_produce_w=false` estaa laitteen kayton purku-/tuotantosuuntaan
3. battery policy clampataan capabilityjen mukaan ennen writeria, ja writer tekee
   saman tarkistuksen viela viimeisena turvallisuusrajana
4. tuotanto-YAML:ssa `HOME_BATTERY.can_absorb_w=false` ja
   `HOME_BATTERY.can_produce_w=false` yhdessa on validaatiovirhe

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

1. jos `adjustable_primary_load` puuttuu/tyhja, runtime kayttaa oletusta (`implicit_primary_equals_surplus`), jossa primary asetetaan samaksi kuin `adjustable_surplus_load`
2. trace raportoi taman syylla `primary_surplus_combo_reason = implicit_primary_equals_surplus`
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
2. contract-testit ovat kansiossa `tests/contract/`
3. aja contract-testit suoraan polulla tai `-k contract`-suodatuksella

Projektin testikomento:

```bash
pytest -q tests
```



## Kayttoonotto

Tama repositorio ei sisalla koko Home Assistant -ympariston konfiguraatiota, vaan EMS olettaa etta vaaditut entityt ovat jo olemassa Home Assistantissa.

Ennen kayttoonottoa varmista ainakin:

1. `EMS_config.yaml` on kopioitu Home Assistantin `/config/`-hakemistoon nimella `/config/EMS_config.yaml`
2. kaikki `EMS_config.yaml`-tiedostossa viitatut entityt on provisioitu
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

1. `sensor.ems_device_policies_pyscript`
2. `sensor.ems_surplus_dispatch_command_pyscript`
3. `sensor.ems_policy_decision_trace_pyscript`
4. `sensor.ems_dispatch_state_applier_trace`
5. `sensor.ems_actuator_writer_trace`

Erityisen hyodyllisia attribuutteja:

1. `guard`
2. `guard_reason`
3. `dominant_limitation`
4. `effective_forecast`
5. `battery_write_enabled`
6. `surplus_device_dispatch_action`
7. `ev_policy_mode`

## Tunnetut rajoitteet

1. tuettu akkumalli on yksi `HOME_BATTERY`
2. useampi EV voi olla konfiguroituna, mutta tuotantoraja on selected-single EV
3. multi-EV simultaneous power split ja EV-round-robin eivat kuulu tahan releaseen
4. `DEGRADED` ei pakota kaikkia jo paalla olevia aktuaattoreita pois paalta
5. goal-switchauksen automatiikkaa ei ole dokumentoitu taman repon sisalla
6. projekti ei sisalla valmista Home Assistant YAML -kokoonpanoa

## Rollback / disable

Jos EMS:n vaikutus halutaan poistaa nopeasti:

1. pysayta tai disabloi top-level komponentit
2. vaihda `control_profile` manuaalitilaan
3. aseta akku, EV ja releet haluttuihin turvallisiin manuaaliasetuksiin Home Assistantista

Jos tulevaisuudessa tarvitaan yksi eksplisiittinen safe-off-kayttotila, se kannattaa toteuttaa erillisena operointitilana eika goal-profiilina.
