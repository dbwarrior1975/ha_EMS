# Operointi ja vianetsintä

## Päivittäinen seuranta

Seuraa ensisijaisesti:

```text
sensor.ems_policy_diagnostics_pyscript
sensor.ems_device_policies_pyscript
sensor.ems_actuator_writer_trace
sensor.ems_surplus_dispatch_command_pyscript
sensor.ems_dispatch_state_applier_trace
```

Diagnostics on selitys- ja valvontanäkymä. Writerin authoritative input on `sensor.ems_device_policies_pyscript`.

## Canonical publish -tulkinta

```text
Diagnostics reason = interval
DP / DC / PS = false / false / false
```

Ohjaus ei muuttunut; diagnostics julkaistiin heartbeat-välin vuoksi.

```text
Diagnostics reason = canonical_changed
```

Vähintään yksi muuttui:

- DP = Device Policies
- DC = Dispatch Command
- PS = Policy State

## Oirepohjainen runbook

| Oire | Tarkista | Tyypillinen syy | Toimenpide |
|---|---|---|---|
| Runtime ei käynnisty | `config_runtime_ok`, missing fields | template/config mismatch tai puuttuva entity | korjaa ensimmäinen raportoitu schema-polku; älä lisää nollafallbackia |
| Akku jää pieneen targetiin | effective primary, guard, desired target, floor reason | guard, step/ramp tai capability-raja | vertaa requested → desired → final ja tarkista hard ceiling |
| EV ei käynnisty primaryna | `primary_consuming_skipped_by_id`, lifecycle | HARD_OFF, alle minimin tai activation block | korjaa syy tai varmista battery fallback |
| EV ei käynnisty surplus-laitteena | `hard_off_active`, `activation_allowed`, next device, RPC | HARD_OFF ei ole vielä vapautunut tai activation threshold ei täyty | varmista ensin PV-release-counter; tarkista sen jälkeen RPC ja priority |
| Useita surplus-laitteita jää päälle vaikka RPC on negatiivinen | `surplus_active_activation_order`, release power/margin/threshold, freeze | excess ei vielä ylitä uusimman portaan marginaalikorjattua kynnystä tai settle-freeze on aktiivinen | tarkista uusin active device, sen `releasable_power_w` ja `surplus_freeze_until_ts` |
| Rele ei aktivoidu | next device ja candidate stack | korkeampi eligible priority odottaa omaa kynnystään | muuta prioriteettia tai eligibilityä tietoisesti |
| Producer-request näkyy mutta purkua ei tule | effective ceiling ja allocation | SOC/guard/limit tekee ceilingistä 0 | korjaa turvallisuusraja vain, jos fyysisesti perusteltua |
| Writer ei kirjoita | writer trace error code/path | mapping puuttuu tai policy invalidi | korjaa entity registry; diagnostics ei ole command fallback |
| PS-versio kasvaa koko yön | `low_pv_cycles` ja release counter | vanha engine tai muu continuity-state muuttuu | varmista saturation-versio; etsi muuttuva PS-kenttä |
| Diagnostics on aina `canonical_changed` | DP/DC/PS publish-flags | jokin canonical payload vaihtuu | vertaa peräkkäisiä payload-versioita ja sisältöä |
| HAEO ei vaikuta | configured/effective forecast, stale reason | forecast stale tai plan inactive | korjaa fresh source ja timestamp; local NET_ZERO jatkuu fallbackina |

## Primary-feedback-ketju

Kun säätö näyttää väärältä, lue järjestyksessä:

```text
producer_feedback_target_grid_w
producer_feedback_grid_actual_w
producer_feedback_error_w
producer_feedback_current_control_target_w
producer_feedback_desired_control_target_w
primary_consuming_requested_w_by_id
primary_consuming_skipped_by_id
effective_primary_consuming_device_id
primary_consuming_device_target_w
```

Näin erotat laskennan, resolverin ja final policy -rajoituksen toisistaan.

## Surplus-ketju

```text
surplus_rpc_kw
surplus_candidate_stack
surplus_next_device_id
surplus_next_threshold_kw
surplus_dispatch_action
surplus_dispatch_device_id
surplus_active_device_ids
surplus_active_activation_order
surplus_anchor_device_id
surplus_release_mode
surplus_release_power_w
surplus_release_margin_w
surplus_release_threshold_w
surplus_excess_consumption_w
```

Strict priority tarkoittaa, että seuraavan eligible laitteen oma kynnys ratkaisee. Alempaa laitetta ei aktivoida vain siksi, että sen kynnys olisi pienempi.

## Producer-ketju

```text
producer_requested_w
producer_authority_device_ids
producer_effective_hard_ceiling_w_by_id
producer_allocated_w_by_id
producer_skipped_below_min_device_ids
unserved_production_w
```

`unserved_production_w` ei itsessään ole virhe. Se kertoo, että pyydettyä purkua ei voitu toteuttaa capabilityjen ja turvarajojen sisällä.

## Reload ja revision

Helper-arvon muuttuminen päivittää policy revisionin automaattisesti, jos helper on revision-lähdelistassa.

Templateen kovakoodatun arvon muuttamisessa käytä jompaakumpaa:

1. muuta staattista revision-saltia ja reload template, tai
2. reload template sekä Pyscript, jolloin parser-cache tyhjenee

Pelkkä Pyscript-reload ei päivitä template-sensorin vanhaa outputia.

## Recorder-kohina

Diagnostics, writer trace ja dispatch trace voivat toimia tarkoituksellisina heartbeat-sensoreina. Jos historian määrä on ongelma, rajaa ne recorderista ennen kuin poistat valvontajulkaisut.

## Milloin pysäyttää automaattiohjaus

Vaihda `MANUAL_SAFE`-tilaan heti, jos:

- grid- tai battery-merkit näyttävät vääriltä
- writer kirjoittaa väärää entityä
- runtime packet on invalidi
- guard ei reagoi odotetusti
- target ylittää fyysisesti turvallisen rajan
- toinen automaatio kilpailee samoista actuator-entiteeteistä
