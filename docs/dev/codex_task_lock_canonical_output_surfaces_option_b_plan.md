# Toteutussuunnitelma: Option B canonical output surfaces

## Arvio

Option B on hyvä vaihtoehto ja arkkitehtonisesti parempi tavoitetila kuin Option A.

Perustelu:

1. `policy_outputs` ovat EMS:n sisäisiä command/state bus -pintoja, eivät käyttäjän nimeämiä inputteja.
2. `ems_actuator_writers.py` ja `ems_dispatch_state_applier.py` käyttävät edelleen kanonisia sensoreita Pyscript-triggeripintoina.
3. Jos YAML antaa vaikutelman, että nämä entity ID:t voi nimetä vapaasti, config-sopimus valehtelee suhteessa runtime-toteutukseen.
4. Vakioihin siirtäminen tekee oikeasta mallista yksinkertaisen: runtime inputit ovat konfiguroitavia, output bus -pinnat ovat kiinteitä.

Option B:n riski on mekaaninen, ei arkkitehtoninen. Nykyinen loader pitää `policy_outputs`- ja `diagnostics_outputs`-osiot pakollisina, `CoreConfig` rakentaa ne YAML:stä ja `runtime_context` täyttää entity registryä YAML-outputeista. Siksi Option B pitää toteuttaa hallitusti testien kanssa, ei pelkkänä dokumenttisiivouksena.

Koska EMS on vielä DEV-tilassa, taaksepäin yhteensopivuutta ei kannata pitää mukana. Tässä haetaan nimenomaan puhdasta sopimuksen korjausta ennen julkista/stabiilia config-kontraktia.

Suositus: toteuta Option B breaking cleanupina.

Käytännössä tämä tarkoittaa:

1. Uudet ja esimerkkikonfigit eivät enää sisällä `policy_outputs`- tai `diagnostics_outputs`-osioita.
2. Loader täyttää canonical outputit aina koodin vakioista.
3. Jos käyttäjäkonfigissa on `policy_outputs` tai `diagnostics_outputs`, validointi hylkää osion kokonaan.
4. Custom-arvoille ei tarvita erillistä polkua, koska koko osio on virheellinen user configissa.
5. Virheviestin pitää kertoa, että output-pinnat ovat kiinteitä koodissa eikä niitä voi nimetä YAML:ssä.

Tämä on selkein DEV-vaiheen ratkaisu: config-sopimus korjataan nyt, eikä ylläpidetä väliaikaista legacy-politiikkaa, joka pitäisi myöhemmin poistaa.

## Tavoitetila

Config-sopimus:

```text
runtime:
  user-configurable read targets sampled by policy_engine timer

policy_engine:
  user-configurable scheduler settings

policy_outputs:
  not user config; fixed EMS internal command/state bus surfaces

diagnostics_outputs:
  not user config; fixed EMS diagnostics surfaces for now
```

Kanoniset entity ID:t määritellään yhdessä paikassa koodissa, ja kaikki loader-, runtime-context-, testi- ja dokumentaatiokäyttö viittaa niihin joko suoraan importin kautta tai testien odotusarvoina.

## Rajaus

Tässä tehtävässä ei saa:

1. muuttaa NET_ZERO-kaavoja;
2. muuttaa policy-engine timer-loopin ajoitusta;
3. muuttaa E2E business expected value -arvoja;
4. tehdä writer/dispatch triggereistä dynaamisia;
5. poistaa canonical hash-state -sensoreita;
6. muuttaa runtime input -konfiguraation käyttäytymistä.

## Vaihe 1: lisää canonical output -vakiot

Lisää uusi moduuli:

```text
modules/ems_core/domain/constants.py
```

Sisältö:

