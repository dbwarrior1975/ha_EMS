# Surplus Loads To Support More Flexibility

Paivitetty: 2026-06-22

Taman dokumentin tarkoitus on suunnitella muutos, jossa EMS ei oleta kiinteasti
kahta reletta (`RELAY1`, `RELAY2`) ja yhta EV-laturia (`EV_CHARGER`). Tavoite on
tukea surplus-kuormia muodossa:

1. releita `0-n`
2. EV-latureita optiona `0-n`
3. akku edelleen erikoislaitteena, koska se voi seka absorboida etta tuottaa
4. surplus-dispatch ja writerit device-id -pohjaisesti ilman kiinteita
   `relay1/relay2` haaroja

Nykyinen arkkitehtuuri on jo osin oikeassa suunnassa:

1. `device_policies` on kanoninen writer-sopimus
2. `active_surplus_devices` on device-id -pohjainen state
3. `surplus_device_dispatch_*` trace kantaa device-id -tietoa
4. capabilityt (`can_absorb_w`, `can_produce_w`) ovat nyt oikeita kovia rajoja

Jaljella oleva kiinteys on kuitenkin merkittavaa:

1. `EMS_config.yaml` listaa `EV_CHARGER`, `RELAY1`, `RELAY2` yksittaisina
   top-level device-id:ina
2. `CoreConfig` sisaltaa kentat `ev_charger`, `relay1`, `relay2`
3. `EmsConfig` sisaltaa `relay1_*`, `relay2_*`, `ev_*` scalar-kenttia
4. `build_surplus_device_targets` rakentaa aina kolme targettia:
   `ADJUSTABLE`, `RELAY1`, `RELAY2`
5. `ems_policy_engine.py` lukee erikseen `relay1_*` ja `relay2_*` entityt
6. `ems_actuator_writers.py` kirjoittaa erikseen yhden EV:n ja kaksi reletta
7. e2e-harness ja testit olettavat samat kiinteat device-id:t

## Tavoitetila

Surplus-kuormat ovat lista konfiguroituja deviceja:

```yaml
ems:
  devices:
    HOME_BATTERY:
      kind: BATTERY
      ...

    EV_MAIN:
      kind: EV_CHARGER
      ...

    EV_GARAGE:
      kind: EV_CHARGER
      ...

    RELAY_SAUNA:
      kind: RELAY
      ...

    RELAY_BOILER:
      kind: RELAY
      ...
```

Device-id:n nimi ei maarita logiikkaa. `kind`, `capabilities`, `policy` ja
`adapter` maarittavat kayttaytymisen.

Surplus activation order muodostuu device-policyista:

1. ota mukaan device, jonka `capabilities.can_absorb_w=true`
2. ota mukaan vain device, jonka surplus policy on sallittu
3. jarjesta `policy.priority` ja mahdollisen tie-breaker-saannon mukaan
4. dispatch tuottaa `ACTIVATE device_id`, `RELEASE device_id` tai `CLEAR_ALL`
5. writer etsii saman `device_id`:n policyista ja device-configista

## Ei-tavoitteet ensivaiheessa

1. Ei muuteta akun roolia geneeriseksi surplus-kuormaksi ennen kuin rele/EV-listat
   toimivat.
2. Ei poisteta kaikkia scalar trace -kenttia ensivaiheessa. Ne voidaan jattaa
   diagnostisiksi compatibility-traceiksi, kunhan writer-sopimus pysyy
   `device_policies`-pohjaisena.
3. Ei yriteta tukea useita akkuja samassa vaiheessa.
4. Ei yriteta ratkaista HAEO:n usean EV:n optimointia ennen kuin perusdispatch
   tukee device-listoja.

## Vaiheet

| Vaihe | Status | Sisalto |
|---|---|---|
| 1. Nykyisten kiinteiden oletusten inventointi | completed | koodista luettu inventaario lisatty dokumenttiin ja luokiteltu |
| 2. YAML device-listan sopimus | completed | maaritelty map-pohjainen device contract, cardinality-saannot ja siirtymarajat |
| 3. Core device registry | completed | `CoreConfig.devices` registry, helperit ja ekstra-devicejen lukeminen YAML:sta |
| 4. Runtime entity registry | completed | registry toimii n-device-pohjaisesti; relay1/relay2 top-level aliasit ovat viela siirtyma- ja compatibility-pintaa |
| 5. Surplus target builder | completed | target-builder vastaanottaa geneerisen relay-listan ja tuottaa device-id-pohjaiset targetit |
| 6. Policy engine | completed | relay- ja EV-device-policyt tuotetaan registry-pohjaisesti; multi-EV boundary on edelleen "multiple configured, one selected" |
| 7. Dispatch state applier | completed | dispatch kasittelee active-device-listaa geneerisesti ja sailyttaa aktivointijarjestyksen device-id-pohjaisesti |
| 8. Writerit | completed | writer loop kirjoittaa kaikki registryssa olevat relay- ja EV-devicet kindin mukaan; relay1/relay2 fallbackit ovat vain compatibilitya |
| 9. Trace- ja dashboard-sopimus | completed | canonical trace kantaa device-id-listat ja writer-trace julkaisee geneerisen `devices`-mapin |
| 10. Testit | completed | unit/contract/e2e ovat vihreat nykyisella 0-n relay + selected single-EV boundarylla; koko `tests` -> `222 passed, 1 xfailed` |
| 11. Dokumentaatio ja migration | pending | kuvaa uusi YAML ja rikkoutuvat HA-dashboard/entity-oletukset |
| 12. Release-validaatio | pending | koko testsuite, Pyscript smoke ja paketointi |

