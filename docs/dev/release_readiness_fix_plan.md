# Release Readiness Fix Plan

Paivitetty: 2026-06-22

## Tarkoitus

Tama dokumentti muuttaa katselmointipalautteen toteutuskelpoiseksi
korjaussuunnitelmaksi ennen seuraavaa kayttajavalmista releasea.

Nykyinen arvio:

1. n-relepolku on production-ready candidate.
2. n-EV-polku on vain selected-single boundary -tasolla.
3. release-artifact ja kayttajadokumentaatio eivat viela ole valmiit uudelle
   kayttajalle.

Tavoiteltu release-tila:

1. `0-n` `kind: RELAY` toimii configissa, policyssa, dispatchissa ja writerissa.
2. `0-n` `kind: EV_CHARGER` on rehellisesti tuettu ainakin boundarylla:
   useampi konfiguroitu, yksi valittu; 0 EV ei kaada runtimea.
3. HAEO NET_ZERO -rajaus on joko korjattu custom EV device-id:lle tai
   eksplisiittisesti dokumentoitu rajoitteeksi.
4. ZIP-artifact on self-contained testattava paketti.
5. Uusi kayttaja loytaa minimiohjeet releen lisaamiseen, releiden poistamiseen,
   toisen EV:n lisaamiseen ja dashboard/trace-pinnan lukemiseen.

## Katselmoinnin paahavainnot

Hyvin toimivat asiat:

1. `CoreConfig.devices`, runtime `entities['devices']`, relay runtime-state map,
   surplus targetit, dispatch state ja writer-loop ovat siirtyneet aidosti
   device-id-malliin n-releiden osalta.
2. `actuator_relay3`-ongelmaa ei korjattu lisaamalla uutta pysyvaa top-level
   aliasia. RELAY3 loytyy oikein `entities['devices']['RELAY3']`-polusta.
3. Dispatch-applier kasittelee `ACTIVATE`, `RELEASE` ja `CLEAR_ALL` geneerisena
   device-id-listana.
4. Writer-loop iteroi `cfg.devices.values()` ja kirjoittaa relay/EV-laitteet
   device-id:n mukaan.
5. Multi-EV-rajauksena "multiple configured, one selected" on oikea
   ensimmainen boundary.

Releasea estavat tai heikentavat asiat:

1. 0 EV validoituu config-contractissa, mutta core/runtime ei kesta sita.
2. HAEO NET_ZERO -polku kayttaa yha literal `EV_CHARGER` -device-id:ta.
3. `compute_net_zero_engine_outputs(...)` signature kantaa yha pakollisia
   `relay1_*` ja `relay2_*` legacy-parametreja.
4. Runtime entity registry pudottaa tyhjat `relay_device_ids` ja `ev_device_ids`
   avaimet, vaikka nollalaite on eksplisiittinen tila.
5. Release ZIP ei ole self-contained testattava artifact:
   `example_EMS_config.yaml` puuttuu ja mukana on `*.Zone.Identifier`-sivutiedostoja.
6. Kayttajadokumentaatiosta puuttuu n-device migration- ja minimikonfiguraatio-ohje.

## Toteutusjarjestys

Jarjestys on valittu niin, etta pienet P0-rajapintakorjaukset tehdään ennen
laajempia runtime- ja release-validointitoita.

| Vaihe | Prioriteetti | Status | Sisalto |
|---|---:|---|---|
| 1. Eksplisiittiset tyhjat device-id-listat | P0 | pending | `relay_device_ids=()` ja `ev_device_ids=()` aina runtime registryyn |
| 2. 0 EV core/runtime path | P0 | pending | 0 EV ei saa kaataa enginea, policya tai writeria |
| 3. 0 EV / no relay e2e- ja contract-testit | P0 | pending | todista 0-device-boundaryt testeilla |
| 4. Release artifact self-consistency | P0 | pending | `example_EMS_config.yaml` ja ZIP-sisallon siivous |
| 5. HAEO NET_ZERO EV device-id -linja | P1 | pending | korjaa custom EV tai dokumentoi rajoite nakyvasti |
| 6. Kayttajadokumentaatio ja migration | P0 | pending | lisaamis-/poisto-/dashboard-ohjeet uudelle kayttajalle |
| 7. Puhdas release-validointi | P0 | pending | testit puhtaasta unzipista ja smoke/paketointi |
| 8. Core API legacy-signature deprecation | P2 | pending | tee vasta release-blockereiden jalkeen, ellei muutos ole pieni shim |

