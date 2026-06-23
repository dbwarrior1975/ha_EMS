# E2E scenario YAML migration plan

Paivays: 2026-06-23

## Tarkoitus

Taman suunnitelman tavoite on poistaa `tests/e2e_entity/`-testien riippuvuus
root-tason `EMS_config.yaml`:sta. Lopputilassa jokainen e2e-skenaario ajaa
aidosti oman skenaariokohtaisen grouped YAML -konfiguraationsa varassa.

Nykyinen ongelma:

1. `QuarterScenarioHarness` voi jo asettaa `EMS_GROUPED_CONFIG_PATH`:in
   skenaariokohtaiseen `tests/e2e_entity/<scenario>/EMS_config.yaml` -tiedostoon.
2. Testien helperit lukevat silti `tests/entity_ids.py`:n globaalia `ENT`-mapia.
3. `tests/entity_ids.py` rakentaa `ENT`:n import-aikana root `EMS_config.yaml`:sta.
4. Jos skenaariossa on device, jota root-configissa ei ole, esimerkiksi
   `RELAY3`, helperit kuten `device_entity('RELAY3', 'enabled')` hajoavat ennen
   kuin skenaariokohtainen YAML vaikuttaa runtimeen.

## Lopputila

E2E-testin ainoa konfiguraatiototuus on sen oma scenario YAML.

Tavoiteltu malli:

```python
h = QuarterScenarioHarness(
    project_root=project_root,
    scenario_dir=Path(__file__).parent,
)

h.ent['devices']['RELAY3']['enabled']
h.device_entity('RELAY3', 'enabled')
```

Root `EMS_config.yaml` ei saa vaikuttaa:

1. e2e-testin device registryyn
2. e2e-testin helperien entity-id-hakuihin
3. e2e-testin seedaukseen
4. e2e-testin odotusarvojen entity-id:ihin

Root `EMS_config.yaml` saa jatkossa kuulua vain:

1. production-defaultin dokumentointiin
2. smoke-testeihin
3. config contract- ja parity-testeihin, joissa root-config on nimenomainen testikohde

## Vaihe 0: nykytilan kartoitus

Tavoite: tiedetaan tarkasti, missa root `ENT` -riippuvuus on.

Tehtavat:

1. Listaa kaikki e2e-kansiot, joissa on oma `EMS_config.yaml`.
2. Listaa kaikki e2e-kansiot, joissa ei viela ole omaa `EMS_config.yaml`:ia.
3. Listaa `tests/e2e_entity/`-osumat, jotka importtaavat `ENT` suoraan:

```bash
rg -n "from tests.entity_ids import ENT|import ENT|ENT\\[" tests/e2e_entity
```

4. Listaa helperit, jotka kayttavat globaalia `ENT`:a:

```bash
rg -n "ENT\\[|ENT\\.get|device_entity\\(" tests/e2e_entity tests/entity_ids.py
```

Hyvaksynta:

1. Tulokset on kirjattu PR:n kuvaukseen tai erilliseen checklistiin.
2. Tiedetaan, mitka testit ovat jo scenario YAML -valmiita ja mitka tarvitsevat fixture-konfigin.

## Vaihe 1: lisae harnessiin scenario entity registry

Tavoite: `QuarterScenarioHarness` omistaa testin entity registry -totuuden.

Muutos:

1. Kun harness ratkaisee `self.grouped_config_path`, se lataa saman YAML:n
   registryksi.
2. Harness asettaa:
   - `self.grouped_config`
   - `self.ent`
3. `self.ent` rakennetaan `build_runtime_entities_from_grouped_config(...)`
   -funktiolla samasta configista, jota runtime kayttaa.

Tavoiteltu toteutustapa:

```python
from ems_adapter.config_loader import load_grouped_ems_config
from ems_adapter.runtime_context import build_runtime_entities_from_grouped_config

self.grouped_config = load_grouped_ems_config(self.grouped_config_path)
self.ent = build_runtime_entities_from_grouped_config(self.grouped_config)
```

Hyvaksynta:

1. `h.grouped_config_path` osoittaa scenario YAML:iin, kun scenario YAML on olemassa.
2. `h.ent['devices']` sisaltaa scenario YAML:n laitteet, myos rootista puuttuvat device-id:t.
3. `tests/entity_ids.py` ei ole mukana harnessin scenario registry -rakennuksessa.

## Vaihe 2: lisae harnessiin entity helperit

Tavoite: testien ei tarvitse importata globaalia `device_entity(...)`-helperia.

Lisattavat metodit:

```python
def entity(self, key):
    return self.ent[key]

def device_entity(self, device_id, field):
    device = (self.ent.get('devices') or {}).get(device_id) or {}
    entity_id = device.get(field)
    if not entity_id:
        raise KeyError(
            f"missing scenario runtime entity for device_id={device_id} field={field} "
            f"config={self.grouped_config_path}"
        )
    return entity_id
```

Lisae tarvittaessa lyhyt alias:

```python
h.dev('RELAY3', 'enabled')
```

Hyvaksynta:

1. `h.device_entity('RELAY3', 'enabled')` toimii 3-releen skenaariossa, vaikka root configissa ei ole `RELAY3`:a.
2. Virheviesti kertoo scenario config -polun, jos entity puuttuu.
3. Uudet testit eivat tarvitse `tests.e2e_entity.refactored_runner.device_entity` -funktiota.

## Vaihe 3: paivita e2e seed-helperit harness-aware-malliin

Tavoite: seedaus ei hae entity-id:ita globaalista `ENT`:sta.

Nykyiset ongelmakohdat:

1. `seed_active_surplus_devices(...)` kayttaa `ENT` ja `device_entity(...)`.
2. `seed_previous_device_state(...)` ja muut helperit voivat kirjoittaa entityja root registrylla.
3. `_configured_device_order(...)` muodostaa jarjestysta root `ENT`:n perusteella.

Muutoslinja:

1. Muuta helperien ensisijaiseksi registryksi `h.ent`.
2. Kayta `h.device_entity(...)` helperia device-kohtaisiin entityihin.
3. Pida vanha globaali `ENT` vain fallbackina lyhyen siirtyman ajan, jos helperia kutsutaan ilman harnessia.
4. Kirjaa fallback deprecatediksi ja lisae fail-fast guard siirtyman lopussa.

Esimerkkitavoite:

```python
def seed_active_surplus_devices(h, *, active_device_ids=(), relay_states=None, ev_states=None, ...):
    ent = h.ent
    seed = {
        ent['active_surplus_devices']: ','.join(_configured_device_order(h, active_device_ids)),
        ent['actuator_relay1']: actuator_relay1,
        ent['actuator_relay2']: actuator_relay2,
        ent['actuator_ev_enabled']: actuator_ev_enabled,
    }
    for device_id, enabled in (relay_states or {}).items():
        seed[h.device_entity(device_id, 'enabled')] = enabled
    h.set_entities(seed)
```

Hyvaksynta:

1. `seed_active_surplus_devices(... relay_states={'RELAY3': True})` toimii ilman root `RELAY3`:a.
2. E2E-helperit eivat lue `tests.entity_ids.ENT`:a device-kohtaisiin hakuihin.
3. Aktiivisten device-id:iden jarjestys tulee scenario YAML:n device registrysta ja aktiivisesta pinosta, ei root configista.

## Vaihe 4: migroi testit kansio kerrallaan

Tavoite: e2e-testien lukupinta vaihtuu globaalista `ENT`:sta scenario harnessiin.

Migraatioyksikko on yksi `tests/e2e_entity/<scenario>/` -kansio.

Per kansio:

1. Varmista, etta kansiossa on oma `EMS_config.yaml`.
2. Muuta `build_harness(...)` kayttamaan:

```python
QuarterScenarioHarness(
    project_root=project_root,
    start_ts=...,
    step_s=...,
    scenario_dir=Path(__file__).parent,
)
```

3. Korvaa testien root `ENT` -riippuvuudet:

```python
ENT['actuator_relay1']
```

muotoon:

```python
h.ent['actuator_relay1']
```

