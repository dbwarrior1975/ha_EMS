# Surplus Loads Handoff

Paivitetty: 2026-06-21

## Tila nyt

Tama repo on nyt pisteessa, jossa surplus-kuormien joustavoittamisen vaiheet 1-10
on viety lapi dokumentin
[surplusloads_to_support_more_flexibiity.md](/home/virtamik/code/ha_EMS/docs/archive/surplusloads_to_support_more_flexibiity.md)
mukaisesti.

Vahvistettu tila:

- `python3 -m pytest -q tests` -> `207 passed, 1 xfailed`
- ainoa `xfail`:
  - `tests/e2e_entity/haeo_02_net_zero_homebattery_primary_ev_adjustable/...`
  - syy: tuleva HAEO combo -semantiikka, ei regressio

## Mita valmistui tassa vaiheessa

1. `CoreConfig.devices` toimii kanonisena device-registryna.
2. Runtime entityt rakentuvat `entities['devices']`-registryyn.
3. Surplus-target builder toimii geneerisella relay-listalla.
4. Policy engine laskee relay- ja EV-deviceja listapohjaisesti.
5. Dispatch-applier kasittelee aktiivisia surplus-deviceja geneerisena
   device-id-listana.
6. Writer loop kirjoittaa kaikki registryssa olevat relay- ja EV-devicet
   `kind`-pohjaisesti.
7. Writer trace julkaisee geneerisen `devices`-mapin.
8. E2E:t on paivitetty vastaamaan uutta ordering- ja trace-semanttiikkaa.

## Tarkeimmat muutetut tiedostot

- [modules/ems_adapter/runtime_context.py](/home/virtamik/code/ha_EMS/modules/ems_adapter/runtime_context.py)
- [modules/ems_adapter/config_loader.py](/home/virtamik/code/ha_EMS/modules/ems_adapter/config_loader.py)
- [modules/ems_adapter/device_read_model.py](/home/virtamik/code/ha_EMS/modules/ems_adapter/device_read_model.py)
- [modules/ems_core/domain/models.py](/home/virtamik/code/ha_EMS/modules/ems_core/domain/models.py)
- [modules/ems_core/net_zero/engine.py](/home/virtamik/code/ha_EMS/modules/ems_core/net_zero/engine.py)
- [modules/ems_core/net_zero/surplus_device_targets.py](/home/virtamik/code/ha_EMS/modules/ems_core/net_zero/surplus_device_targets.py)
- [ems_policy_engine.py](/home/virtamik/code/ha_EMS/ems_policy_engine.py)
- [ems_dispatch_state_applier.py](/home/virtamik/code/ha_EMS/ems_dispatch_state_applier.py)
- [ems_actuator_writers.py](/home/virtamik/code/ha_EMS/ems_actuator_writers.py)

## Jäljella oleva tekninen velka

Vaikka 0-n relay / 0-n EV -perusta on nyt olemassa, toteutuksessa on edelleen
kiinteita siirtymaoletuksia:

1. `CoreConfig` sisaltaa yha convenience-kentat:
   - `home_battery`
   - `ev_charger`
   - `relay1`
   - `relay2`
2. `config_loader.py` rakentaa yha scalar/alias-nakymia:
   - `relay1_power_kw`
   - `relay2_force_on`
   - `charger_current`
   - jne.
3. `EMS_config.yaml` tuotantoesimerkki kayttaa edelleen:
   - `EV_CHARGER`
   - `RELAY1`
   - `RELAY2`
4. Osa trace- ja dashboard-semantiikasta sailyttaa yha compatibility-avaimia:
   - writer trace: `ev`, `relay1`, `relay2`
   - policy trace: scalarit kuten `relay1_command`, `relay2_command`, `ev_current_a`
5. Monen EV:n state-semantiiikka ei ole viela aidosti valmis:
   - `previous_device_state` on edelleen yhden adjustable-polun muistimalli
   - usean EV:n oma hard-off/release-memory ei ole viela mallinnettu per EV