## Vaihe 1: eksplisiittiset tyhjat device-id-listat

Status: pending

Ongelma:

`build_runtime_entities_from_grouped_config(...)` palauttaa device registryn,
mutta pudottaa tyhjat `relay_device_ids` ja `ev_device_ids` avaimet pois
falsy-suodatuksessa.

Tavoite:

Runtime registry palauttaa aina:

```python
relay_device_ids = ()
ev_device_ids = ()
```

myos silloin, kun kyseisen kindin deviceja ei ole.

Miksi ensin:

1. Muutos on pieni ja pieniriskinen.
2. Se selkeyttaa heti 0 EV / 0 relay -testien fixtureita.
3. Se erottaa eksplisiittisen "0 devicea" -tilan missing-key-virheesta.

Hyvaksynta:

```bash
python3 -m pytest -q tests/contract/test_runtime_entity_registry_contract.py
```

## Vaihe 2: 0 EV core/runtime path

Status: pending

Ongelma:

Config-loader sallii 0 `EV_CHARGER` -devicea, mutta core-polku voi silti laskea
EV-min/max/current/step-arvoja `None`-arvoista. Katselmoinnissa tama nakyi
`TypeError`-virheena `compute_net_zero_engine_outputs(...)`-polussa.

Tavoite:

1. Jos `devices_by_kind('EV_CHARGER') == ()`, engine ei laske EV hard-off-,
   min/max-current-, step- tai power-arvoja.
2. `device_policies` ei sisalla EV-politiikkoja.
3. Surplus-targetit muodostuvat akusta ja releista ilman EV-oletusta.
4. Writer ei yrita kirjoittaa EV-actuatoria, jos EV-deviceja ei ole.
5. `adjustable_surplus_load=HOME_BATTERY` toimii ilman EV:ta.

Toteutuslinja:

1. Erota selected EV -resoluutio omaksi guardatuksi poluksi.
2. Palauta EV-derived arvot turvallisina nollina tai `None` vain sellaisiin
   trace-kenttiin, joita ei syoteta `int(...)`/`float(...)`-muunnoksiin.
3. Tee core-outputista eksplisiittisesti EV-vapaa silloin, kun EV-lista on tyhja.

Hyvaksynta:

```bash
python3 -m pytest -q tests/unit/test_engine.py tests/unit/test_surplus_device_targets.py
python3 -m pytest -q tests/contract/test_grouped_config_runtime_parity.py
```

## Vaihe 3: 0 EV / no relay testikattavuus

Status: pending

Lisattavat testit:

1. Contract:
   `test_zero_ev_config_runs_policy_without_ev_policy`
2. E2E:
   `tests/e2e_entity/net_zero_no_ev_relays_only`
3. E2E:
   `tests/e2e_entity/net_zero_no_relays_ev_only`

Miksi P0:

1. 0 EV ja 0 relay ovat suoraan `0-n`-lupauksen reunatapauksia.
2. Vaiheet 1 ja 2 voivat muuten nayttaa vihreilta ilman e2e-todistetta.
3. Uuden kayttajan release-valmius riippuu juuri naista boundaryista.

Hyvaksynta:

```bash
python3 -m pytest -q tests/contract/test_grouped_config_runtime_parity.py
python3 -m pytest -q tests/e2e_entity/net_zero_no_ev_relays_only
python3 -m pytest -q tests/e2e_entity/net_zero_no_relays_ev_only
```