tai scenario helperilla:

```python
E = h.ent
```

4. Korvaa device-haut:

```python
device_entity('RELAY3', 'enabled')
```

muotoon:

```python
h.device_entity('RELAY3', 'enabled')
```

5. Korvaa skenaariokohtaiset paikalliset workaroundit, kuten kovakoodattu
   `RELAY3_ENT`, kun harness-aware helperit ovat valmiit.

Hyvaksynta per kansio:

1. Kansio menee lapi yksin:

```bash
python3 -m pytest -q tests/e2e_entity/<scenario>
```

2. Kansio menee lapi, vaikka root `EMS_config.yaml`:sta poistetaan jokin vain
   kyseisessa skenaariossa oleva device.
3. Kansio ei importtaa `tests.entity_ids.ENT`:a, ellei testin tarkoitus ole
   nimenomaan root config -contract.

## Vaihe 5: lisae root YAML isolation -regressiotesti

Tavoite: root YAML -kytkenta ei palaa vahingossa.

Lisae contract- tai e2e-infra-testi, joka todistaa scenario registryn olevan
itsenainen.

Esimerkki:

```python
def test_scenario_harness_uses_scenario_yaml_for_entity_registry(project_root):
    h = QuarterScenarioHarness(
        project_root=project_root,
        scenario_dir=project_root / 'tests/e2e_entity/net_zero_priority_order_quarter_3_relays',
    )

    assert h.grouped_config_path.name == 'EMS_config.yaml'
    assert 'RELAY3' in h.ent['devices']
    assert h.device_entity('RELAY3', 'enabled') == 'switch.relay_3_2'
```

Lisae negatiivinen suoja:

1. testaa scenario, jonka device-id puuttuu root configista
2. varmista, etta haku toimii silti scenario registrylla

Hyvaksynta:

1. Regressiotesti failaa nykyisella root `ENT` -mallilla.
2. Regressiotesti menee lapi harness-aware registry -mallilla.

## Vaihe 6: poista e2e:n globaali ENT-riippuvuus

Tavoite: `tests/entity_ids.py` ei vaikuta `tests/e2e_entity/`-testien ajoon.

Poistettavat tai rajattavat asiat:

1. `from tests.entity_ids import ENT` e2e-testitiedostoista
2. `device_entity(...)` global helper e2e-asserttien ja seedauksen ensisijaisena pintana
3. root `ENT` fallback `tests/e2e_entity/refactored_runner.py`:sta

Sallittu jatkokaytto:

1. contract-testit, jotka vertaavat root configia runtimeen
2. smoke-testit, jotka tarkistavat root example / root production configin latautumisen
3. yksittaiset compatibility-testit, joissa root config on nimenomainen testikohde

Hyvaksynta:

```bash
rg -n "from tests.entity_ids import ENT|ENT\\[|ENT\\.get|device_entity\\(" tests/e2e_entity
```

ei loyda e2e-testien runtime- tai assert-polusta root registry -riippuvuutta.
Dokumentaatio-osumat ja erikseen nimetyt compatibility-testit ovat sallittuja
vain perustellusti.

## Vaihe 7: tee scenario YAML pakolliseksi e2e-kansioissa

Tavoite: yksikaan e2e-skenaario ei putoa root configiin vahingossa.

Muutos:

1. `QuarterScenarioHarness(... scenario_dir=...)` failaa, jos scenario_dir on
   annettu mutta sielta puuttuu `EMS_config.yaml`.
2. Root fallback sallitaan vain, jos harness rakennetaan eksplisiittisesti:

```python
QuarterScenarioHarness(... grouped_config_path=project_root / 'EMS_config.yaml')
```

3. Lisae infra-testi, joka varmistaa, etta jokaisessa e2e-skenaariokansiossa
   on `EMS_config.yaml` tai eksplisiittinen poikkeuslista.

Hyvaksynta:

1. Uusi e2e-skenaario ei voi kayttaa root YAML:ia vahingossa.
2. Scenario YAML -puute antaa selkean virheen.
3. Poikkeuslista on tyhja tai lyhyt ja perusteltu.

