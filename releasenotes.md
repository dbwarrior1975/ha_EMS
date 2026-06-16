# Release Notes

Paivays: 2026-06-16

## Scope

Tama release lanceeraa EMS:n, jossa:

1. grouped `EMS_config.yaml` on kanoninen konfiguraatio
2. device model on tuotantopolun ensisijainen malli
3. writerien kanoninen ohjausrajapinta on `device_policies`
4. EV writerin kanoninen input on `target_w`

## Breaking changes

Seuraavat Home Assistant -entityt poistuvat eivatka paivity enaa:

1. `sensor.ems_policy_battery_target_w_pyscript`
2. `sensor.ems_policy_ev_current_a_pyscript`
3. `sensor.ems_policy_relay1_command_pyscript`
4. `sensor.ems_policy_relay2_command_pyscript`
5. `sensor.ems_net_zero_surplus_dispatch_decision_pyscript`
6. `input_boolean.ems_surplus_adjustable_active`
7. `input_boolean.ems_surplus_relay1_active`
8. `input_boolean.ems_surplus_relay2_active`

Jos Home Assistant -automaatiot, dashboardit tai template-sensorit ovat
nojaaneet naihin entityihin, ne on paivitettava.

## Canonical replacements

Kayta jatkossa ensisijaisesti naita:

1. `sensor.ems_policy_decision_trace_pyscript`
2. `sensor.ems_device_policies_pyscript`
3. `sensor.ems_active_surplus_devices`
4. `sensor.ems_previous_device_state`
5. `input_datetime.ems_surplus_freeze_until`

Konkreettinen tulkinta:

1. yksittaisen laitteen ohjauspyynto luetaan `device_policies`-payloadista
2. dispatch-paatokset luetaan `policy_decision_trace`-attribuuteista:
   - `surplus_device_dispatch_action`
   - `surplus_device_dispatch_target`
   - `surplus_device_dispatch_device_id`
3. aktiivinen surplus-tila luetaan `active_surplus_devices.device_ids`
   -attribuutista

## Configuration

Kanoninen tuotantokonfiguraatio on:

- `/config/EMS_config.yaml`

`EMS_GROUPED_CONFIG_PATH` voi edelleen overrideata polun, mutta oletuspolku on
nyt osa normaalia tuotantopolkua.

`EMS_config.yaml` on nyt pakollinen. Jos tiedosto puuttuu tai ei validoidu,
EMS ei fallbackaa compatibility-defaultteihin, vaan runtime epäonnistuu
näkyvästi.

## Behavioral notes

1. writerit eivat lue legacy `policy_*` -sensoreita fallbackina
2. dispatch state applier ei yllapida legacy `surplus_*_active` -booleaneja
3. dispatch trace on device-id-pohjainen, ei legacy boolean -pohjainen
4. EV:n amperit ovat edelleen adapteri- ja actuator-rajalla mukana, mutta
   core/writer contract on wattipohjainen

## Upgrade note for HA users

Paivita mahdolliset automaatiot ja dashboardit pois vanhoista policy- ja
surplus-active entityista ennen tai viimeistaan taman releasen yhteydessa.

Suositeltu uusi tarkastelupinta:

1. `sensor.ems_policy_decision_trace_pyscript`
2. `sensor.ems_device_policies_pyscript`
3. `sensor.ems_active_surplus_devices`
4. `sensor.ems_actuator_writer_trace`
5. `sensor.ems_dispatch_state_applier_trace`