## Vaihe 4: release artifact self-consistency

Status: pending

Ongelma:

Katselmoinnin ZIP ei lapaisy koko testisuitea sellaisenaan, koska
`example_EMS_config.yaml` puuttui. Lisäksi mukana oli Windowsin
`*.Zone.Identifier`-sivutiedostoja.

Tavoite:

1. Paata onko `example_EMS_config.yaml` release-artifactin virallinen osa.
2. Jos testit tarvitsevat sita, se on mukana paketissa.
3. Jos sita ei haluta releaseen, testit eivat saa riippua siita.
4. ZIP ei sisalla `*.Zone.Identifier`, `__pycache__`, `.pytest_cache`,
   vanhoja tuotantozippeja tai muita sivutuotteita.
5. Puhdas unzipattu paketti lapisee samat testit kuin tyopuu.

Hyvaksynta:

```bash
./zippaa_ems.sh -o /tmp/ems_release_candidate.zip
python3 -m pytest -q tests
```

Lisaksi erillisessa temp-hakemistossa:

```bash
unzip /tmp/ems_release_candidate.zip -d /tmp/ems_release_candidate
cd /tmp/ems_release_candidate
python3 -m pytest -q tests
```

## Vaihe 5: HAEO NET_ZERO EV device-id -linja

Status: pending

Ongelma:

`modules/ems_core/integrations/haeo_net_zero_plan.py` kayttaa literal
`EV_CHARGER` -device-id:ta. Custom EV device-id:t kuten `EV_MAIN` ja
`EV_GARAGE` eivat siis ole aidosti tuettuja HAEO NET_ZERO -polussa.

Paatosvaihtoehdot:

1. Korjaa HAEO NET_ZERO kayttamaan valittua EV device-id:ta.
2. Dokumentoi rajoite: HAEO NET_ZERO tukee toistaiseksi vain canonical
   `EV_CHARGER` -id:ta.

Suositus:

Korjaa polku valittuun EV device-id:hen, koska muu runtime on jo siirtynyt
device-id-malliin. Jos korjaus osoittautuu isoksi, dokumentoi rajoite
selkeasti releaseen ja avaa jatkotyo erikseen.

Hyvaksynta korjaukselle:

```bash
python3 -m pytest -q tests/unit/test_engine.py
python3 -m pytest -q tests/e2e_entity/haeo_02_net_zero_homebattery_primary_ev_adjustable
```

Hyvaksynta dokumentointirajaukselle:

1. `docs/user/README.md` tai `docs/user/operointi.md` kertoo HAEO NET_ZERO
   custom-EV-rajoitteen.
2. `docs/user/releasenotes.md` kertoo saman upgrade note -tasolla.

## Vaihe 6: kayttajadokumentaatio ja migration

Status: pending

Ongelma:

Uusi kayttaja ei viela saa riittavaa ohjetta siihen, miten n-device-konfiguraatio
kirjoitetaan ja mita Home Assistant -helper-entiteetteja tarvitaan.

Lisattavat dokumentit tai osiot:

1. `docs/user/EMS_parametrointi_guide.md`
   - miten rele lisataan
   - miten kaikki releet poistetaan
   - miten toinen EV lisataan
   - miten `priority`, `threshold_w`, `max_absorb_w` ja capabilityt vaikuttavat
2. `docs/user/operointi.md`
   - miten dashboard lukee `device_policies`, `surplus_device_targets`,
     `active_surplus_devices` ja writer-tracen `devices`-mapin
3. `docs/user/releasenotes.md`
   - n-device boundaryt
   - HAEO NET_ZERO custom-EV-rajaus tai korjattu tuki
   - release-artifactin tiedostot ja migration note
4. `README.md`
   - lyhyt docs-layout ja minimilinkit uudelle kayttajalle

Hyvaksynta:

1. Uusi kayttaja nakee yhdesta paikasta minimiesimerkit:
   - 0 reletta
   - 3 reletta
   - 0 EV
   - 2 EV, yksi valittu
2. Dokumentit eivat vaita, etta multi-EV power split olisi tuettu.
3. Dokumentit eivat vaita, etta HAEO NET_ZERO tukee custom EV device-id:ta,
   ellei vaihe 5 korjaa sita.

## Vaihe 7: puhdas release-validointi

Status: pending

Lopullinen validointiketju:

```bash
python3 -m pytest -q tests/unit/test_core_config.py tests/unit/test_device_read_model.py tests/unit/test_surplus_device_targets.py tests/unit/test_dispatch_state_applier.py tests/unit/test_writer_semantics.py tests/unit/test_engine.py
python3 -m pytest -q tests/contract
python3 -m pytest -q tests/e2e_entity
python3 -m pytest -q tests/smoke/test_pyscript_ast_compat.py
python3 -m pytest -q tests
./zippaa_ems.sh -o /tmp/ems_release_candidate.zip
```

Artifact-tarkistus:

```bash
unzip -l /tmp/ems_release_candidate.zip | rg "example_EMS_config.yaml|Zone.Identifier|__pycache__|\\.pytest_cache|ems_production_.*\\.zip"
```

Hyvaksynta:

1. Koko testsuite menee lapi tyopuussa.
2. Smoke menee lapi.
3. ZIP syntyy.
4. ZIP ei sisalla sivutuotteita.
5. ZIP sisaltaa kaikki testien edellyttamat config-esimerkit.
6. Puhdas unzipattu paketti lapisee koko testsuiten.

## Vaihe 8: core API legacy-signature deprecation

Status: pending

Ongelma:

`compute_net_zero_engine_outputs(...)` ottaa yha pakollisina legacy-parametreina
`relay1_*`, `relay2_*`, `prev_relay1_force_on` ja `prev_relay2_force_on`.
Tama on ristiriidassa tavoitteen kanssa, jossa core saa device runtime snapshotin.

Tavoite:

1. Uusi ensisijainen API ottaa `relay_device_states`, `ev_states` ja
   `previous_force_on_device_ids`.
2. Legacy `relay1_*`/`relay2_*`-parametrit ovat adapteritasolla tai optional
   compatibility-shimissa.
3. Tuotantopolku ei tarvitse legacy-parametreja.

Jarjestys:

1. Tee vasta release-blockereiden jalkeen.
2. Poikkeus: jos muutos osoittautuu pieneksi optional-shimiksi, sen voi ottaa
   mukaan aiemmin ilman, etta vaihe 7 viivastyy.

Riskit:

1. Testeja on todennakoisesti paljon kiinni nykyisessa signaturessa.
2. Muutos ei saa sotkea P0-release-validaatiota.

Hyvaksynta:

```bash
rg -n "relay1_surplus_allowed|relay2_surplus_allowed|prev_relay1_force_on|prev_relay2_force_on" modules ems_*.py tests
python3 -m pytest -q tests/unit/test_engine.py tests/e2e_entity
```

## Definition of Done

Release voidaan kutsua kayttajavalmiiksi, kun:

1. 0 EV ei kaada core-, policy-, dispatch- tai writer-polkuja.
2. 0 reletta ja 0 EV:ta nakyvat runtime registryssa eksplisiittisina tyhjina
   device-id-listoina.
3. 3 releen e2e, no-relay e2e ja no-EV e2e ovat vihreita.
4. Multi-EV selected-single boundary on todistettu contractilla ja/tai e2e:lla.
5. HAEO NET_ZERO custom-EV-kayttaytyminen on joko korjattu tai dokumentoitu
   rajoitteeksi.
6. Release ZIP on self-contained ja puhdas.
7. `docs/user` kertoo uudelle kayttajalle, miten n-device-konfiguraatio otetaan
   kayttoon ilman handoff-dokumenttien lukemista.

