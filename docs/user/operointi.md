# EMS-operointi

## Tarkoitus

Tama dokumentti kuvaa nykyisen EMS-runtime-polun valvonnan ja perusvianetsinnan.

## Kanoninen runtime-pinta

Operoinnissa seurataan ensisijaisesti naita entiteetteja:

1. `sensor.ems_device_policies_pyscript`
2. `sensor.ems_surplus_dispatch_command_pyscript`
3. `sensor.ems_policy_state_pyscript`
4. `sensor.ems_active_surplus_devices`
5. `sensor.ems_policy_diagnostics_pyscript`
6. `sensor.ems_actuator_writer_trace`
7. `sensor.ems_dispatch_state_applier_trace`

Kaytannollinen tulkinta:

1. `device_policies` kertoo mita writerille pyydetaan
2. `dispatch_command` kertoo mita surplus-tilalle pyydetaan
3. `policy_state` kantaa yli syklien tarvittavan jatkuvuustilan
4. `active_surplus_devices` kertoo mitka surplus-kohteet ovat aktiivisia
5. `policy_diagnostics` kertoo miksi EMS paatti niin kuin paatti
6. `actuator_writer_trace` kertoo mita writer teki
7. `dispatch_state_applier_trace` kertoo miten dispatch-komento sovellettiin

## Ajastus ja diagnostiikan kuorma

Policy engine laskee paatokset `ems.policy_engine.interval_seconds`-cadencella
kiintean `2s` scheduler-tickin sisalla. `policy_diagnostics` julkaistaan
timer-ajossa heti, jos canonical output tai warning/input-quality-tila muuttuu;
muuten se julkaistaan enintaan
`ems.policy_engine.diagnostics_interval_seconds`-cadencella. Manual- ja E2E-ajot
pakottavat diagnostiikan julkaisun.

Kuormanvahennykseksi Home Assistant recorderista voi rajata diagnostiikan pois:

```yaml
recorder:
  exclude:
    entities:
      - sensor.ems_policy_diagnostics_pyscript
```

Tama ei ole correctness-vaatimus. Canonical outputit ovat
`device_policies`, `dispatch_command` ja `policy_state`.

## Hash-state semantiikka

Kolmen kanonisen output-sensorin `state` on sisaltopohjainen hash:

1. `device_policies` -> `device_policies_hash`
2. `dispatch_command` -> `dispatch_command_hash`
3. `policy_state` -> `policy_state_hash`

Varsinainen payload luetaan attribuuteista. `state` ei ole monotoninen laskuri.

## Tarkeimmat seurattavat entiteetit

### Profiilit

1. `input_select.ems_control_profile`
2. `input_select.ems_goal_profile`
3. `input_select.ems_forecast_profile`
4. `input_select.ems_guard_profile`

### Mittaukset

1. `sensor.victron_mqtt_b827eb48c929_system_0_system_dc_battery_soc`
2. `sensor.victron_mqtt_b827eb48c929_battery_1_battery_min_cell_voltage`
3. `sensor.victron_mqtt_b827eb48c929_battery_1_battery_power`
4. `sensor.average_active_power_2`
5. `sensor.hourly_energy_balance`
6. `sensor.pv_instant_power_2`

### Aktuaattorit

1. `number.victron_mqtt_b827eb48c929_system_0_system_ac_power_set_point`
2. `switch.charger_control`
3. `number.charger_current_level`
4. `switch.relay_1_2`
5. `switch.relay_2_2`

## Surplus-kandidaattipoolin valvonta

Seuraa ensisijaisesti `sensor.ems_policy_diagnostics_pyscript` -attribuutteja:

1. `surplus_candidate_device_ids`: mitka laitteet ovat poolissa
2. `surplus_candidate_stack`: strict-priority-jarjestys
3. `surplus_active_device_ids`: mitka kandidaatit ovat aktiivisia
4. `surplus_next_device_id`: seuraava activation-kohde
5. `surplus_release_device_id`: seuraava release-kohde
6. `device_policies`: lopulliset per-device target/mode/enabled-arvot
7. `device_lifecycle_states`: device-owned hard-off/lifecycle-state

Kandidaattirivista tarkista ainakin `priority`, `threshold_w`,
`threshold_source`, `surplus_dispatch_mode`, `enabled`, `force_on`, `active` ja
`activation_allowed`. `threshold_w` vastaa laitteen `capabilities.max_absorb_w`-arvoa. Kahden EV:n tapauksessa molempien device-id:iden pitaa
nakya poolissa, jos molemmilla on `can_absorb_w=true` ja
`surplus_allowed=true`.