## Vaihe 8: paivita dokumentaatio ja poistettavat workaroundit

Tavoite: uusi malli on dokumentoitu ja siirtymavaiheen workaroundit poistettu.

Paivitettavat dokumentit:

1. `docs/dev/testausautomaatio.md`
2. `tests/e2e_entity/e2e_refactoring.md`
3. scenario YAML -esimerkit `docs/user/config_examples.md`, jos helper-malli muuttaa testiviitteita

Poistettavat workaroundit:

1. skenaariokohtaiset paikalliset entity-id mapit, kuten `RELAY3_ENT`, jos ne
   ovat syntyneet root `ENT` -riippuvuuden kiertamiseksi
2. helperien root `ENT` fallbackit
3. dokumentoidut ohjeet, jotka kaskevat lisaamaan testilaitteen root configiin
   vain e2e-helperien takia

Hyvaksynta:

1. Dokumentaatio kertoo, etta e2e scenario YAML on testin ainoa config-totuus.
2. Root configin muuttaminen ei muuta e2e-skenaarioiden device registrya.
3. Koko testisetti menee lapi:

```bash
python3 -m pytest -q tests
```

## Migraatiojarjestys

Suositeltu jarjestys:

1. Toteuta harnessin `self.ent` ja `h.device_entity(...)`.
2. Muuta `seed_active_surplus_devices(...)` ja muut seed-helperit harness-aware-malliin.
3. Lisae root isolation -regressiotesti.
4. Migroi ensin pieni custom-device-skenaario:
   `tests/e2e_entity/custom_device_ids_selected_single_ev/`.
5. Migroi 3-releen skenaario:
   `tests/e2e_entity/net_zero_priority_order_quarter_3_relays/`.
6. Migroi n-device boundary -skenaariot:
   - `tests/e2e_entity/net_zero_no_ev_relays_only/`
   - `tests/e2e_entity/net_zero_no_relays_ev_only/`
   - `tests/e2e_entity/net_zero_two_ev_one_relay/`
7. Migroi loput e2e-kansiot.
8. Poista root fallback e2e-polusta.
9. Tee scenario YAML pakolliseksi e2e-kansioissa.

## Riskit ja hallinta

### Riski: liian iso kertamuutos

Hallinta: pidetaan harness API ensin backward compatible -tilassa ja migroidaan
kansio kerrallaan.

### Riski: helperit alkavat sekoittaa kahta registrya

Hallinta: helperit ottavat aina `h`-olion ensimmaiseksi parametriksi ja lukevat
vain `h.ent`:a. Jos fallback on valiaikaisesti pakollinen, se lokitetaan tai
merkitään selkeasti deprecatediksi.

### Riski: root config -contract-testit rikkoutuvat

Hallinta: contract-testit saavat kayttaa root configia eksplisiittisesti.
E2E-migraatio ei poista root configin testattavuutta, vaan rajaa sen pois
skenaariotestien implisiittisesta polusta.

### Riski: scenario YAML -duplikaatio kasvaa

Hallinta: skenaariokohtainen YAML on tarkoituksellista testidataa. Jos
duplikaatio kasvaa liikaa, lisae myohemmin fixture-generaattori tai YAML anchor
-malli, mutta vasta kun scenario isolation on valmis.

## Definition of Done

Migraatio on valmis, kun:

1. Jokaisella `tests/e2e_entity/<scenario>/` -kansiolla on oma `EMS_config.yaml`.
2. `QuarterScenarioHarness` rakentaa `h.ent`:n samasta YAML:sta, jota runtime lukee.
3. E2E-testit ja helperit kayttavat `h.ent` / `h.device_entity(...)` -pintaa.
4. `tests/e2e_entity/` ei riipu root `EMS_config.yaml`:sta device registryssa.
5. Root YAML:n device-listan muuttaminen ei riko skenaariota, jonka oma YAML
   sisaltaa tarvittavat devicet.
6. Root YAML -kytkennalle on regressiotesti.
7. Koko testisetti menee lapi:

```bash
python3 -m pytest -q tests
```