## Vaihe 1: Nykyisten kiinteiden oletusten inventointi

Status: completed

Tavoite:

1. Kirjaa koodipaikat, joissa device-id tai lukumaara on kovakoodattu.
2. Erota kolme eri kiinteyden lajia:
   - tuotantologiikka
   - runtime/entity adapterointi
   - testien odotukset

Todennakoiset kohteet:

1. `modules/ems_adapter/config_loader.py`
   - `SUPPORTED_DEVICE_IDS`
   - `SUPPORTED_DEVICE_KINDS`
   - `CoreConfig(home_battery, ev_charger, relay1, relay2)`
   - runtime aliasit kuten `relay1_power_kw`, `relay2_force_on`,
     `actuator_ev_current_a`
2. `modules/ems_adapter/device_read_model.py`
   - `_BATTERY_ID`, `_EV_ID`, `_RELAY1_ID`, `_RELAY2_ID`
   - `build_device_configs` palauttaa aina nelja devicea
3. `modules/ems_core/net_zero/surplus_device_targets.py`
   - `build_surplus_device_targets` palauttaa aina `ADJUSTABLE`, `RELAY1`,
     `RELAY2`
4. `modules/ems_core/net_zero/engine.py`
   - `relay1_*`, `relay2_*`
   - `EV_CHARGER` yksittaisena primary/adjustable targettina
   - scalar trace kentat `relay1_command`, `relay2_command`, `ev_current_a`
5. `ems_policy_engine.py`
   - `read_measurements` lukee yhden EV:n ja kaksi reletta
   - loop antaa corelle `relay1_surplus_allowed`, `relay2_surplus_allowed`,
     `relay1_net_zero_active`, `relay2_net_zero_active`
6. `ems_dispatch_state_applier.py`
   - aktivointi/vapautus kasittelee erikseen `RELAY1`, `RELAY2` ja
     adjustable-deviceja
7. `ems_actuator_writers.py`
   - yksi EV writer
   - kaksi relay writer -kutsua
   - writer trace avaimet `ev`, `relay1`, `relay2`
8. `tests/e2e_entity`
   - skenaariot olettavat kaksi reletta ja yhden EV:n

Hyvaksynta:

1. Dokumenttiin lisataan inventory-osio, jossa jokainen aktiivinen kiintea oletus
   on luokiteltu.
2. Ei viela muuteta kayttaytymista.

Toteutunut inventory:

1. Tuotantologiikka:
   `modules/ems_core/net_zero/engine.py`
   - core ottaa edelleen sisaan `relay1_surplus_allowed`, `relay2_surplus_allowed`,
     `relay1_force_on`, `relay2_force_on`, `relay1_net_zero_active`,
     `relay2_net_zero_active`
   - primary/surplus-combo logiikka olettaa edelleen yhden EV:n ja yhden akun
     parin (`EV_CHARGER` vs `HOME_BATTERY`)
   - scalar trace tuottaa edelleen `relay1_command`, `relay2_command`,
     `ev_current_a`
   - surplus-targetit rakennetaan edelleen kiinteasta kolmikosta
     `ADJUSTABLE`, `RELAY1`, `RELAY2`

2. Surplus-target builder:
   `modules/ems_core/net_zero/surplus_device_targets.py`
   - `build_surplus_device_targets(...)` palauttaa aina kolme targettia
   - `SurplusDeviceTarget.decision_name` on edelleen rajattu literal-arvoihin
     `ADJUSTABLE`, `RELAY1`, `RELAY2`
   - `device_dispatch_to_legacy_dispatch(...)` mapittaa edelleen device-id:t
     takaisin noihin kolmeen nimeen

3. Config- ja runtime-adapterointi:
   `modules/ems_adapter/config_loader.py`
   - `REQUIRED_DEVICE_IDS` vaatii edelleen `HOME_BATTERY`, `EV_CHARGER`,
     `RELAY1`, `RELAY2`
   - `EXPECTED_DEVICE_KINDS` olettaa yhden EV:n ja kaksi reletta
   - `CoreConfig` rakennetaan edelleen kenttiin `home_battery`, `ev_charger`,
     `relay1`, `relay2`
   - runtime aliasit ovat litteita, esimerkiksi `relay1_power_kw`,
     `relay2_force_on`, `charger_current`, `actuator_relay1`
   - grouped configin contract ei viela salli 0-n saman kindin deviceja

