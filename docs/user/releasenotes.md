## 2026-07-09 — L3 per-device EV execution cleanup

L3 poistaa NET_ZERO-coren implicit selected-EV execution pivotin ilman policy-objective redesignia.

Muutokset:

1. primary on optional explicit `primary_device_id`; tyhja primary on validi surplus-only-topologia
2. first-primary-capable ja first-EV fallbackit on poistettu NET_ZERO-coresta
3. EV lifecycle lasketaan per device-ID canonical state-mapista
4. jokaiselle EV:lle rakennetaan oma `DevicePolicy`; explicit primary EV saa erillisen role-polun
5. `hard_off_active` on device-owned latch ja sailyttaa policy-auktoriteetin myos ilman surplus-eligibilitya
6. FORCE_ON precedence, latchin sailyminen ja FORCE_ON release -> HARD_OFF palautuminen sailyvat
7. surplus `fixed` tarkoittaa canonicalisti `min_absorb_w`; `max_absorb` tarkoittaa `max_absorb_w` kaikille device-kindeille
8. direct-runtime `selected_ev_context_by_id` ja selected-EV metrics/intermediates on poistettu
9. no-primary E2E, device-order permutation ja multi-EV per-device regressiot lukitsevat uuden execution-sopimuksen
10. HAEO:n scalar one-selected-EV plan-selection sailyy tarkoituksella L4-velkana

---

## 2026-07-08 — Legacy compatibility cleanup P2

P2 viimeistelee primary-role -nimimigraation ilman control-policy redesignia.

Muutokset:

1. canonical config/core/runtime-nimi on kaikkialla `primary_device_id`
2. direct-runtime wire contract on versionoitu `direct_tick_frame_v3`:ksi ja packet `schema_version=3`:ksi
3. policy-config packet julkaisee `config.primary_device_id`; v2-paketti ei kelpaa v3-parserille
4. fyysinen HA-helper `input_select.ems_adjustable_primary_load` saa sailyä arvon lahteena; vain sisainen semanttinen avain muuttui
5. config loader, CoreConfig, runtime context, NET_ZERO engine, HAEO plan, testit, fixturet ja docs kayttavat canonical nimea
6. viimeinen diagnostics legacy blacklist poistettiin; canonical `primary_device_id` julkaistaan suoraan
7. ei dual-readia eika rinnakkaista truth sourcea; ZIP ja template on tarkoitus deployata yhdessa

---

## 2026-07-08 — Legacy compatibility cleanup P1

P1 poistaa P0:n jalkeen jaljelle jaaneet migration-/selected-device-yhteensopivuuspinnat
ilman control-policy redesignia.

Muutokset:

1. HAEO NET_ZERO julkaisee vain `haeo_nz_device_limits_w[device_id]` -mapin; battery/EV scalar limit -peilit on poistettu
2. `HaeoNetZeroPlan` kayttaa per-device limit-mapia ilman `battery_limit_w`/`ev_limit_w`-mirror-kenttia
3. legacy device bridge -laskurit ja diagnostics-metriikat on poistettu; lazy device materialization sailyy toteutusdetaljina
4. `CoreConfig.ev_charger` ja direct/config-view selected-EV compatibility -nakyma on poistettu; callerit kayttavat `device_by_id()`/kind-kyselyita
5. policy-wrapperin selected-EV active -silta on poistettu; core saa canonical `active_surplus_device_ids` -joukon
6. testiharnessin `__legacy__.*` derived-input override -polku on poistettu; NET_ZERO E2E syottaa tuotantoa vastaavat raw runtime -inputit
7. diagnostics legacy blacklistissa oli P1:n jalkeen vain P2:ssa poistettava legacy primary-role -avain
8. `activation_block_reason` sailyy tarkoituksella singular-muodossa, koska nykyisessa arkkitehtuurissa on yksi `primary_device_id` ja yksi primary/residual feedback-protection -pari

---

## 2026-07-07 — Legacy compatibility cleanup P0

P0 poistaa redundantit execution/output-yhteensopivuuskerrokset ilman policy-algoritmin
uudelleensuunnittelua.

Muutokset:

1. selected-EV scalar output -peilit ja `previous_ev_device_states` on poistettu
2. policy-state persistoi vain `previous_device_states[device_id]` -kartan
3. legacy surplus-nimialiaset on poistettu; canonical `surplus_*`-kentat tuotetaan suoraan
4. dispatch-command ja state applier kayttavat vain `device_id`-identiteettia
5. `surplus_targets_by_device_id` on poistettu; targetit luetaan `device_policies`-rakenteesta
6. redundantit diagnostics contract -markerit on poistettu kokonaan
7. diagnostics legacy blacklist pieneni 38 avaimesta viiteen P1/P2-avaimeen; P1 jatkaa taman yhteen P2-avaimeen
8. FORCE_ON/HARD_OFF-precedence, feedback protection, strict priority ja multi-EV writer routing sailyvat

---

# Release Notes

## 2026-07-07 — FORCE_ON precedence simplification

