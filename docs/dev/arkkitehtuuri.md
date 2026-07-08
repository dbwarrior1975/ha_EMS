# EMS-arkkitehtuuri

## Tarkoitus

Tama dokumentti kuvaa nykyisen aktiivisen runtime-arkkitehtuurin. Kuvaus
vastaa tiedostoja `ems_policy_engine.py`, `ems_dispatch_state_applier.py`,
`ems_actuator_writers.py` ja `modules/ems_adapter/runtime_context.py`.

## Kanoninen tuotantoketju

EMS:n tuotantopolku on kolmevaiheinen:

1. policy engine laskee policy-payloadit
2. dispatch state applier paivittaa aktiiviset surplus-tilat
3. actuator writer kirjoittaa lopulliset aktuaattorikomennot

Kanoniset runtime-outputit ovat:

1. `sensor.ems_device_policies_pyscript`
2. `sensor.ems_surplus_dispatch_command_pyscript`
3. `sensor.ems_policy_state_pyscript`

Diagnostiikka-outputit ovat:

1. `sensor.ems_policy_diagnostics_pyscript`
2. `sensor.ems_actuator_writer_trace`
3. `sensor.ems_dispatch_state_applier_trace`

`policy_diagnostics` on vain selitys- ja debug-pinta. Sita ei saa kayttaa
command/state-lahteena.

`runtime.*` entity-id:t ovat kayttajan konfiguroitavia read target -pintoja.
`policy_outputs` ja `diagnostics_outputs` eivat ole enaa kayttajakonfiguraatiota,
vaan EMS:n kiinteita canonical output bus- ja diagnostics-pintoja.

## Kokonaiskuva

```mermaid
flowchart LR
    HA[Home Assistant entityt] --> RC[runtime_context.py\nentity registry + CoreConfig]
    RC --> P[ems_policy_engine.py]
    P --> DP[device_policies]
    P --> DC[dispatch_command]
    P --> PS[policy_state]
    P --> PD[policy_diagnostics]
    DC --> D[ems_dispatch_state_applier.py]
    D --> ACTIVE[active_surplus_devices\n+ surplus_freeze_until]
    D --> DTRACE[dispatch_state_applier_trace]
    DP --> W[ems_actuator_writers.py]
    ACTIVE --> W
    W --> ACT[actuator_* entityt]
    W --> WTRACE[actuator_writer_trace]
```

## Komponentit

### Policy Engine

Tiedosto: `ems_policy_engine.py`

Vastuut:

1. lukee `CoreConfig`-konfiguraation runtime_contextin kautta
2. lukee profiilit ja mittaukset
3. arvioi guard-tilan
4. laskee `NetZeroOutputs`-ulostulon
5. julkaisee `device_policies`, `dispatch_command` ja `policy_state`
6. julkaisee `policy_diagnostics`-selityspayloadin throttlatulla timer-cadencella

Ajastusmalli:

1. Pyscript scheduler kutsuu policy-engine tickia kiinteasti `2s` valein
2. `ems.policy_engine.interval_seconds` maarittaa minimi elapsed intervalin
3. kevyt skip-polku ei lue configia, runtime-contextia tai entityja
4. runtime-inputit luetaan oikean policy-ajon alussa grouped-configin entity-id:ista
5. config interval -muutos voi tulla voimaan seuraavassa oikeassa ajossa tai manual/reload-ajossa
6. raw runtime entityt eivat ole enaa policy-enginen `@state_trigger`-sopimus

Julkaisusopimus:

1. `device_policies` sensorin `state` on `device_policies_hash`
2. `dispatch_command` sensorin `state` on `dispatch_command_hash`
3. `policy_state` sensorin `state` on `policy_state_hash`
4. `policy_diagnostics` julkaistaan timer-ajossa heti canonical outputin tai warning/input-quality-tilan muuttuessa, muuten enintaan `ems.policy_engine.diagnostics_interval_seconds`-cadencella
5. manual- ja E2E-ajot julkaisevat `policy_diagnostics`-payloadin aina
6. varsinainen payload on attribuuteissa

### Geneerinen surplus-kandidaattipooli

`NET_ZERO`-enginen surplus-polku ei valitse ensin yhta adjustable-laitetta. Pooli
rakennetaan kaikista konfiguroiduista laitteista, jotka tayttavat laitekohtaisen
sopimuksen:

1. `capabilities.can_absorb_w = true`
2. `policy.surplus_allowed = true`
3. runtime availability/enable-ehdot sallivat osallistumisen
4. capability- tai lifecycle-tila ei tee targetista kelvotonta

