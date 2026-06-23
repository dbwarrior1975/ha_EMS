# Final Cleaning

Paivitetty: 2026-06-21

Taman dokumentin tarkoitus on seurata refaktoroinnin jalkeista loppusiivousta.
Tavoitetila on yksiselitteinen tuotantolinja:

`EMS_config.yaml -> runtime_context -> CoreConfig/runtime registry -> device_policies -> writer`

## Vaiheet

| Vaihe | Status | Sisalto |
|---|---|---|
| 1. Dokumenttien nykytilasiivous | done | poista migration-kieli ja vanhentunut current-state-kuvaus |
| 2. Parity-/compat-sanaston uudelleennimeaminen | done | kavenna tai nimea neutraalisti parity-/compat-apurit |
| 3. Trace-scalarien tarkoituksen lukitseminen | done | pidetaan scalarit diagnostisina, ei writer-sopimuksena |
| 4. EV-ampeerien rajaus adapteritasolle | done | tarkenna dokumentaatio ja rajaa `current_a` adapteri-/trace-kayttoon |
| 5. Testien migration-jaanteiden arviointi | done | poista vain migration-arvoa suojaavat testit |
| 6. Lopullinen release-validaatio | done | aja koko testsuite ja release-paketointi |

## Vaihe 1

Status: done

Tehty:

1. `EMS_config.yaml`-header siivottu pois migration- ja fallback-testikielesta
2. `README.md` paivitetty kuvaamaan kanoniset surplus/state-pinnat
3. `arkkitehtuuri.md` paivitetty poistamaan virheellinen nykytilakuva

Hyvaksynta:

1. grouped config on dokumentoitu kanoniseksi tuotantokonfiguraatioksi
2. `policy_*`- ja `surplus_*_active` -pintoja ei esitetä aktiivisena tuotantototuutena
3. dispatch state authority on kuvattu `active_surplus_devices`-mallilla

## Muistiin

Vaiheen 1 jalkeen repoon saa jaada historiallisia viittauksia release-notes- tai
taustadokumentteihin, kunhan ne eivat esita vanhaa mallia nykytilana.

## Vaihe 2

Status: done

Tehty:

1. `legacy_parity_index` nimetty muotoon `runtime_alias_index`
2. `LegacyParityAlias` nimetty muotoon `RuntimeAlias`
3. `compat_cfg` nimetty muotoon `scalar_cfg`
4. `grouped_legacy_view` nimetty muotoon `grouped_scalar_view`
5. `_read_compat_config()` nimetty muotoon `_read_scalar_config_view()`
6. `_populate_core_config_compat_fields()` nimetty muotoon `_populate_core_config_derived_fields()`
7. vastaavat unit- ja contract-testit paivitetty

Hyvaksynta:

1. aktiivinen runtime-polku ei kayta enaa harhaanjohtavaa parity-/compat-sanastoa noissa apureissa
2. `PYTHONPATH=modules python3 -m pytest -q tests/unit/test_config_loader.py tests/contract/test_grouped_config_contract.py tests/contract/test_grouped_config_runtime_parity.py`
3. tulos: `28 passed`

## Vaihe 3

Status: done

Tehty:

1. `policy_decision_trace` sai eksplisiittiset kentat:
   - `policy_trace_scalar_role = diagnostic_scalar`
   - `policy_trace_canonical_contract = device_policies`
2. `tests/unit/test_decision_trace.py` paivitetty varmistamaan nuo
3. `README.md`, `operointi.md` ja `arkkitehtuuri.md` paivitetty kuvaamaan
   scalar-kentat diagnostisiksi trace-kentiksi

Hyvaksynta:

1. writerin kanoninen sopimus on dokumentoitu `device_policies`-payloadiksi
2. trace-scalareita ei esitetä writerin ensisijaisena ohjausrajapintana


## Vaihe 4

Status: done

Tehty:

1. `DevicePolicy` ei enaa kanna `current_a`-kenttaa
2. `policy_decision_trace.device_policies` ei enaa julkaise EV:n ampeeripeilia
3. EV:n ampeerit rajattiin dokumentaatiossa scalar-traceen, writer-traceen ja actuator-adapteriin
4. e2e- ja unit-testit paivitettiin lopettamaan `device_policies.current_a`-assertit

Hyvaksynta:

1. EV:n kanoninen writer-sopimus on `device_policies[*].target_w`
2. writerin toteutunut ampeeriarvo loytyy `actuator_writer_trace.ev.target_current_a`-kentasta
3. `current_a` ei enaa esiinny canonical `device_policies`-payloadissa


## Vaihe 5

Status: done

Tehty:

1. poistettu vanha `tests/e2e_entity/e2e_refactor_handover.md`, joka oli pelkka historiallinen migraatiohandover
2. nimetty testejä uudelleen niin, etteivat ne esita aktiivista adapteri- tai runtime-kayttoa migration- tai legacy-kielen kautta
3. pidetty parity-, alias- ja dispatch-mapping-testit tallella niilta osin kuin ne suojaavat edelleen aktiivista runtime-adapteria

Hyvaksynta:

1. testipuun nimet kuvaavat nykyista grouped-config- ja device-policy-mallia aiempaa tarkemmin
2. puhdas migraatiohandover ei ole enaa osa aktiivista testipuuta
3. koko testsuite menee lapi nykyisella steady-state-rakenteella


## Vaihe 6

Status: done

Tehty:

1. ajettu koko testsuite
2. ajettu Pyscript AST -smoke
3. ajettu release-paketointi `zippaa_ems.sh`-skriptilla

Hyvaksynta:

1. `PYTHONPATH=modules python3 -m pytest -q tests`
   - tulos: `193 passed, 1 xfailed`
2. `PYTHONPATH=modules python3 -m pytest -q tests/smoke/test_pyscript_ast_compat.py`
   - tulos: `7 passed`
3. `./zippaa_ems.sh -o /tmp/ems_final_cleaning_release.zip`
   - onnistui

Paketti:

- `/tmp/ems_final_cleaning_release.zip`
- sisaltaa:
  - `ems_policy_engine.py`
  - `ems_dispatch_state_applier.py`
  - `ems_actuator_writers.py`
  - `modules/ems_adapter`
  - `modules/ems_core`
  - `requirements.txt`
  - `EMS_config.yaml`

Huomio:

- pytest antoi vain `.pytest_cache`-kirjoitukseen liittyvat varoitukset read-only-ymparistossa
- ainoa `xfail` on tarkoituksellinen tulevan HAEO combo -semantiikan testi