FORCE_ON-semanttiikka on suoraviivaistettu vastaamaan eksplisiittista kayttajan
tahdonilmaisua: laite halutaan paalle, vaikka NET_ZERO-tavoite ei toteutuisi.

Muutokset:

1. EV FORCE_ON ohittaa low-PV/HARD_OFF-lifecycle activation gaten
2. HARD_OFF-statea ei nollata; se sailyy taustalla ja palaa voimaan heti FORCE_ONin poistuessa
3. FORCE_ON ohittaa surplus-thresholdin ja `surplus_allowed` optimizer-eligibilityn
4. FORCE_ON ohittaa HAEO NET_ZERO -plan-limitin EV-targetille
5. FORCE_ON ohittaa primary/residual feedback-optimointiblokin; pakotettu EV-target pysyy kiinteana capability-rajoitettuna kuormana
6. dispatch clear/release ei saa nollata pakotettua EV-targetia
7. `DevicePolicy.reason=ev_force_on` tekee precedence-paatoksen nakyvaksi
8. diagnostics julkaisee `force_on_active_device_ids` ja `force_on_hard_off_bypass_device_ids`
9. uusi E2E todistaa aktiivisen HARD_OFFin bypassin writerille ja actuatorille asti seka HARD_OFF-auktoriteetin palautumisen FORCE_ONin poistuessa
10. `guard=DEGRADED`, puuttuva capability ja muut aidot safety/toteutusesteet sailyvat FORCE_ONia korkeammalla

---

## 2026-07-07 — EV FORCE_ON + primary/residual feedback protection refactor

Tama release korjaa tilanteen, jossa EV:n `force_on=true` nakyi kandidaatti-
diagnostiikassa mutta low PV + negatiivinen akun setpoint nollasi lopullisen EV-
policyn ennen writeria.

Muutokset:

1. yleinen `battery_to_ev_loop_risk` execution gate on poistettu
2. ei-HARD_OFF EV FORCE_ON on eksplisiittinen aktivointipyynto ja etenee
   positiiviseen `DevicePolicy.target_w`-arvoon, `enabled=true`-tilaan ja writerin
   `enable_and_set_current`-toimintoon
3. primary-EV:n FORCE_ON targetia ei ylikirjoiteta stepped-regulation targetilla;
   `max_absorb`-polku sailyttaa eksplisiittisen targetin
4. todellinen feedback-suojaus perustuu `primary_device_id` / valittuun
   `residual_regulator_device_id` -ownershipiin, capabilityihin, low-energy-ehtoon
   ja residual-regulaattorin todelliseen negatiiviseen tehoon
5. eksplisiittinen FORCE_ON ohittaa feedback-suojauksen; taman valireleasen
   alkuperainen active-HARD_OFF precedence korvattiin myohemmin saman paivan
   `FORCE_ON precedence simplification` -muutoksella ylla
6. lifecycle kayttaa eksplisiittista `activation_blocked`-semantiikkaa, joten
   primary->residual feedback-tilanne voi edeta low-PV persistence -laskureilla
   kohti HARD_OFFia ilman legacy-booleanin sivuvaikutusta
7. diagnostics julkaisee `activation_block_reason`- ja `feedback_protection_*`-kentat
8. historiallista `battery_to_ev_loop_risk`-kenttaa ei julkaista diagnosticsissa
9. uusi EV FORCE_ON E2E todistaa koko runtime -> candidate -> DevicePolicy -> writer
   -> actuator -ketjun
10. uusi primary/residual E2E todistaa topology-aware protectionin ja lifecycle-
    progression; relay FORCE_ON, strict priority, direct-v2, multi-EV ja writer
    contract sailyvat ennallaan

Historiallinen huomio: taman valireleasen alkuperainen sopimus antoi aktiiviselle
HARD_OFFille FORCE_ONia korkeamman precedence-tason. Ylla kuvattu myohempi
`FORCE_ON precedence simplification` korvaa taman: FORCE_ON bypassaa HARD_OFF-
activation gaten, mutta ei nollaa lifecycle-statea tai release-laskureita.

---

## 2026-07-07 — Pyscript event-loop config I/O fix

Tama maintenance-release poistaa `EMS_config.yaml`-tiedoston synkronisen filesystem-I/O:n
Home Assistantin main event loopista.

Muutokset:

1. grouped-config `Path.exists()` / `Path.read_text()` ajetaan `@pyscript_executor`-threadissa
2. runtime config-signaturen `os.stat()` ajetaan `@pyscript_executor`-threadissa
3. grouped-config cache-, validation- ja direct-v2-semantics sailyvat ennallaan
4. uusi Pyscript smoke-contract hylkaa runtime-filesystem-kutsut, joita ei ole executor-suojattu

Tavoite on poistaa Home Assistantin `Detected blocking call to read_text/open inside the event loop` -varoitukset muuttamatta EMS-policykaytosta.

---

## 2026-07-06 — Surplus candidate pool + max_absorb threshold cleanup

