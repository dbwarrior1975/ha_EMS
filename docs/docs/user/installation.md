# Asennus

## 1. Esivaatimukset

Tarvitset:

- Home Assistant -asennuksen, jossa Pyscript on asennettu ja toiminnassa
- pääsyn `/config`-hakemistoon
- varmuuskopion nykyisestä konfiguraatiosta
- toimivat lähdemittaukset: verkon teho, varttitase ja PV-teho
- laitekohtaiset actuator-entiteetit sekä riippumattomat fyysiset suojaukset

Tämä beta ei asenna helper-entiteettejä automaattisesti.

## 2. Varmuuskopioi

Tallenna ennen muutoksia vähintään:

```text
/config/configuration.yaml
/config/template.yaml tai muu template-include
/config/EMS_config.yaml
/config/pyscript/
```

Kirjaa myös nykyiset akun, EV-laturin ja releiden turvalliset manuaaliasetukset.

## 3. Kopioi Pyscript-tiedostot

Kopioi seuraavat `/config/pyscript/`-hakemistoon säilyttäen hakemistorakenne:

```text
ems_policy_engine.py
ems_actuator_writers.py
ems_dispatch_state_applier.py
modules/
```

Kopioi staattinen topologia:

```text
EMS_config.yaml → /config/EMS_config.yaml
```

Muokkaa tiedostoon vain oma device-topologia, capability-roolit ja cadence. Runtime-policy-arvot tulevat template-sensoreista.

## 4. Lisää runtime template -sensorit

Paketin `template.yaml` sisältää täydellisen Home Assistant -osion:

```yaml
template:
  - sensor:
      # ...
```

Voit yhdistää tämän osion suoraan `configuration.yaml`:iin tai package-tiedostoon.

Jos käytät rakennetta:

```yaml
template: !include template_ems.yaml
```

include-tiedoston pitää alkaa listana, ei uudella `template:`-avaimella. Käytä valmista tiedostoa:

```text
examples/template_include.example.yaml
```

Sen alku näyttää tältä:

```yaml
- sensor:
    # ...
```

Älä sijoita täydellistä `template:`-osiota `template: !include` -tiedoston sisään.

## 5. Korvaa geneeriset entity-ID:t

Aktiivisissa esimerkeissä käytetään tarkoituksella geneerisiä nimiä. Etsi ja korvaa ainakin:

```text
sensor.ems_grid_power_w
sensor.ems_pv_power_w
sensor.ems_home_battery_soc
sensor.ems_home_battery_min_cell_voltage_v
sensor.ems_home_battery_power_w
number.ems_home_battery_target_w
switch.ems_ev_charger_enabled
number.ems_ev_charger_current_a
switch.ems_relay1_enabled
switch.ems_relay2_enabled
sensor.ems_haeo_battery_fresh_source
sensor.ems_haeo_ev_fresh_source
```

Kaikkien pakollisten lähteiden pitää olla olemassa. Strict parser ei korvaa puuttuvaa mittausta nollalla.

## 6. Luo tai mapita helperit

`template.yaml` viittaa `input_select`, `input_number`, `input_boolean` ja `input_datetime` -entiteetteihin. Niiden pitää olla olemassa tai template pitää muuttaa käyttämään omia entiteettejäsi.

Erityisen tärkeät:

- control, goal, forecast ja guard -profiilit
- deadband, ramp ja strict limit
- akun lataus-/purkurajat ja guard-kynnykset
- EV:n min/max, virta-askel, vaiheet ja jännite
- EV:n HARD_OFF-kynnykset
- releiden nimellistehot, prioriteetit ja FORCE_ON-valinnat
- surplus freeze -tila

## 7. Tarkista Home Assistantin konfiguraatio

Aja Home Assistantin konfiguraation tarkistus. Korjaa kaikki YAML- ja template-virheet ennen reloadia.

Tarkista erityisesti:

- `template.yaml`-juuren muoto
- entity-ID:t
- yksiköt: W, kW, kWh, A ja V
- ettei samaa `unique_id`:tä määritellä kahdesti

## 8. Reload-järjestys

Turvallinen järjestys:

1. aseta control-profiiliksi `MANUAL_SAFE`
2. lataa template-entiteetit uudelleen tai käynnistä Home Assistant
3. lataa Pyscript uudelleen tai käynnistä Home Assistant
4. varmista runtime-sensorit ja schema
5. suorita [ensikäynnistyksen tarkistuslista](first_start_checklist.md)
6. vaihda `AUTOMATIC`-tilaan vasta tarkistusten jälkeen

Kun templateen kovakoodattu policy-arvo muuttuu mutta revision-lähteet eivät muutu, nosta template-revisionin staattista salt-arvoa tai tee sekä template- että Pyscript-reload. Tavallisten helper-arvojen muutos päivittää revisionin automaattisesti.

## 9. Rollback

Jos runtime on invalidi tai actuator-käyttäytyminen poikkeaa odotetusta:

1. vaihda `MANUAL_SAFE`-tilaan
2. poista automaattinen writer-ohjaus käytöstä tarvittaessa Pyscript-reloadilla tai palauttamalla aiempi tiedosto
3. palauta varmuuskopioidut tiedostot
4. lataa template ja Pyscript uudelleen
5. varmista laitteiden turvalliset manuaaliset targetit

Älä jatka beta-testausta ennen kuin virheen syy on tunnistettu.