4. Device-read-malli:
   `modules/ems_adapter/device_read_model.py`
   - `_BATTERY_ID`, `_EV_ID`, `_RELAY1_ID`, `_RELAY2_ID` ovat kovakoodattuja
   - `build_device_configs(...)` palauttaa aina nelja devicea
   - `build_device_states(...)` lukee aina yhden EV:n ja kaksi reletta
   - `build_devices(...)` kokoaa tupleen vain nuo nelja devicea

5. Policy engine:
   `ems_policy_engine.py`
   - `read_measurements(...)` lukee yhden EV:n (`charger_on`, `charger_current_a`)
     ja kaksi reletta (`relay1_on`, `relay2_on`)
   - `_read_adjustable_surplus_active(...)` etsii aktiivisista deviceista vain
     `EV_CHARGER` tai `HOME_BATTERY`
   - loop syottaa corelle kiinteat `relay1_*` ja `relay2_*` kentat
   - `previous_device_state` kirjoitetaan yhdelle adjustable-device-id:lle,
     ei usealle EV:lle

6. Dispatch state applier:
   `ems_dispatch_state_applier.py`
   - `_canonical_active_device_ids(...)` jarjestaa aktiiviset id:t edelleen
     kiinteassa jarjestyksessa `RELAY1`, `EV_CHARGER`, `HOME_BATTERY`, `RELAY2`
   - `_decision_text_from_device_command(...)` tuntee vain `ADJUSTABLE`,
     `RELAY1`, `RELAY2`
   - `_apply_device_dispatch(...)` kasittelee erikseen `RELAY1`, `RELAY2` ja
     yhden adjustable-laitteen
   - `CLEAR_ALL` tunnistaa edelleen adjustable-joukon vain
     `EV_CHARGER` / `HOME_BATTERY`
   - trace `writes` kayttaa edelleen nimiä kuten `relay1_on`, `adjustable_off`

7. Writerit:
   `ems_actuator_writers.py`
   - `_capability_device_config_for_id(...)` tuntee vain
     `HOME_BATTERY`, `EV_CHARGER`, `RELAY1`, `RELAY2`
   - yksi EV writer, kaksi relay writer -kutsua
   - writer trace julkaisee avaimet `victron`, `ev`, `relay1`, `relay2`
   - writer-looppi kutsuu edelleen kiinteasti `RELAY1` ja `RELAY2`

8. YAML:
   `EMS_config.yaml`
   - yksi `EV_CHARGER` top-level device
   - kaksi top-level relay-devicea `RELAY1` ja `RELAY2`
   - `global_config.adjustable_surplus_load` ja `adjustable_primary_load`
     tukevat edelleen kaytannossa vain `EV_CHARGER` / `HOME_BATTERY` kombon

9. Testit:
   `tests/contract`, `tests/unit`, `tests/e2e_entity`
   - contract-testit odottavat edelleen alias-avaimia kuten `relay1_power_kw`,
     `relay2_force_on`, `charger_current`
   - unit-testit viittaavat laajasti `RELAY1`, `RELAY2`, `EV_CHARGER`
   - e2e-harness seedaa edelleen yhden EV:n ja kaksi reletta
   - useat e2e-storyt todistavat nimenomaan kahden releen priority-jarjestysta

Johtopaatos:

1. `active_surplus_devices` ja `device_policies` ovat jo oikeassa suunnassa,
   koska ne ovat device-id -pohjaisia.
2. Suurin kiinteys ei ole enaa trace-pinnassa vaan config-loaderissa,
   core-sopimuksessa, dispatch-applierissa ja writer-loopissa.
3. Releiden `0-n` kannattaa toteuttaa ennen monen EV:n tukea, koska relay ei
   kanna mukana EV:n hard-off/release-statea.

## Vaihe 2: YAML device-listan sopimus

Status: completed

Tavoite:

`EMS_config.yaml` sallii device-id:t ilman kiinteaa nimeamista, kunhan device
kuvaa oman tyyppinsa ja adapterinsa.

Valittu sopimus:

```yaml
ems:
  global_config:
    adjustable_primary_load: input_select.ems_adjustable_primary_load
    adjustable_surplus_load: input_select.ems_adjustable_surplus_load

  devices:
    HOME_BATTERY:
      kind: BATTERY
      capabilities:
        can_absorb_w: true
        can_produce_w: true
      policy:
        priority: input_number.ems_home_battery_priority
      adapter:
        target_w: number.victron_system_ac_power_setpoint
        current_w: sensor.victron_system_ac_power_setpoint

    EV_MAIN:
      kind: EV_CHARGER
      capabilities:
        can_absorb_w: true
        can_produce_w: false
      policy:
        priority: input_number.ems_ev_main_priority
        surplus_allowed: input_boolean.ems_ev_main_surplus_allowed
      adapter:
        enabled: switch.ev_main_enabled
        current_a: number.ev_main_current
        current_min_a: input_number.ems_ev_main_min_current_a
        current_max_a: input_number.ems_ev_main_max_current_a
        current_step_a: input_number.ems_ev_main_current_step_a
        phases: input_number.ems_ev_main_phases
        voltage_v: input_number.ems_ev_main_voltage_v

    EV_GARAGE:
      kind: EV_CHARGER
      capabilities:
        can_absorb_w: true
        can_produce_w: false
      policy:
        priority: input_number.ems_ev_garage_priority
        surplus_allowed: input_boolean.ems_ev_garage_surplus_allowed
      adapter:
        enabled: switch.ev_garage_enabled
        current_a: number.ev_garage_current
        current_min_a: input_number.ems_ev_garage_min_current_a
        current_max_a: input_number.ems_ev_garage_max_current_a
        current_step_a: input_number.ems_ev_garage_current_step_a
        phases: input_number.ems_ev_garage_phases
        voltage_v: input_number.ems_ev_garage_voltage_v

    RELAY_SAUNA:
      kind: RELAY
      capabilities:
        can_absorb_w: true
        can_produce_w: false
      policy:
        priority: input_number.ems_relay_sauna_priority
        surplus_allowed: input_boolean.ems_relay_sauna_surplus_allowed
        force_on: input_boolean.ems_relay_sauna_force_on
      adapter:
        enabled: switch.sauna_relay
```