```python
CANONICAL_POLICY_OUTPUT_DEVICE_POLICIES = "sensor.ems_device_policies_pyscript"
CANONICAL_POLICY_OUTPUT_DISPATCH_COMMAND = "sensor.ems_surplus_dispatch_command_pyscript"
CANONICAL_POLICY_OUTPUT_POLICY_STATE = "sensor.ems_policy_state_pyscript"

CANONICAL_DIAGNOSTICS_POLICY = "sensor.ems_policy_diagnostics_pyscript"
CANONICAL_DIAGNOSTICS_ACTUATOR_WRITER_TRACE = "sensor.ems_actuator_writer_trace"
CANONICAL_DIAGNOSTICS_DISPATCH_STATE_APPLIER_TRACE = "sensor.ems_dispatch_state_applier_trace"

CANONICAL_POLICY_OUTPUTS = {
    "device_policies": CANONICAL_POLICY_OUTPUT_DEVICE_POLICIES,
    "dispatch_command": CANONICAL_POLICY_OUTPUT_DISPATCH_COMMAND,
    "policy_state": CANONICAL_POLICY_OUTPUT_POLICY_STATE,
}

CANONICAL_DIAGNOSTICS_OUTPUTS = {
    "policy_diagnostics": CANONICAL_DIAGNOSTICS_POLICY,
    "actuator_writer_trace": CANONICAL_DIAGNOSTICS_ACTUATOR_WRITER_TRACE,
    "dispatch_state_applier_trace": CANONICAL_DIAGNOSTICS_DISPATCH_STATE_APPLIER_TRACE,
}
```

Pidä stringit tässä yhdessä paikassa. Täydellistä deduplikointia Pyscript `@state_trigger` -dekoraattoreista ei kannata pakottaa tässä tehtävässä, koska decorator tarvitsee staattisen stringin ja tavoite ei ole muuttaa triggerimallia.

## Vaihe 2: muuta config-loaderin sopimus

Muuta `modules/ems_adapter/config_loader.py`:

1. Poista `policy_outputs` ja `diagnostics_outputs` `REQUIRED_TOP_LEVEL_SECTIONS`-joukosta.
2. Poista ne myös sallitusta aktiivisesta user config -top-level-sopimuksesta.
3. Lisää niille eksplisiittinen hylkäys, jotta virhe on parempi kuin geneerinen unknown-field.
4. Jos `ems.policy_outputs` tai `ems.diagnostics_outputs` puuttuu, validointi hyväksyy konfigin.
5. Jos `ems.policy_outputs` on mukana millään sisällöllä, hylkää osio kovalla virheellä.
6. Jos `ems.diagnostics_outputs` on mukana millään sisällöllä, hylkää osio kovalla virheellä.
7. Säilytä vanhojen legacy `policy_outputs.*`-avainten eksplisiittiset virheet vain jos haluat tarkemman kehittäjäpalautteen, mutta älä hyväksy mitään `policy_outputs`-osion muotoa.

Virhemallin pitää olla selkeä:

```text
ems.policy_outputs is no longer user config. EMS canonical policy output entity IDs are fixed in code.
```

Diagnostiikalle:

```text
ems.diagnostics_outputs is no longer user config. EMS diagnostics output entity IDs are fixed in code.
```

## Vaihe 3: rakenna CoreConfig vakioista

Muuta `build_core_config_from_grouped_reader()`:

1. Älä lue `policy_outputs`-arvoja YAML:stä.
2. Rakenna `CorePolicyOutputsConfig` suoraan `CANONICAL_POLICY_OUTPUTS`-vakioista.
3. Rakenna `CoreDiagnosticsOutputsConfig` suoraan `CANONICAL_DIAGNOSTICS_OUTPUTS`-vakioista.
4. Älä kutsu `_resolve_core_config_value()` näille arvoille. Nämä ovat entity ID -pintoja, eivät runtime-luettavia arvoja.

Odotus:

```python
core.policy_outputs.device_policies == "sensor.ems_device_policies_pyscript"
core.diagnostics_outputs.policy_diagnostics == "sensor.ems_policy_diagnostics_pyscript"
```

Tämän pitää pitää paikkansa, vaikka YAML ei sisällä output-osioita.

## Vaihe 4: muuta runtime registry täyttymään vakioista

Muuta `modules/ems_adapter/runtime_context.py`:

1. Älä täytä `ent['device_policies']`, `ent['dispatch_command']` tai `ent['policy_state']` YAML:n `policy_outputs`-osiosta.
2. Täytä ne `CANONICAL_POLICY_OUTPUTS`-vakioista.
3. Älä täytä diagnostiikkaentityjä YAML:n `diagnostics_outputs`-osiosta.
4. Täytä ne `CANONICAL_DIAGNOSTICS_OUTPUTS`-vakioista.

Tämä on kriittinen kohta. Runtime registry ei saa enää olla riippuvainen YAML-output-osioista missään polussa.

## Vaihe 5: päivitä config-esimerkit

Päivitä ainakin:

```text
example_EMS_config.yaml
EMS_config.yaml
tests/e2e_entity/*/EMS_config.yaml
```

Poista näistä:

```yaml
policy_outputs:
  device_policies: sensor.ems_device_policies_pyscript
  dispatch_command: sensor.ems_surplus_dispatch_command_pyscript
  policy_state: sensor.ems_policy_state_pyscript

diagnostics_outputs:
  policy_diagnostics: sensor.ems_policy_diagnostics_pyscript
  actuator_writer_trace: sensor.ems_actuator_writer_trace
  dispatch_state_applier_trace: sensor.ems_dispatch_state_applier_trace
```

Älä lisää näiden tilalle uutta user-config-osiota. Jos haluat jättää kommentin, pidä se lyhyenä:

```yaml
# EMS output bus and diagnostics entity IDs are fixed in code, not user config.
```

## Vaihe 6: päivitä testit

Päivitä `tests/unit/test_config_loader.py`:

Lisää tai muuta testit:

```text
test_policy_outputs_defaults_to_canonical_values_if_missing
test_policy_outputs_section_is_rejected_even_with_canonical_values
test_policy_outputs_section_is_rejected_with_custom_values
test_policy_outputs_section_is_rejected_with_unknown_key
test_diagnostics_outputs_defaults_to_canonical_values_if_missing
test_diagnostics_outputs_section_is_rejected_even_with_canonical_values
test_diagnostics_outputs_section_is_rejected_with_custom_values
test_diagnostics_outputs_section_is_rejected_with_unknown_key
```

Päivitä `tests/unit/test_core_config.py`:

1. Poista `_core_entity_values()`-fixturestä canonical output entity ID -arvojen tarve, jos niitä ei enää lueta `read_entity`n kautta.
2. Lisää testi, jossa example-configistä poistetaan `policy_outputs` ja `diagnostics_outputs`, ja `build_core_config_from_grouped_config()` palauttaa silti canonical outputit.
3. Lisää testi, jossa YAML sisältää output-osion ja validointi hylkää koko osion.

Päivitä runtime-context-testit tai lisää uusi testi, joka varmistaa:

```text
ent["device_policies"] == sensor.ems_device_policies_pyscript
ent["dispatch_command"] == sensor.ems_surplus_dispatch_command_pyscript
ent["policy_state"] == sensor.ems_policy_state_pyscript
ent["policy_diagnostics"] == sensor.ems_policy_diagnostics_pyscript
ent["actuator_writer_trace"] == sensor.ems_actuator_writer_trace
ent["dispatch_state_applier_trace"] == sensor.ems_dispatch_state_applier_trace
```

Tämän pitää toimia ilman YAML-output-osioita.

Säilytä tai lisää lähdetesti, joka varmistaa nykyiset staattiset triggerit:

```text
@state_trigger('sensor.ems_device_policies_pyscript')
@state_trigger('sensor.ems_surplus_dispatch_command_pyscript')
```

## Vaihe 7: päivitä aktiivinen dokumentaatio

Päivitä ainakin:

```text
README.md
docs/dev/arkkitehtuuri.md
docs/dev/ems_step_model.md
docs/dev/testausautomaatio.md
tests/e2e_entity/e2e_conventions.md
docs/user/config_examples.md
docs/user/EMS_parametrointi_guide.md
```

Dokumentoi ero näin:

```text
runtime.* entity ID:t ovat käyttäjän konfiguroitavia read target -pintoja.
policy_outputs ja diagnostics_outputs eivät ole käyttäjän konfiguraatiota.
Ne ovat EMS:n kiinteitä canonical output bus- ja diagnostics-pintoja.
```