Kandidaatin authoritative policy-kentat ovat `priority` ja
`surplus_dispatch_mode`. Aktivointikynnys johdetaan aina fyysisesta
`capabilities.max_absorb_w`-arvosta. Tuetut dispatch-modet ovat `max_absorb` ja
`fixed`. Core builder/allocator ei kysy laitteen kindia eika legacy-selectorin
arvoa. EV-, relay- ja muut absorb-capable kandidaatit ovat samassa
strict-priority-jarjestyksessa.

`primary_device_id` sailyy singular control role -kasitteena. Primary-only-
regulaattoria ei dispatchata toista kertaa poolista. Nykyinen laite, joka tukee
seka primary- etta residual-regulaatiota, voi sailyttaa tuotannon overlap-
semantiikan, jos sen oma `surplus_allowed` policy sallii osallistumisen; lopullinen
`DevicePolicy`-omistus pysyy yhtena.

Lifecycle on device-owned: `previous_device_states[device_id]` on authoritative.
Jokainen eligible `uses_hard_off_lifecycle=true` -laite arvioidaan itsenaisesti,
myos silloin kun toinen EV on aktiivisempi tai korkeammalla prioriteetilla.
Consecutive release -laskurit etenevat ja nollautuvat device-kohtaisesti.

### Primary/residual feedback protection ja FORCE_ON

NET_ZERO ei kayta enaa yleista `low PV + negatiivinen battery setpoint` -porttia
EV-targetin nollaamiseen. Feedback-suojaus aktivoituu vain todellisessa
control-topologiassa, jossa kaikki seuraavat ehdot tayttyvat:

1. valittu `primary_device_id` tukee primary-regulaatiota ja voi absorboida tehoa
2. valittu `residual_regulator_device_id` on eri laite
3. residual-regulaattori tukee residual-regulaatiota ja voi tuottaa tehoa
4. primary-laitteen low-energy/PV-ehto on aktiivinen
5. valittu residual-regulaattori tuottaa oikeasti tehoa (`measured_power_w < 0`)
6. primary-laitteella ei ole eksplisiittista `force_on=true` aktivointipyyntoa

Policy-merkitys on `primary_residual_feedback_protection`. Suojaus on
capability- ja ownership-vetoinen; generic paatos ei haarauta `EV_CHARGER`-kindilla.
Battery-mittauksen signitulkinta kuuluu adapter/read-model -tasolle.

`force_on=true` on eksplisiittinen kayttajan aktivointipyynto ja sen precedence
on NET_ZERO-optimointia korkeampi. Capabilityt validilla EV:lla FORCE_ON saa
positiivisen `DevicePolicy.target_w`-arvon ja `enabled=true`; `max_absorb`-EV:lla
target on `capabilities.max_absorb_w`.

FORCE_ON ohittaa optimizer-owned gate -kerroksen:

1. surplus activation threshold
2. `surplus_allowed`-eligibility
3. low-PV/HARD_OFF-lifecycle activation gate
4. HAEO NET_ZERO plan/limit
5. primary/residual feedback-protection block
6. dispatch clear/release -paatos siltä osin kuin se yrittäisi nollata pakotetun EV-targetin

HARD_OFF-state sailyy silti device-owned lifecycle-storessa. FORCE_ON on effective
activation bypass, ei lifecycle reset. Kun FORCE_ON poistuu, edelleen aktiivinen
HARD_OFF saa heti uudelleen auktoriteetin normaalilla consecutive release -sopimuksella.

Aito safety/toteutuskerros pysyy FORCE_ONia korkeammalla. `GuardProfile.DEGRADED`,
puuttuva absorb-capability, invalidi writer/entity-polku tai muu fyysinen
safety-interlock voi edelleen estaa aktuaattorikomennon.

Lifecycle-request on eksplisiittinen: feedback-suojattu primary kasitellaan
`activation_blocked=true`-tilassa, jolloin low-PV persistence voi edeta kohti
HARD_OFFia ilman historiallista battery/EV-riskibooleanin sivuvaikutusta. FORCE_ON
voi samanaikaisesti bypassata taman optimizer-owned tilan effective policyssa;
lifecycle-historiaa ei tuhota.

Generic feedback diagnostics:

1. `activation_block_reason`
2. `feedback_protection_active`
3. `feedback_protection_primary_device_id`
4. `feedback_protection_residual_device_id`
5. `feedback_protection_low_energy_active`
6. `feedback_protection_residual_producing`
7. `feedback_protection_residual_power_w`
8. `force_on_active_device_ids`
9. `force_on_hard_off_bypass_device_ids`