Valinnat:

1. `devices` pysyy map-rakenteena, koska `device_id` on luonnollinen pysyva
   avain writerille, dispatchille, state-muistille ja traceille.
2. `kind` maarittaa device-luokan:
   - `BATTERY`
   - `EV_CHARGER`
   - `RELAY`
3. Device-id:n nimi ei kanna semantiikkaa. `RELAY1`, `RELAY2` ja `EV_CHARGER`
   eivat ole enaa erityisnimiä vaan vain mahdollisia yksittaisia id:ita.
4. `policy.priority` on geneerinen surplus-jarjestyskentta kaikille
   absorboiville deviceille.
5. `policy.surplus_allowed` on geneerinen absorboivalle surplus-kuormalle:
   - sallittu `RELAY`- ja `EV_CHARGER`-deviceille
   - `BATTERY` voi olla primary-device ilman tata kenttaa
6. `policy.force_on` on ensivaiheessa sallittu vain `RELAY`-deviceille.
   EV:lle ei vaiheessa 2 maaritella yleista `force_on`-semantiikkaa, koska EV:n
   hard-off / release-logiikka on eri luonteinen.
7. EV:n low-PV / hard-off -asetukset pysyvat EV-kindin erikoispolitiikkana,
   eivat geneerisena surplus-device-kenttana.
8. `global_config.adjustable_primary_load` ja
   `global_config.adjustable_surplus_load` saavat jatkossakin device-id-arvon,
   mutta niiden sallittujen arvojen ei enaa oleteta olevan vain
   `HOME_BATTERY` / `EV_CHARGER`.

Ensivaiheen siirtymarajat:

1. `HOME_BATTERY` pidetaan edelleen pakollisena kiinteana device-id:na.
   Usean akun tukea ei avata tassa muutoksessa.
2. `0-n` `kind: RELAY` sallitaan.
3. `0-n` `kind: EV_CHARGER` sallitaan.
4. Production-YAML saa edelleen kayttaa nykyista yksinkertaista rakennetta
   yhdella EV:lla ja kahdella releella ilman kayttaytymismuutosta.
5. `global_config.adjustable_surplus_load` voi osoittaa vain yhteen
   device-id:hen kerrallaan. Usean adjustable-device paritys tai round-robin ei
   kuulu tahan vaiheeseen.
6. `global_config.adjustable_primary_load` voi ensivaiheessa osoittaa vain
   `HOME_BATTERY`-deviceen.

Validaatiosaannot vaiheelle 2:

1. `devices`-mapissa on tasan yksi `HOME_BATTERY`, jonka `kind=BATTERY`.
2. `BATTERY`-deviceja voi olla ensivaiheessa vain yksi.
3. `RELAY`-deviceja saa olla `0-n`.
4. `EV_CHARGER`-deviceja saa olla `0-n`.
5. Jokaisella `RELAY`-devicella tulee olla:
   - `capabilities.can_absorb_w=true`
   - `capabilities.can_produce_w=false`
   - `policy.priority`
   - `policy.surplus_allowed`
   - `policy.force_on`
   - `adapter.enabled`
6. Jokaisella `EV_CHARGER`-devicella tulee olla:
   - `capabilities.can_absorb_w=true`
   - `capabilities.can_produce_w=false`
   - `policy.priority`
   - `policy.surplus_allowed`
   - virta-/vaihe-/janniteadapterikentat
7. `global_config.adjustable_surplus_load`, jos asetettu, tulee osoittaa
   olemassa olevaan `EV_CHARGER`- tai myohemmin erikseen sallittuun
   absorboivaan deviceen.
8. `global_config.adjustable_primary_load` tulee osoittaa olemassa olevaan
   `BATTERY`-deviceen, ensivaiheessa kaytannossa `HOME_BATTERY`.

Toteutuspäätos:

1. Vaihe 2 ei muuta viela runtimea. Se lukitsee sen, mihin suuntaan YAML
   contract muutetaan seuraavissa vaiheissa.