Poista tai muotoile uudelleen kohdat, joissa `policy_outputs` tai `diagnostics_outputs` kuvataan käyttäjän YAML-sopimuksena.

## Vaihe 8: grep-tarkistukset

Aja:

```bash
rg "policy_outputs|diagnostics_outputs" EMS_config.yaml example_EMS_config.yaml tests/e2e_entity docs tests modules ems_*.py
```

Hyväksyttävät osumat:

1. loaderin eksplisiittinen hylkäys;
2. testit, jotka varmistavat output-osioiden hylkäyksen;
3. dokumentaatio, joka sanoo ettei osio ole enää user config;
4. vanhojen legacy fieldien hylkäysviestit, jos ne pidetään tarkemman palautteen vuoksi.

Epäilyttävät osumat:

1. esimerkkikonfigissa aktiivinen `policy_outputs`- tai `diagnostics_outputs`-osio;
2. dokumentti, joka neuvoo käyttäjää nimeämään nämä entityt;
3. runtime code, joka lukee output entity ID:t YAML:stä.

Aja:

```bash
rg "sensor\.ems_device_policies_pyscript|sensor\.ems_surplus_dispatch_command_pyscript|sensor\.ems_policy_state_pyscript|sensor\.ems_policy_diagnostics_pyscript|sensor\.ems_actuator_writer_trace|sensor\.ems_dispatch_state_applier_trace" modules ems_*.py tests docs
```

Hyväksyttävät osumat:

1. canonical constants;
2. Pyscript static triggerit;
3. testien odotusarvot;
4. dokumentaatio, joka kuvaa fixed surfaces -mallin.

## Vaihe 9: testiajo

Aja vähintään:

```bash
python3 -m pytest -q tests/unit/test_config_loader.py
python3 -m pytest -q tests/unit/test_core_config.py
python3 -m pytest -q tests/contract
python3 -m pytest -q tests/e2e_entity
python3 -m pytest -q
```

Jos repossa on standardi wrapper, käytä sitä näiden sijasta.

## Hyväksymiskriteerit

Functional:

1. `policy_outputs` ja `diagnostics_outputs` eivät ole enää pakollisia user config -osioita.
2. Loader täyttää canonical outputit koodin vakioista.
3. Runtime registry saa output entity ID:t vakioista, ei YAML:stä.
4. `policy_outputs` user configissa hylätään selkeällä virheellä, vaikka arvot olisivat kanoniset.
5. `diagnostics_outputs` user configissa hylätään selkeällä virheellä, vaikka arvot olisivat kanoniset.
6. Custom output entity ID:t eivät pääse vaikuttamaan runtimeen missään polussa.

Safety:

1. Writer ja dispatch applier jatkavat kanonisten sensoreiden kuluttamista.
2. Ei dynaamista triggerirekisteröintiä.
3. Ei muutoksia policy-engine timer-loopiin.
4. Ei muutoksia NET_ZERO-logiikkaan.
5. Ei E2E expected value -muutoksia.

Documentation:

1. Aktiiviset config-esimerkit eivät enää näytä `policy_outputs`- tai `diagnostics_outputs`-osioita käyttäjän muokattavina arvoina.
2. Dokumentaatio erottaa selvästi runtime inputit ja fixed canonical output bus -pinnat.
3. Dokumentaatio kertoo, että output bus -entityjen muuttaminen vaatisi erillisen dynaamisen writer/dispatch trigger -arkkitehtuurin.

## Ei migration-vaihetta

Älä lisää väliaikaista hyväksyntää vanhoille canonical `policy_outputs`- tai `diagnostics_outputs`-osioille.

Perustelu:

1. EMS on vielä DEV-tilassa.
2. Tavoitteena on lukita oikea config-sopimus ennen stabiilia käyttöä.
3. Taaksepäin yhteensopiva hyväksyntä pitäisi myöhemmin poistaa, jolloin syntyy toinen cleanup-tehtävä ilman todellista hyötyä.
4. Selkeä virhe pakottaa korjaamaan konfigit heti ja estää väärän mental modelin jäämisen dokumentteihin tai testeihin.