Historiallista `battery_to_ev_loop_risk`-kenttaa ei julkaista execution- eika
diagnostics-sopimuksessa.

Generic diagnostics:

1. `surplus_candidate_device_ids`
2. `surplus_candidate_stack`
3. `surplus_active_device_ids`
4. `surplus_next_device_id`
5. `surplus_release_device_id`

`adjustable_surplus_load`, `adjustable_surplus_activation_w` ja
`surplus_adjustable_device_id` on poistettu aktiivisesta config/runtime/diagnostics-
sopimuksesta. Julkinen policy-diagnostics ei julkaise `selected_ev_device_id`-,
`previous_ev_device_states`- tai scalar `ev_*` compatibility -peileja. Canonical
seuranta tapahtuu `device_policies`, `surplus_candidates`, `previous_device_states`
ja `device_lifecycle_states` -kentilla.

### Dispatch State Applier

Tiedosto: `ems_dispatch_state_applier.py`

Vastuut:

1. lukee dispatch-paatoksen vain `dispatch_command`-sensorista
2. paivittaa `active_surplus_devices`-tilan
3. kirjoittaa `surplus_freeze_until`-ajan
4. julkaisee `dispatch_state_applier_trace`-diagnostiikan

Jos `dispatch_command` puuttuu tai on invalidi, kayttaytyminen on eksplisiittinen
safe `NOOP`.

### Actuator Writer

Tiedosto: `ems_actuator_writers.py`

Vastuut:

1. lukee laitekohtaiset policyt vain `device_policies`-sensorista
2. kirjoittaa akun setpointin
3. kirjoittaa EV-laturin enabled/current-arvot
4. kirjoittaa releiden on/off-tilat
5. julkaisee `actuator_writer_trace`-diagnostiikan

Writer ei lue `policy_diagnostics`-payloadia fallbackina.

## Runtime entity registry

Tiedosto: `modules/ems_adapter/runtime_context.py`

Kanoniset runtime-avaimet:

1. `device_policies`
2. `dispatch_command`
3. `policy_state`
4. `policy_diagnostics`
5. `actuator_writer_trace`
6. `dispatch_state_applier_trace`
7. `active_surplus_devices`
8. `surplus_freeze_until`

Legacy-trace- ja standalone surplus summary -avaimia ei exposeerata aktiivisessa
registryssa.

Grouped `EMS_config.yaml` -tiedoston olemassaolo-, luku- ja signature-I/O ajetaan
Pyscriptin `@pyscript_executor`-wrapperilla erillisessa threadissa. Runtime-cache ja
validation pysyvat samoina, mutta Home Assistantin main event loopissa ei tehda
synkronista `Path.read_text()`- tai `os.stat()`-filesystem-I/O:ta.

## Konfiguraatiosopimus

Kanoninen grouped config -sopimus erottaa read targetit ja output-pinnat:

1. `runtime.*` entity-id:t ovat kayttajan konfiguroitavia read target -pintoja
2. canonical policy output -sensorit ovat kiinteasti koodissa
3. canonical diagnostics-outputit ovat kiinteasti koodissa
4. `ems.policy_outputs` ja `ems.diagnostics_outputs` hylataan eksplisiittisesti

## Diagnostiikkamoduuli

Tiedosto: `modules/ems_core/diagnostics/policy_diagnostics.py`

Diagnostiikkapayload sisaltaa selitys- ja seurantakenttia kuten:

1. `device_policies`
2. `surplus_dispatch_action`
3. `surplus_dispatch_device_id`
4. `surplus_dispatch_contract`
5. `surplus_candidates`
6. `surplus_candidate_device_ids`
7. `surplus_active_device_ids`
8. `surplus_next_device_id`
9. `surplus_release_device_id`
10. `surplus_explanation`
11. `previous_device_states`
12. `device_lifecycle_states`
13. `config_source`
14. `policy_output_contract`

P0-cleanup poistaa legacy surplus-/selected-EV-tuottajat ennen diagnostiikkaprojektiota.
Diagnostiikkaprojektion jaljelle jaava blacklist koskee vain myohempien P1/P2-vaiheiden
viitta legacy-avainta. Dispatch- ja policy-state -sensorisopimukset sailyvat erillisina
eika cleanup muuta execution-polun omistajuutta.

Se ei ole erillinen command-bus eika state-bus.