2. Ensimmainen toteutus kohdistuu releiden `0-n` tukeen niin, etta usea relay
   voidaan lisata `devices`-mapiin ilman uusia top-level kovakoodattuja id:ita.
3. Monen EV:n tuki rakennetaan saman sopimuksen paalle, mutta sille jaa viela
   erillinen state-/dispatch-tyo vaiheisiin 6-8.

Hyvaksynta:

1. Dokumentti maarittelee yksiselitteisesti, etta `devices` on ainoa
   laitelista ja device-id on pysyva avain.
2. Dokumentti maarittelee erikseen:
   - mita kenttia kaikkien `RELAY`-devicejen tulee sisaltaa
   - mita kenttia kaikkien `EV_CHARGER`-devicejen tulee sisaltaa
   - mita cardinality-saantoja vaihe 3-4 implementaatio alkaa enforceata
3. Dokumentti ei enaa oleta kiinteita id:ita `RELAY1`, `RELAY2` tai
   `EV_CHARGER`, vaikka ne voivat edelleen esiintya yksittaisessa tuotanto-YAML:ssa.

## Vaihe 3: Core device registry

Status: completed

Tavoite:

Poistetaan core-mallista oletus, etta releita on kaksi ja EV-latureita yksi.

Muutos:

1. Lisaa `CoreConfig.devices: dict[str, CoreDeviceConfig]` tai tuple/lista.
2. Sailyta alkuvaiheessa convenience-propertyt:
   - `home_battery`
   - `ev_charger`
   - `relay1`
   - `relay2`
   vain adapterina vanhoille testeille ja vaiheittaiselle migraatiolle.
3. Lisaa helperit:
   - `devices_by_kind(cfg, 'RELAY')`
   - `devices_by_kind(cfg, 'EV_CHARGER')`
   - `surplus_capable_devices(cfg)`
   - `device_config_by_id(cfg, device_id)`

Hyvaksynta:

1. Uusi device registry rakentuu YAML:sta.
2. Vanha 1 EV + 2 relay config tuottaa saman device-listan kuin ennen.
3. Unit-test todistaa, etta kolmas relay nakyy registryssa ilman uutta
   dataclass-kenttaa.

Toteutunut vaihe 3:

1. `CoreConfig` sai uuden `devices`-registryn, joka sisaltaa koko YAML:n
   `ems.devices`-mapin device-configit.
2. `CoreConfig` sai helperit:
   - `device_by_id(device_id)`
   - `devices_by_kind(kind)`
   - `surplus_capable_devices()`
3. Vanhat `home_battery`, `ev_charger`, `relay1`, `relay2` jaiivat viela
   siirtyma-adapteriksi, jotta nykyinen runtime voi jatkaa ilman big bang
   -muutosta.
4. `build_core_config_from_grouped_reader(...)` lukee nyt kaikki YAML:n
   device-entryt registryyn, vaikka runtime kayttaisi viela vain osaa niista.
5. `device_read_model` lukee CoreConfigin device-configit registrysta eika
   enaa rakenteellisesti oleta tasan neljaa laitetta.
6. Ekstra-deviceille, joille runtime-measurement adapteria ei viela ole,
   muodostetaan turvallinen `UNWIRED`-tila eika niita pudoteta pois registrysta.

## Vaihe 4: Runtime entity registry

Status: completed

Tavoite:

Runtime entityt eivat ole enaa littea lista kuten `relay1_force_on` vaan
device-kohtainen registry.

Ehdotettu runtime-malli:

```python
entities = {
    'devices': {
        'EV_MAIN': {
            'enabled': 'switch.ev_main_enabled',
            'current_a': 'number.ev_main_current',
            'surplus_allowed': 'input_boolean.ems_ev_main_surplus_allowed',
        },
        'RELAY_SAUNA': {
            'enabled': 'switch.sauna_relay',
            'surplus_allowed': 'input_boolean.ems_relay_sauna_surplus_allowed',
            'force_on': 'input_boolean.ems_relay_sauna_force_on',
        },
    },
    'policy_decision_trace': 'sensor.ems_policy_decision_trace_pyscript',
}
```

Siirtyma:

1. Pida vanhat aliasit vain testeissa tai compatibility-helperissa, jos tarvitaan.
2. Tuotantoloopit lukevat device-kohtaisia entiteetteja registrylla.

Hyvaksynta:

1. `read_runtime_entities` palauttaa device registry -rakenteen.
2. Contract-test todistaa, etta RELAY3 ja EV2 saavat omat entityt.
3. Tuotantoloopit eivat tarvitse `entities['relay1_force_on']` tyyppisia avaimia.

Toteutunut vaihe 4:

1. `runtime_context.build_runtime_entities_from_grouped_config(...)` rakentaa
   nyt `entities['devices']`-registryn kaikille YAML:n laitteille.
2. Registryssa on kind-kohtaiset runtime-avaimet EV:lle ja releille seka
   `relay_device_ids` / `ev_device_ids`.
