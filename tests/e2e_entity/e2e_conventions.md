# E2E conventions

Paivays: 2026-06-29

Tama tiedosto kokoaa nykyiset e2e-kaytannot yhteen.
Historiallinen suunnitelmamateriaali on poistettu, mutta seuraavat nykyiset
saannot ja guardit jaavat voimaan.

NET_ZERO raw runtime fixtureiden ja `expect_derived`-kaytannon kuvaus:
`tests/e2e_entity/net_zero_fixture_conventions.md`.

## Canonical e2e contract

E2E-testien tulee todistaa nykyista tuotantoketjua:

1. policy engine julkaisee `device_policies`-payloadin ja device-id dispatch
   tracekentat
2. dispatch state applier lukee canonical device trace -komennon
3. writerit lukevat device-policyja
4. HA-actuatorit ja state-entityt paattyvat odotettuun lopputilaan

Skenaario-YAML on vain ihmisluettava fixture-maarittely. Harness materialisoi
jokaisella policy-ajolla kolme strict schema-v3 -pakettia (`policy_config`,
`measurements`, `policy_state`) ja ajaa ne oikeiden
`parse_policy_config_cached()`- ja `parse_tick_frame_v3()`-parserien kautta.
Canonical output- ja diagnostics-sensorit ovat kiinteita koodissa.

## Scenario and harness rules

1. Rakenna harness aina skenaarion omasta `EMS_config.yaml`:sta, ellei testi
   ole nimenomaan root-config contract -testi.
2. Hae globaalit entityt `h.ent`-registrysta.
3. Hae laitekohtaiset entityt `h.device_entity(device_id, field)`-helperilla.
4. Ala importtaa `tests.entity_ids.ENT`:a e2e-polkuun.
5. Yksi harness-step rakentaa strict v3 -paketit, kutsuu
   `ems_policy_engine_loop(trigger_reason='e2e')` ja jatkaa samaan
   dispatch-applier -> writer -ketjuun kuin tuotanto.
6. `policy_diagnostics.runtime_input_contract` on aina
   `direct_tick_frame_v3` aktiivisissa E2E-skenaarioissa.
7. E2E-triggeri julkaisee `policy_diagnostics`-payloadin aina, vaikka
   tuotannon timer-ajossa diagnostiikka olisi throttlatty.

## Preferred assertions

Policy trace:

- `device_policies`
- `surplus_dispatch_action`
- `surplus_device_dispatch_target`
- `surplus_dispatch_device_id`
- `surplus_dispatch_contract == 'device_id_primary'`

Dispatch state applier trace:

- `decision_source == 'device_trace'`
- `device_dispatch_action`
- `device_dispatch_target`
- `device_dispatch_device_id`
- `dispatch_state_contract == 'device_id_primary'`
- `active_surplus_device_ids`
- `writes`
- `freeze_written`

Writer trace:

- `writer_policy_contract == 'device_policy_primary'`
- per-laite `action`, `reason`, `written`
- EV-polussa `target_current_a`, kun selector-muunnos halutaan todistaa

## Guardrails

Naita ei kayteta e2e-kansion behavioral assert -pintana:

- vanhat policy mirror -kentat
- vanhat standalone dispatch mirror -kentat

Jos jokin arvo kuuluu vain alias- tai contract-pintaan, testaa se
siella, ei `tests/e2e_entity/`-kansiossa.