## Suositeltu seuraava vaihe

Seuraava oikea vaihe ei ole enaa "tehda 0-n relay mahdolliseksi", koska se on jo
tehty. Seuraava vaihe on poistaa siirtymakauden kiinteita oletuksia.

Suositeltu tyopaketti:

### Vaihe A: Poista kiinteat relay1/relay2/ev_charger convenience-riippuvuudet

Tavoite:
- `CoreConfig` ei olisi enaa sisaisesti riippuvainen kentista `ev_charger`,
  `relay1`, `relay2`, paitsi korkeintaan adapteri- tai deprecated-tasolla.

Konreettiset kohteet:
- [modules/ems_core/domain/models.py](/home/virtamik/code/ha_EMS/modules/ems_core/domain/models.py)
- [modules/ems_adapter/config_loader.py](/home/virtamik/code/ha_EMS/modules/ems_adapter/config_loader.py)
- [modules/ems_adapter/device_read_model.py](/home/virtamik/code/ha_EMS/modules/ems_adapter/device_read_model.py)

Hyvaksynta:
- runtime toimii ilman oletusta, etta juuri `RELAY1`, `RELAY2`, `EV_CHARGER`
  ovat "erityisia" device-id:ita
- vanhat compatibility-kentat voidaan tarvittaessa rakentaa erikseen adapterina

### Vaihe B: Monen EV:n state-malli

Tavoite:
- `previous_device_state` ei oleteta vain yhdelle adjustable-polulle
- EV:n hard-off / low-PV / release-laskurit voidaan pitaa per `device_id`

Konreettiset kohteet:
- [ems_policy_engine.py](/home/virtamik/code/ha_EMS/ems_policy_engine.py)
- [modules/ems_core/net_zero/engine.py](/home/virtamik/code/ha_EMS/modules/ems_core/net_zero/engine.py)

Hyvaksynta:
- 2 EV:n skenaariossa molemmilla voi olla oma muistinsa
- state ei katoa, jos adjustable-device vaihtuu

### Vaihe C: Trace- ja scalar-siivous

Tavoite:
- scalarit kuten `relay1_command`, `relay2_command`, `ev_current_a` rajataan
  eksplisiittisesti legacy-diagnostiikaksi tai poistetaan
- dashboardien canonical pinta on:
  - `device_policies`
  - `surplus_device_targets`
  - `active_surplus_devices`
  - writer trace `devices`

## Suositeltu aloitus seuraavassa sessiossa

Jos jatkat toisessa sessiossa, aloita taman dokumentin ja suunnitelmadokumentin
luvulla:

1. [surplusloads_handoff.md](/home/virtamik/code/ha_EMS/docs/archive/surplusloads_handoff.md)
2. [surplusloads_to_support_more_flexibiity.md](/home/virtamik/code/ha_EMS/docs/archive/surplusloads_to_support_more_flexibiity.md)

Sitten tee ensin tarkka inventaario:

```bash
rg -n "relay1|relay2|EV_CHARGER|ev_charger|devices_by_kind\\('EV_CHARGER'\\)|devices_by_kind\\('RELAY'\\)" modules ems_*.py tests
```

Ja kaynnista samalla baseline:

```bash
python3 -m pytest -q tests
```

## Huomiot tyopuusta

Nykyisessa tyopuussa on edelleen myos muita aiempia muutoksia ja muutama
untracked-tiedosto. Tarkista ennen PR:aa ainakin:

- [final_cleaning.md](/home/virtamik/code/ha_EMS/docs/archive/final_cleaning.md)
- [surplusloads_to_support_more_flexibiity.md](/home/virtamik/code/ha_EMS/docs/archive/surplusloads_to_support_more_flexibiity.md)
- repojuuren mahdolliset artefaktit kuten `ems_production_*.zip`