3. Vanhat litteat aliasit jaiivat siirtymaksi, mutta policy-, dispatch- ja
   writer-polut lukevat ensisijaisesti device-registrya.
4. Nykyinen raja: uusia litteita top-level aliaksia kuten `actuator_relay3` ei
   lisata; n-device-polun todistus tapahtuu `entities['devices'][device_id]`
   kautta e2e-harnessissa ja contract-testeissa.

## Vaihe 5: Surplus target builder

Status: completed

Tavoite:

`build_surplus_device_targets` ottaa listan deviceja eika rakenna aina kolmea
targettia.

Uusi input:

```python
build_surplus_device_targets(
    devices,
    active_device_ids,
    read_policy_state,
)
```

Tai core-puolella valmiiksi normalisoitu:

```python
SurplusCandidate(
    device_id='RELAY_SAUNA',
    kind='RELAY',
    priority=2,
    threshold_w=2500,
    enabled=True,
    force_on=False,
    active=False,
)
```

Muutos:

1. Targetin `decision_name` ei saa olla vain `ADJUSTABLE/RELAY1/RELAY2`.
2. Kayta joko `device_id` suoraan decision targettina tai erillista
   `display_name`-kenttaa.
3. Poista `device_targets_to_legacy_targets` tai muuta se vain diagnostiseksi
   adapteriksi.

Hyvaksynta:

1. 0 surplus-kuormaa -> dispatch `NOOP`, next target `NONE`.
2. 1 surplus-kuorma -> activation/release toimii.
3. 3+ surplus-kuormaa -> priority order toimii.
4. Force-on ei ohita capabilitya.

Toteutunut vaihe 5:

1. `build_surplus_device_targets(...)` ottaa nyt geneerisen `relay_candidates`
   -listan eika nojaa kiinteasti `RELAY1` / `RELAY2` -parametreihin.
2. `SurplusDeviceTarget` ja `SurplusTargetConfig` sallivat geneerisen
   `decision_name`-kenttan.
3. Core rakentaa target-listan relay-candidateista ja adjustable-device-id:sta.

## Vaihe 6: Policy engine

Status: completed

Tavoite:

`compute_net_zero_engine_outputs` ei ota vastaan `relay1_*` ja `relay2_*`
parametreja, vaan device runtime state -kokoelman.

Uusi input:

```python
compute_net_zero_engine_outputs(..., devices=DeviceRuntimeSnapshot(...))
```

Tai alkuvaiheessa:

```python
surplus_runtime_devices=(
    SurplusRuntimeDevice(device_id='RELAY_SAUNA', active=False, allowed=True, force_on=False),
    ...
)
```

Muutos:

1. `relay1_command` ja `relay2_command` poistuvat core-sopimuksesta tai jaavat
   vain diagnostiseksi legacy-scalariksi vanhalle kahden releen configille.
2. `device_policies` tuotetaan kaikille konfiguroiduille deviceille.
3. EV hard-off -tila sidotaan device-id:hen, jotta usealla EV:lla voi olla oma
   `previous_device_state`.
4. HAEO NET_ZERO combo valitsee device-id:t listasta, ei kovakoodatuista
   `EV_CHARGER/HOME_BATTERY` vaihtoehdoista.

Hyvaksynta:

1. Vanha yhden EV:n ja kahden releen e2e pysyy vihreana.
2. Uusi unit-test kolmella releella tuottaa kolme relay device policya.
3. Uusi unit-test ilman releita tuottaa vain akun ja EV:n device policyt.

Toteutunut vaihe 6:

1. `ems_policy_engine.read_measurements(...)` rakentaa relay- ja EV-state-mapit
   `entities['devices']`-registryssa olevista laitteista.
2. `compute_net_zero_engine_outputs(...)` ottaa sisaan listapohjaiset
   `relay_device_states`, `ev_states` ja `previous_force_on_device_ids`.
3. Device-policyt rakennetaan kaikille registryssa oleville relay- ja
   EV-deviceille; valittu adjustable-EV saa aktiivisen policytason ja muut EV:t
   turvallisen disabled/restore-min -politiikan.
4. Nykyinen raja: usean EV:n tuotantotuki on toistaiseksi "multiple configured,
   one selected". Multi-EV power split ja HAEO usealle EV:lle eivat kuulu tahan
   vaiheeseen.

## Vaihe 7: Dispatch state applier

Status: completed

Tavoite:

Dispatch state applier kasittelee mita tahansa device-id:tä.

Nykyinen ongelma:

1. `ACTIVATE RELAY1` ja `ACTIVATE RELAY2` kasitellaan erikseen.
2. Adjustable-laitteita kasitellaan vain `EV_CHARGER` ja `HOME_BATTERY`
   -joukkona.
3. Trace kirjoittaa viela historiallisia `relay1_on`, `relay2_off` tyyppisia
   write-nimia.

Muutos:

1. `ACTIVATE device_id` -> lisaa `device_id` aktiiviseen joukkoon.
2. `RELEASE device_id` -> poista `device_id` aktiivisesta joukosta.
3. `CLEAR_ALL` -> tyhjenna aktiivinen joukko.
4. Validointi tarkistaa vain, etta device-id loytyy konfiguroiduista
   surplus-capable deviceista.