Julkinen policy-diagnostics ei julkaise `selected_ev_device_id`-,
`previous_ev_device_states`- tai scalar `ev_*` compatibility -peileja.
Vianetsinnassa `surplus_candidates`, `device_policies`, `previous_device_states` ja
`device_lifecycle_states` ovat canonical seuranta.

## Troubleshooting

### EMS paattaa, mutta writer ei kirjoita

1. tarkista `sensor.ems_device_policies_pyscript`
2. tarkista `sensor.ems_actuator_writer_trace`
3. tarkista laitteen `policy_source`, `reason` ja `written` writer tracesta

### Surplus-tila ei paivity odotetusti

1. tarkista `sensor.ems_surplus_dispatch_command_pyscript`
2. tarkista `sensor.ems_dispatch_state_applier_trace`
3. tarkista `sensor.ems_active_surplus_devices`
4. tarkista `input_datetime.ems_surplus_freeze_until`

### Halutaan ymmartaa policy-paatoksen syy

Tarkista ensin `sensor.ems_policy_diagnostics_pyscript` attribuutit:

1. `explanation`
2. `dominant_limitation`
3. `surplus_explanation`
4. `surplus_dispatch_action`
5. `surplus_dispatch_device_id`
6. `surplus_candidates`
7. `surplus_active_device_ids`
8. `surplus_next_device_id`
9. `surplus_release_device_id`
10. `device_policies`
11. `device_lifecycle_states`
12. `activation_block_reason`
13. `feedback_protection_active`
14. `feedback_protection_primary_device_id`
15. `feedback_protection_residual_device_id`
16. `feedback_protection_residual_producing`
17. `feedback_protection_residual_power_w`

### EV FORCE_ON ei kaynnista latausta

Tarkista ketju jarjestyksessa:

1. `surplus_candidates`-rivilla EV:n `force_on=true`
2. `surplus_candidates`-rivilla EV:n `activation_allowed=true`
3. `device_policies`-rivilla EV:n `target_w > 0`, `enabled=true` ja syy `ev_force_on`
4. `sensor.ems_actuator_writer_trace`-rivilla action `enable_and_set_current`
5. EV:n enabled/current actuator entityt paivittyvat

Low PV, negatiivinen akun setpoint, liian pieni surplus RPC, `surplus_allowed=false`,
HAEO NET_ZERO -limit tai aktiivinen low-PV HARD_OFF eivät saa perua FORCE_ON-
pyyntoa. Jos HARD_OFF on taustalla aktiivinen, tarkista:

1. `device_lifecycle_states[device_id].hard_off_active=true`
2. `force_on_hard_off_bypass_device_ids` sisaltaa laitteen
3. DevicePolicy on silti `enabled=true`

FORCE_ON ei nollaa HARD_OFF-statea. Kun FORCE_ON poistuu, latched HARD_OFF voi
palata heti voimaan, kunnes normaali consecutive recovery/release -sopimus vapauttaa sen.
Jos FORCE_ON ei silti etene writerille, tarkista aito safety/toteutuskerros:
`guard`, capabilityt, writer-entityt ja laitekohtaiset fyysiset interlockit.

### Primary/residual feedback protection on aktiivinen

`feedback_protection_active=true` tarkoittaa todellista control-topologiaa, jossa
absorboiva primary ja eri tuottava residual-regulaattori voisivat syottaa toisiaan.
Tarkista:

1. `feedback_protection_primary_device_id`
2. `feedback_protection_residual_device_id`
3. `feedback_protection_residual_producing=true`
4. `feedback_protection_residual_power_w < 0`
5. `activation_block_reason=primary_residual_feedback_protection`
6. primary-laitteen `device_lifecycle_states` low-PV/HARD_OFF progression

Historiallista `battery_to_ev_loop_risk`-diagnostiikkaa ei enaa ole.

### Invalidi tai puuttuva runtime-output

1. puuttuva tai invalidi `device_policies` johtaa writerissa safe skip -kayttaytymiseen
2. puuttuva tai invalidi `dispatch_command` johtaa dispatch-applierissa safe `NOOP` -kayttaytymiseen
3. puuttuva tai invalidi `policy_state` ei kaynnista trace-fallbackia, vaan policy engine kayttaa oletusjatkuvuutta

## Poistetut vanhat pinnat

Seuraavia ei tule enaa kayttaa dashboardeissa, automaatioissa tai templateissa:

1. vanha policy-trace-sensori
2. standalone surplus summary -sensorit
3. vanhat surplus active -boolean peilit

Jos Home Assistantissa on viela riippuvuuksia naihin, ne on paivitettava
kanonisiin `device_policies`, `dispatch_command`, `policy_state` ja
`policy_diagnostics` -pintoihin.
