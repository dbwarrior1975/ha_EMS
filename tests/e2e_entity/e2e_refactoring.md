# E2E conventions

Paivays: 2026-06-29

Tama tiedosto korvaa aiemman migration aikana kertyneen refaktorointimuistion.
Historiallinen suunnitelmamateriaali on poistettu, mutta seuraavat nykyiset
saannot ja guardit jaavat voimaan.

## Canonical e2e contract

E2E-testien tulee todistaa nykyista tuotantoketjua:

1. policy engine julkaisee `device_policies`-payloadin ja device-id dispatch
   tracekentat
2. dispatch state applier lukee canonical device trace -komennon
3. writerit lukevat device-policyja
4. HA-actuatorit ja state-entityt paattyvat odotettuun lopputilaan

## Scenario and harness rules

1. Rakenna harness aina skenaarion omasta `EMS_config.yaml`:sta, ellei testi
   ole nimenomaan root-config contract -testi.
2. Hae globaalit entityt `h.ent`-registrysta.
3. Hae laitekohtaiset entityt `h.device_entity(device_id, field)`-helperilla.
4. Ala importtaa `tests.entity_ids.ENT`:a e2e-polkuun.

## Preferred assertions

Policy trace:

- `policy_output_contract == 'device_policy_primary'`
- `device_policies`
- `surplus_device_dispatch_action`
- `surplus_device_dispatch_target`
- `surplus_device_dispatch_device_id`
- `surplus_device_dispatch_contract == 'device_id_primary'`

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

Jos jokin arvo kuuluu vain compatibility- tai contract-pintaan, testaa se
siella, ei `tests/e2e_entity/`-kansiossa.