Hyvaksynta:

1. Applier toimii `RELAY_SAUNA`, `RELAY_BOILER`, `EV_MAIN` nimilla.
2. Trace raportoi `writes: ['activate:RELAY_SAUNA']` tms. ilman relay1/relay2
   erikoisnimia.

Toteutunut vaihe 7:

1. Dispatch-applier paivittaa aktiivisia surplus-deviceja geneerisena
   device-id-listana.
2. Active-lista sailyttaa aktivointijarjestyksen; se ei enaa normalisoidu
   aakkosjarjestykseen.
3. Trace `writes` sailyttaa vanhoille id:ille luettavat nimet, mutta geneeriset
   device-id:t toimivat samassa mallissa.
4. Nykyinen raja: geneerinen dispatch on todistettu 3 releen e2e-polulla;
   canonical trace on device-id-pohjainen ja mahdolliset legacy decision-nimet
   ovat vain compatibility-diagnostiikkaa.

## Vaihe 8: Writerit

Status: completed

Tavoite:

Writer loop kay lapi `device_policies` listan ja kirjoittaa jokaisen device-id:n
sen `kind`-writerilla.

Uusi rakenne:

```python
for policy in device_policies:
    device_cfg = registry[policy.device_id]
    if device_cfg.kind == 'BATTERY':
        write_battery(device_cfg, policy)
    elif device_cfg.kind == 'EV_CHARGER':
        write_ev(device_cfg, policy)
    elif device_cfg.kind == 'RELAY':
        write_relay(device_cfg, policy)
```

Muutos:

1. `_write_ev_actuator` saa `device_cfg`, ei oleta `EV_CHARGER`.
2. `_write_relay_actuator` saa `device_cfg`, ei oleta `RELAY1/RELAY2`.
3. Writer trace muuttuu device-id mapiksi:

```yaml
writes:
  HOME_BATTERY: {...}
  EV_MAIN: {...}
  RELAY_SAUNA: {...}
```

Hyvaksynta:

1. 0 EV:ta ei aiheuta writer-virhetta.
2. 2 EV:ta kirjoitetaan erikseen omiin entityihin.
3. 3 reletta kirjoitetaan erikseen omiin entityihin.
4. Capability guard toimii jokaiselle device-id:lle.

Toteutunut vaihe 8:

1. Writer-looppi iterioi `cfg.devices.values()` ja kirjoittaa kaikki relay- ja
   EV-devicet kindin mukaan.
2. EV- ja relay-writerit lukevat runtime entityt ensisijaisesti
   `entities['devices'][device_id]` -registryssa.
3. Writer-trace julkaisee geneerisen `devices`-payloadin ja sailyttaa
   yhteensopivuusavaimet `ev`, `relay1`, `relay2` vanhalla 1 EV + 2 relay
   tuotantoasetuksella.
4. Nykyinen raja: compatibility-fallbackit `actuator_relay1` ja
   `actuator_relay2` ovat edelleen olemassa vanhalle pinnalle, mutta uudet
   n-device-testit ja tuotantopolku lukevat registry-entityja.

## Vaihe 9: Trace- ja dashboard-sopimus

Status: completed

Tavoite:

Trace ei lupaa enaa kiinteita releita tai yksittaista EV:ta.

Muutos:

1. `surplus_next_target` -> mahdollisesti `surplus_next_device_id`
2. `surplus_device_targets` pysyy listana device-id:lla.
3. `relay1_command`, `relay2_command`, `ev_current_a` ja vastaavat scalarit
   rajataan legacy-diagnostiikaksi tai poistetaan release-breaking change
   -kohdassa.
4. Dashboardit ohjataan lukemaan:
   - `device_policies`
   - `surplus_device_targets`
   - `active_surplus_devices`
   - writer trace device-id map

Hyvaksynta:

1. Dashboard pystyy listaamaan device-politiikat ilman device-id kovakoodausta.
2. Release notes kertoo rikkoutuvat scalar-/trace-kentat.

Toteutunut vaihe 9:

1. `policy_decision_trace` julkaisee `relay_device_ids` ja `ev_device_ids`.
2. `sensor.ems_actuator_writer_trace` julkaisee geneerisen `devices`-mapin,
   jota dashboardit voivat lukea ilman kiinteaa relay1/relay2-oletusta.
3. Scalar- ja legacy-trace-kentat jaivat viela diagnostiikkaan, mutta
   canonical pinta on device-id-pohjainen.

## Vaihe 10: Testit

Status: completed

Tavoite:

Testikattavuus todistaa, etta cardinality ei ole vahingossa palautunut
kiinteaksi.

Uudet testitasot:

1. Config contract:
   - 0 reletta
   - 1 rele
   - 3 reletta
   - 0 EV:ta
   - 2 EV:ta
2. Core unit:
   - surplus target order geneerisella device-listalla
   - capability block geneerisilla device-id:illa
3. Writer unit:
   - writer trace device-id map
   - monta relay writeria
   - monta EV writeria
