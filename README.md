# Home Assistant EMS — Beta

Home Assistantin ja Pyscriptin päälle rakennettu device-ID-kohtainen energianhallintajärjestelmä. Tämä paketti on tarkoitettu ensimmäiseen ulkopuoliseen beta-testaukseen, ei valvomattomaan käyttöönottoon.

## Ennen käyttöönottoa

- Ota varmuuskopio Home Assistantin konfiguraatiosta ja nykyisistä automaatioista.
- Varmista, että akun, EV-laturin ja releiden omat fyysiset suojaukset toimivat EMS:stä riippumatta.
- Aloita `MANUAL_SAFE`-tilassa ja varmista mittausten merkit, actuator-mappingit sekä guardit ennen `AUTOMATIC`-tilaa.
- Älä kopioi esimerkkien entity-ID:itä sellaisenaan. Ne ovat tarkoituksella geneerisiä paikkamerkkejä.

## Aloita tästä

1. [Asennus](docs/user/installation.md)
2. [Konfigurointi](docs/user/configuration.md)
3. [Validoidut esimerkit](docs/user/validated_examples.md)
4. [Operointi ja vianetsintä](docs/user/operations_and_troubleshooting.md)
5. [Tunnetut rajoitteet](docs/user/known_limitations.md)

Koko käyttäjädokumentaation hakemisto: [docs/user/README.md](docs/user/README.md).

## Nykyinen tuotantomalli

Runtime-contract:

```text
direct_tick_frame_v5
schema_version = 5
```

Tuetut device-kindit:

- `BATTERY`
- `EV_CHARGER`
- `RELAY`

Roolit:

```text
configured primary-consuming candidates = 0..N, järjestetty lista
effective primary-consuming regulator = 0..1 per policy-ajo
producing regulators = 0..N
surplus consumers = 0..N
```

Jokaiselle laitteelle muodostetaan yksi lopullinen `DevicePolicy`. Positiivinen target tarkoittaa kulutusta/latausta ja negatiivinen target tuotantoa/purkua.

EV:n HARD_OFF-vapautus perustuu peräkkäisiin PV-palautumistickeihin. RPC vaikuttaa vasta surplus-aktivointiin, ei lifecycle-vapautukseen.

Kun surplus-laitteita on useita aktiivisena, uusimmat lisäkuormaportaat vapautetaan yksi kerrallaan negatiivisen RPC:n perusteella. Release käyttää laitteen tehoa ja marginaalia `max(100 W, 5 % tehosta)`; ensimmäisenä aktivoitu anchor-laite säilyttää konservatiivisen RPNZ-release-säännön.

## Canonical ketju

```text
runtime v5 packets
→ ems_policy_engine.py
→ sensor.ems_device_policies_pyscript
→ ems_actuator_writers.py
→ Home Assistant actuators
```

Surplus-state:

```text
sensor.ems_surplus_dispatch_command_pyscript
→ ems_dispatch_state_applier.py
→ sensor.ems_active_surplus_devices
```

## Paketissa olevat pääosat

```text
EMS_config.yaml                         staattinen topologia
                                     
template.yaml                           täydellinen template:-osio; muokkaa entity-ID:t
examples/template_include.example.yaml  !include-fragmentti
ems_policy_engine.py                    policy engine
ems_actuator_writers.py                 actuator writerit
ems_dispatch_state_applier.py           surplus-state applier
modules/                                adapterit ja core-logiikka
docs/user/                              käyttöönotto ja operointi
docs/dev/                               kehitys ja testaus
tests/                                  unit-, contract- ja E2E-testit
```

## Beta-palautteeseen tarvittavat tiedot

Liitä vähintään:

- käytetty ZIP ja SHA-256
- Home Assistant- ja Pyscript-versiot
- oma device-topologia ilman salaisuuksia
- `sensor.ems_policy_diagnostics_pyscript`-attribuutit ongelmahetkeltä
- `sensor.ems_actuator_writer_trace` ja tarvittaessa dispatch trace
- odotettu ja toteutunut käyttäytyminen
- tarkka kellonaika sekä mahdollinen restart/reload juuri ennen ongelmaa

Valmis raporttipohja: [docs/user/beta_feedback.md](docs/user/beta_feedback.md).

## Kehittäminen

Arkkitehtuuri, tilakaaviot, testaus ja regressioreferenssit löytyvät [docs/dev/README.md](docs/dev/README.md)-hakemistosta.

## Lisenssi ja vastuu

Beta-ohjelmisto ohjaa fyysisiä energialaitteita. Käyttäjä vastaa oman järjestelmänsä sähkö- ja laiteturvallisuudesta, rajoista, valvonnasta ja palautussuunnitelmasta.
