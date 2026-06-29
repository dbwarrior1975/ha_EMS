# Release Notes

Paivays: 2026-06-22

## Scope

Tama release lanceeraa EMS:n, jossa:

1. grouped `EMS_config.yaml` on kanoninen konfiguraatio
2. tuotantoruntime rakentaa `CoreConfig`-mallin grouped konfiguraatiosta
3. device model on tuotantopolun ensisijainen malli
4. writerien kanoninen ohjausrajapinta on `device_policies`
5. EV writerin kanoninen input on `target_w`

## N-device support

Tama release tukee:

1. yhta `HOME_BATTERY`-akkua
2. `0-n` `kind: RELAY` -laitetta configissa, policyssa, dispatchissa ja writerissa
3. `0-n` `kind: EV_CHARGER` -laturia konfiguroituna
4. usean EV:n selected-single boundarya: yksi EV valitaan aktiiviseksi adjustable-laitteeksi kerrallaan
5. 0 EV -configia
6. 0 relay -configia
7. custom device-id:ita, esimerkiksi `RELAY_SAUNA`, `RELAY_BOILER`, `EV_MAIN` ja `EV_GARAGE`

Tama release ei toteuta:

1. multi-EV simultaneous power splitia
2. round-robinia usealle EV:lle
3. useaa `HOME_BATTERY`-akkua
4. kaikkien aiempien core API -parametrien poistoa

HAEO NET_ZERO custom EV -polku tukee selected EV device-id:ta unit-tasolla.
EMS-internal HAEO combo -semantiikan laajemmat muutokset ovat jatkotyota siltä
osin kuin niita ei ole katettu nykyisilla e2e-testeilla.

## Breaking changes

Seuraavat Home Assistant -entityt poistuvat eivatka paivity enaa:

1. vanhat policy mirror -sensorit
2. vanha standalone surplus dispatch -mirrorisensori
3. vanhat surplus active -boolean peilit

Jos Home Assistant -automaatiot, dashboardit tai template-sensorit ovat
nojaaneet naihin entityihin, ne on paivitettava.

Lisaksi erillinen peilinakyma on poistettu aktiivisesta runtime-polusta.
Tuotantokoodi nojaa `CoreConfig`-malliin ja device-registryyn.

## Canonical replacements

Kayta jatkossa ensisijaisesti naita:

1. `sensor.ems_policy_decision_trace_pyscript`
2. `sensor.ems_device_policies_pyscript`
3. `sensor.ems_active_surplus_devices`
4. `sensor.ems_previous_device_state`
5. `sensor.ems_actuator_writer_trace`
6. `input_datetime.ems_surplus_freeze_until`

Konkreettinen tulkinta:

1. yksittaisen laitteen ohjauspyynto luetaan `device_policies`-payloadista
2. dispatch-paatokset luetaan `policy_decision_trace`-attribuuteista:
   - `surplus_device_dispatch_action`
   - `surplus_device_dispatch_target`
   - `surplus_device_dispatch_device_id`
   - `surplus_device_targets`
3. aktiivinen surplus-tila luetaan `active_surplus_devices.device_ids`
   -attribuutista
4. writerin toteuma luetaan `sensor.ems_actuator_writer_trace` -sensorin
   `devices`-mapista

Vanhat `relay1`, `relay2`, `ev`, `RELAY1`, `RELAY2`, `EV_CHARGER` ja
`ADJUSTABLE`-nimet voivat nakya trace-diagnostiikassa tai yksittaisina
validin device-id:n esimerkkeina. Uusia dashboardeja tai automaatioita ei tule
rakentaa niiden varaan canonical integraatiosopimuksena.

## Configuration

Kanoninen tuotantokonfiguraatio on:

- `/config/EMS_config.yaml`

`EMS_GROUPED_CONFIG_PATH` voi edelleen overrideata polun, mutta oletuspolku on
nyt osa normaalia tuotantopolkua.

`EMS_config.yaml` on nyt pakollinen. Jos tiedosto puuttuu tai ei validoidu,
EMS ei fallbackaa vanhoihin oletuksiin, vaan runtime epäonnistuu
näkyvästi.

## Behavioral notes

1. writerit eivat lue poistettuja `policy_*` -sensoreita fallbackina
2. dispatch state applier ei yllapida poistettuja `surplus_*_active` -booleaneja
3. dispatch trace on device-id-pohjainen, ei vanha boolean-pohjainen
4. EV:n amperit ovat edelleen adapteri- ja actuator-rajalla mukana, mutta
   core/writer contract on wattipohjainen
5. useampi EV voi olla konfiguroituna, mutta vain selected EV saa aktiivisen
   adjustable-policyroolin yhdella policy-kierroksella

## Upgrade note for HA users

Paivita mahdolliset automaatiot ja dashboardit pois vanhoista policy- ja
surplus-active entityista ennen tai viimeistaan taman releasen yhteydessa.

Suositeltu uusi tarkastelupinta:

1. `sensor.ems_policy_decision_trace_pyscript`
2. `sensor.ems_device_policies_pyscript`
3. `sensor.ems_active_surplus_devices`
4. `sensor.ems_actuator_writer_trace`
5. `sensor.ems_dispatch_state_applier_trace`