Tama release poistaa selected-single-EV / singular adjustable-surplus -rajan ja
viimeistelee surplus-aktivointikynnyksen yhden totuuslahteen mallin.

Muutokset:

1. useampi EV voi olla samassa surplus-kandidaattipoolissa
2. kandidaatin eligibility perustuu `can_absorb_w + surplus_allowed` -sopimukseen
3. device-owned `priority` ja `surplus_dispatch_mode` ohjaavat jarjestysta ja target-strategiaa
4. surplus activation threshold on aina `device.capabilities.max_absorb_w`
5. erillinen `policy.activation_threshold_w` on poistettu ja vanhat paketit hylataan fail-closed
6. `adjustable_surplus_load` ja `adjustable_surplus_activation_w` on poistettu aktiivisesta global config/direct-v2 -sopimuksesta
7. dispatch diagnostics kayttaa device-ID:ita; `ADJUSTABLE`-paatosalias on poistettu
8. public diagnostics -projektio poistaa `surplus_device_*`-duplikaatit, `selected_ev_device_id`-, `previous_ev_device_states`- ja scalar `ev_*` compatibility -peilit
9. kandidaattidiagnostiikka julkaisee vain `surplus_candidates`-rivit ilman redundanttia `decision_name`-kenttaa
10. per-device allocation tuottaa jokaiselle EV:lle oman `DevicePolicy`-tuloksen
11. hard-off lifecycle etenee `previous_device_states[device_id]`-tilassa itsenaisesti
12. strict-priority, relay behavior, EV-primary stepped regulation, battery residual/guard, HAEO ja writer contract on sailyttetty

Compatibility:

1. `primary_device_id` sailyy singular primary-role -valintana
2. vanhat `adjustable_surplus_load`, `adjustable_surplus_activation_w` ja device-policy `activation_threshold_w` -syotteet hylataan direct-v2:ssa eksplisiittisesti
3. sisaiset dispatch-command- ja policy-state -sensorisopimukset sailyvat execution/persistence-kaytossa, mutta niiden compatibility-peileja ei julkaista policy-diagnosticsissa

Ei kuulu scopeen: proportional multi-EV power split, EV round-robin,
strict-priority-vs-first-feasible redesign tai multi-primary control.

---

Paivays: 2026-07-01

## Scope

Tama release viimeistelee policy output -siivouksen:

1. grouped `EMS_config.yaml` on kanoninen konfiguraatio
2. runtime-outputit ovat `device_policies`, `dispatch_command` ja `policy_state`
3. diagnostiikka-outputit ovat `policy_diagnostics`, `actuator_writer_trace` ja `dispatch_state_applier_trace`
4. writer ja dispatch-applier eivat fallbackaa vanhoihin trace-sensoreihin

## Breaking changes

Seuraavat poistuvat aktiivisesta sopimuksesta:

1. `policy_outputs.decision_trace`
2. `policy_outputs.actuator_writer_trace`
3. `policy_outputs.dispatch_state_applier_trace`
4. standalone surplus summary -sensorit
5. vanha `sensor.ems_policy_decision_trace_pyscript`

Jos Home Assistant -automaatiot, dashboardit tai template-sensorit ovat
nojaaneet naihin, ne on paivitettava.

## Canonical outputs

Kayta jatkossa ensisijaisesti naita:

1. `sensor.ems_device_policies_pyscript`
2. `sensor.ems_surplus_dispatch_command_pyscript`
3. `sensor.ems_policy_state_pyscript`
4. `sensor.ems_policy_diagnostics_pyscript`
5. `sensor.ems_active_surplus_devices`
6. `sensor.ems_actuator_writer_trace`
7. `sensor.ems_dispatch_state_applier_trace`
8. `input_datetime.ems_surplus_freeze_until`

## Hash-state contract

Kanonisten output-sensorien `state` on sisaltopohjainen hash:

1. `device_policies` -> `device_policies_hash`
2. `dispatch_command` -> `dispatch_command_hash`
3. `policy_state` -> `policy_state_hash`

Payload luetaan attribuuteista. `state` ei ole counter eika versionumero
monotonisessa merkityksessa.

## Configuration

`runtime.*` entity-id:t ovat edelleen kayttajan konfiguroitavia read target
-pintoja. `policy_outputs` ja `diagnostics_outputs` eivat ole enaa
kayttajakonfiguraatiota, vaan kiinteita canonical output- ja
diagnostics-surfaceja koodissa.

## Upgrade note for HA users

Paivita mahdolliset automaatiot ja dashboardit pois vanhoista policy-trace- ja
surplus-summary-entiteeteista. Suositeltu uusi tarkastelupinta on:

1. `sensor.ems_policy_diagnostics_pyscript`
2. `sensor.ems_device_policies_pyscript`
3. `sensor.ems_surplus_dispatch_command_pyscript`
4. `sensor.ems_policy_state_pyscript`
5. `sensor.ems_active_surplus_devices`
6. `sensor.ems_actuator_writer_trace`
7. `sensor.ems_dispatch_state_applier_trace`