4. E2E:
   - `net_zero_no_relays_ev_only`
   - `net_zero_three_relays_priority_order`
   - `net_zero_two_ev_one_relay`

Hyvaksynta:

1. `rg -n "RELAY1|RELAY2|EV_CHARGER"` tuotantokoodissa palauttaa vain
   dokumentoidut defaultit, test fixturet tai migration-shimit.
2. Uudet cardinality-testit menevat lapi.
3. Vanha kahden releen tuotanto-YAML pysyy toimivana.

Toteutunut vaihe 10:

1. Unit-testit paivitettiin kattamaan registry-pohjaiset relay- ja EV-device-listat.
2. Contract-testit paivitettiin sallimaan `devices`-registry ja ei-scalar
   runtime-entityt.
3. E2E-suite paivitettiin vastaamaan uutta dispatch-ordering- ja
   policy-trace-semanttiikkaa.
4. 3 releen priority-e2e on oma skenaarionsa ja selected single-EV boundary on
   todistettu contract-/writer-polulla.
5. Taman tyopuunkopion validointi:
   - `python3 -m pytest -q tests/e2e_entity/net_zero_priority_order_quarter tests/e2e_entity/net_zero_priority_order_quarter_3_relays`
   - `python3 -m pytest -q tests/e2e_entity`
   - `python3 -m pytest -q tests`
   kaikki vihreina tuloksella `222 passed, 1 xfailed`.

## Vaihe 11: Dokumentaatio ja migration

Status: pending

Tavoite:

Kayttaja ymmartaa, miten uusi joustava surplus-kuormien config kirjoitetaan.

Dokumentoitavat asiat:

1. Miten rele lisataan.
2. Miten rele poistetaan kokonaan.
3. Miten toinen EV-laturi lisataan.
4. Miten priority ja threshold maaraytyvat.
5. Miten force-on toimii usealla device-id:lla.
6. Miten dashboardien tulee lukea writer trace ja `device_policies`.

Migration-linja:

1. Vanha `RELAY1/RELAY2/EV_CHARGER` config toimii yhtena validina configina.
2. Uusi config ei vaadi noita nimiä.
3. Release-notessa kerrotaan, jos scalar trace -kenttia poistuu.

Hyvaksynta:

1. README:ssa on minimiesimerkki 0 releelle.
2. README:ssa on esimerkki 3 releelle.
3. `EMS_config.yaml` kommentit eivat enaa anna ymmartaa, etta releita on aina 2.

## Vaihe 12: Release-validaatio

Status: pending

Tavoite:

Muutos on release-kelpoinen.

Komennot:

```bash
PYTHONPATH=modules python3 -m pytest -q tests
PYTHONPATH=modules python3 -m pytest -q tests/smoke/test_pyscript_ast_compat.py
./zippaa_ems.sh -o /tmp/ems_surplusloads_flexible_release.zip
```

Hyvaksynta:

1. Koko testsuite menee lapi.
2. Pyscript AST smoke menee lapi.
3. Release-paketti syntyy.
4. Paketti sisaltaa paivitetyn `EMS_config.yaml`-rakenteen.

## Riskit

1. `EmsConfig` scalar-kentat ovat viela laajasti kaytossa, joten suora poisto
   olisi iso muutos.
2. EV hard-off state on nyt yksittaisen EV:n logiikkaa. Usea EV vaatii
   device-id-kohtaisen previous-state mallin.
3. HAEO NET_ZERO combo on suunniteltu kahden kohteen komboksi. Usea EV ja usea
   relay vaatii oman valintasaannon.
4. Dashboardit voivat nojata writer tracen `ev`, `relay1`, `relay2` avaimiin.
5. E2E-testien fixturet kayttavat edelleen kiinteita entity-id -avaimia.

## Suositeltu etenemisjarjestys

Suositus on tehda releiden `0-n` ensin ja vasta sen jalkeen EV-latureiden `0-n`.

Perustelu:

1. Rele on yksinkertainen on/off absorber.
2. EV:ssa on lisaksi selector current, hard-off, low-PV counters ja release
   cadence.
3. Releiden geneeristys pakottaa jo writerin, dispatchin ja target-builderin
   oikeaan listamalliin.
4. Kun listamalli toimii releille, EV-laturien monistus on rajatumpi muutos.

Ensimmainen toteutuspaketti:

1. tee `surplus_loads` / `surplus_candidates` listamalli coreen
2. muuta `build_surplus_device_targets` listapohjaiseksi
3. muuta dispatch state applier geneeriseksi device-id-kasittelijaksi
4. muuta relay writer listapohjaiseksi
5. lisaa e2e `net_zero_three_relays_priority_order`

Toinen toteutuspaketti:

1. muuta EV writer device-id-kohtaiseksi
2. muuta previous-device-state tukemaan useaa EV:ta
3. lisaa e2e `net_zero_two_ev_one_relay`

Kolmas toteutuspaketti:

1. siivoa scalar trace -kentat
2. paivita README ja dashboard-esimerkit
3. aja release-validaatio
