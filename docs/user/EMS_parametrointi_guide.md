# EMS parametroinnin opas

Taman oppaan tavoite on antaa kaytannonlaheiset aloitusarvot ja viritysohjeet
n-device-konfiguraatiolle seka kahdelle yleiselle adjustable-kombolle.

## N-device konfiguraatio

EMS:n tuotantoraja tassa releasessa on:

1. yksi `HOME_BATTERY`
2. `0-n` `kind: RELAY` -laitetta
3. `0-n` `kind: EV_CHARGER` -laturia
4. useampi EV voi olla konfiguroituna, mutta vain yksi EV valitaan aktiiviseksi adjustable-laitteeksi kerrallaan
5. multi-EV simultaneous power split ja EV-round-robin eivat kuulu tahan releaseen

### Device-id ei kanna semantiikkaa

`RELAY1`, `RELAY2` ja `EV_CHARGER` ovat edelleen valideja device-id:ita, mutta
uusi tuotantologiikka perustuu `kind`, `capabilities`, `policy` ja `adapter`
-kenttiin. Custom device-id voi olla esimerkiksi `RELAY_SAUNA`,
`RELAY_BOILER`, `EV_MAIN` tai `EV_GARAGE`.

Canonical trace- ja writer-pinta on device-id-pohjainen:

1. `sensor.ems_device_policies_pyscript`
2. `sensor.ems_active_surplus_devices`
3. `sensor.ems_policy_decision_trace_pyscript`
4. `sensor.ems_actuator_writer_trace` ja sen `devices`-map

### Releen lisaaminen

Lisa uusi rele `ems.devices`-mapin alle. Esimerkki:

```yaml
ems:
  devices:
    RELAY_SAUNA:
      kind: RELAY
      capabilities:
        can_absorb_w: true
        can_produce_w: false
        min_absorb_w: input_number.ems_relay_sauna_nominal_absorb_w
        max_absorb_w: input_number.ems_relay_sauna_power_kw
        step_w: input_number.ems_relay_sauna_power_kw
      policy:
        priority: input_number.ems_surplus_relay_sauna_priority
        surplus_allowed: input_boolean.ems_relay_sauna_enabled_import_zero
        force_on: input_boolean.ems_relay_sauna_force_on
      adapter:
        enabled: switch.relay_sauna_enabled
```

Tarvittavat HA-helperit uudelle releelle:

1. `input_number.ems_relay_sauna_nominal_absorb_w`
2. `input_number.ems_relay_sauna_power_kw`
3. `input_number.ems_surplus_relay_sauna_priority`
4. `input_boolean.ems_relay_sauna_enabled_import_zero`
5. `input_boolean.ems_relay_sauna_force_on`
6. `switch.relay_sauna_enabled`

### Kaikkien releiden poistaminen

Poista kaikki `kind: RELAY` -laitteet `ems.devices`-mapista. Jata
`HOME_BATTERY` ja mahdolliset EV-laturit ennalleen.

```yaml
ems:
  devices:
    HOME_BATTERY:
      kind: BATTERY
      # battery capabilities, policy, guard ja adapter

    EV_CHARGER:
      kind: EV_CHARGER
      # EV capabilities, policy ja adapter
```

Testattu referenssi: `tests/e2e_entity/net_zero_no_relays_ev_only/EMS_config.yaml`.

### 0 EV -config

0 EV -configissa `ems.devices` ei sisalla yhtaan `kind: EV_CHARGER` -laitetta.
Tama sopii relays-only-kohteeseen, jossa surplus ohjataan releille ja akulle.

```yaml
ems:
  role_constraints:
    HOME_BATTERY_PRIMARY: {}

  devices:
    HOME_BATTERY:
      kind: BATTERY
      # battery capabilities, policy, guard ja adapter

    RELAY1:
      kind: RELAY
      # relay capabilities, policy ja adapter
```

Testattu referenssi: `tests/e2e_entity/net_zero_no_ev_relays_only/EMS_config.yaml`.

### 3 reletta

Kolmas rele lisataan samalla mallilla kuin muut releet. Device-id voi olla
`RELAY3` tai kuvaavampi custom id.

```yaml
ems:
  devices:
    RELAY1:
      kind: RELAY
      policy:
        priority: input_number.ems_surplus_relay1_priority
        surplus_allowed: input_boolean.ems_relay1_enabled_import_zero
        force_on: input_boolean.ems_relay1_force_on
      adapter:
        enabled: switch.relay_1_2

    RELAY2:
      kind: RELAY
      policy:
        priority: input_number.ems_surplus_relay2_priority
        surplus_allowed: input_boolean.ems_relay2_enabled_import_zero
        force_on: input_boolean.ems_relay2_force_on
      adapter:
        enabled: switch.relay_2_2

    RELAY3:
      kind: RELAY
      policy:
        priority: input_number.ems_surplus_relay3_priority
        surplus_allowed: input_boolean.ems_relay3_enabled_import_zero
        force_on: input_boolean.ems_relay3_force_on
      adapter:
        enabled: switch.relay_3_2
```

Jokaiselle releelle tarvitaan omat `max_absorb_w`, `step_w`, `priority`,
`surplus_allowed`, `force_on` ja `adapter.enabled` -entityt. Testattu
referenssi: `tests/e2e_entity/net_zero_priority_order_quarter_3_relays/EMS_config.yaml`.

### 2 EV, yksi valittu

Useampi EV voi olla konfiguroituna, mutta release tukee selected-single-rajaa.
Valittu EV on se EV-device, jonka device-id on aktiivisessa
`adjustable_primary_load`- tai `adjustable_surplus_load` -helperissa.

```yaml
ems:
  global_config:
    adjustable_surplus_load: input_select.ems_adjustable_surplus_load
    adjustable_primary_load: input_select.ems_adjustable_primary_load

  role_constraints:
    HOME_BATTERY_PRIMARY:
      EV_MAIN:
        activation_threshold_w: input_number.ems_ev_main_activation_threshold_w
      EV_GARAGE:
        activation_threshold_w: input_number.ems_ev_garage_activation_threshold_w

  devices:
    EV_MAIN:
      kind: EV_CHARGER
      policy:
        priority: input_number.ems_surplus_ev_main_priority
        surplus_allowed: input_boolean.ems_ev_main_surplus_allowed
      adapter:
        enabled: switch.ev_main_enabled
        current_a: number.ev_main_current_a

    EV_GARAGE:
      kind: EV_CHARGER
      policy:
        priority: input_number.ems_surplus_ev_garage_priority
        surplus_allowed: input_boolean.ems_ev_garage_surplus_allowed
      adapter:
        enabled: switch.ev_garage_enabled
        current_a: number.ev_garage_current_a
```

Tarvittavat HA-helperit uudelle EV-laturille:

1. `input_number.*_min_power_w`
2. `input_number.*_max_power_w`
3. `input_number.*_power_step_w`
4. `input_number.*_priority`
5. `input_boolean.*_surplus_allowed`
6. `input_number.*_low_pv_threshold_w`
7. `input_number.*_low_pv_cycles`
8. `input_number.*_release_cycles`
9. `switch.*_enabled`
10. `number.*_current_a`
11. `input_number.*_min_power_w`
12. `input_number.*_max_power_w`
13. `input_number.*_power_step_w`
14. `input_number.*_current_step_a`
15. `input_number.*_phases`
16. `input_number.*_voltage_v`

Testatut referenssit:

1. `tests/e2e_entity/net_zero_two_ev_one_relay/EMS_config.yaml`
2. `tests/e2e_entity/custom_device_ids_selected_single_ev/EMS_config.yaml`

### Priority, max_absorb_w, capabilities ja surplus_allowed

`priority` maarittaa aktivointijarjestyksen: suurempi numero aktivoituu ennen
pienempaa. Vapautus tapahtuu kaytannossa matalammasta prioriteetista alkaen.

`max_absorb_w` on laitteen suurin sallittu kulutus-/latauspyynto watteina.
Releella sama arvo on usein nimellisteho; EV:lla se on laturin tai sulakkeen
asettama ylaraja; akulla se on latausraja.

`capabilities.can_absorb_w=false` estaa positiivisen `target_w`-pyynnon.
`capabilities.can_produce_w=false` estaa negatiivisen `target_w`-pyynnon.
Nama ovat kovia runtime-rajoja, eivat vain dokumentaatiota.

`surplus_allowed` on releen tai EV:n kayttolupa surplus-policylle. Jos lupa on
pois paalta, laite voi olla konfiguroituna mutta se ei ole valittavissa
surplus-kohteeksi.

Lisää kopioitavia minimiesimerkkeja on tiedostossa `docs/user/config_examples.md`.

## 1. Nopea valinta

Valitse kombinaatio kayttotavoitteen mukaan:

- Combo A: primary = EV_CHARGER, surplus = HOME_BATTERY
  - Paras kun EV halutaan ensisijaiseksi saato-/kulutuskohteeksi.
  - Akusto toimii taustalla smoothaajana ja lisakuormana.

- Combo B: primary = HOME_BATTERY, surplus = EV_CHARGER
  - Paras kun verkkoon vienti ja akun tehohallinta halutaan pitaa ensisijaisena.
  - EV tulee mukaan surplus-kohteena kun aktivointiehto tayttyy.

## 2. Yhteiset perusparametrit

Nama kannattaa asettaa ensin kuntoon ennen kombokohtaista viritysta.

- ems_ramp_max_w
  - Mita tekee: rajoittaa setpointin muutoksen nopeutta per sykli.
  - Aloitus: 800-1200 W.
  - Nosta jos vaste on liian hidas. Laske jos setpoint heiluu liikaa.

- ems_deadband_w
  - Mita tekee: pienet virheet sivuutetaan, valtaa sahkomelulta.
  - Aloitus: 50 W.
  - Nosta jos saato nykii pienilla tehoilla.

- ems_ev_current_step_a
  - Mita tekee: EV-virran porrastus EV-primary-polussa.
  - Aloitus: 1 A (hienosaato) tai 2 A (vakaampi).
  - Jos EV sahaa ylos/alas usein, kokeile suurempaa askelta.

- ems_ev_hard_off_pv_threshold_kw
  - Mita tekee: matalan PV:n raja hard_off-logiikalle.
  - Aloitus: 1.6 kW.
  - Nosta jos haluat varmemmin estaa battery -> EV loopin.

- ems_ev_hard_off_low_pv_cycles
  - Mita tekee: montako perakkaista sykliä ennen hard_off aktivointia.
  - Aloitus: 2.
  - Nosta jos haluat hitaamman hard_off-aktivoinnin.

- ems_ev_hard_off_release_cycles
  - Mita tekee: montako perakkaista release-ehdon tayttavaa sykliä vaaditaan ennen hard_off-vapautusta.
  - Aloitus: 2.
  - Nosta jos haluat vakaamman hard_off-vapautuksen ja vahemman sahaysta kynnyksen tuntumassa.

## 3. Combo A: primary EV_CHARGER, surplus HOME_BATTERY

### 3.1 Tyypillinen kayttotapaus

- Omakotitalo, jossa EV latautuu paivisin aina kun mahdollista.
- Akusto halutaan mukaan vasta kun EV ei yksin riita absorbointiin tai tarvitaan pehmennysta.
- Tavoite: EV ensin, akku toisena.

### 3.2 Suositellut aloitusarvot

- ems_adjustable_primary_load = EV_CHARGER
- ems_adjustable_surplus_load = HOME_BATTERY
- ems_adjustable_surplus_activation_w = 2500 W
- ems_adjustable_surplus_load_priority = 4
- ems_ev_priority = 3
- ems_surplus_relay1_priority = 2
- ems_surplus_relay2_priority = 1
- ems_nz_battery_floor_ev_active_w = 0 W
- ems_ev_current_step_a = 1 A

Selvennys floor-parametreihin (tarkea):

- `ems_nz_battery_floor_default_w` on NET_ZERO:n yleinen akun minimi-floor.
- Kun `ems_adjustable_primary_load = EV_CHARGER`, akun floor tulee arvosta `ems_nz_battery_floor_ev_active_w`.
- Eli EV-primary-polussa `ems_nz_battery_floor_ev_active_w` korvaa default-floorin.
- Jos haluat saman floorin molempiin polkuihin, aseta molemmat arvot samaksi (esim. 100 W).

Selvennys activation-parametriin (tarkea):

- HA-helperin nimi on `ems_adjustable_surplus_activation_w`.
- EMS-avain on `adjustable_surplus_activation`.
- Nykyinen saadin kasittelee activation-arvon watteina (W), joten kayta W-tasoa (esim. 2000-3000), ei pienta kW-lukua.

### 3.3 Mitä odottaa kaytannossa

- EV reagoi jatkuvasti primary-polussa.
- Hard_off estaa latauksen matalassa PV:ssa.
- Hard_off-vapautus vaatii enemman kuin hetkellisen RPNZ > 0 tilanteen.
- Akun adjustable-polku aktivoituu erikseen activation-rajan perusteella.

### 3.4 Ongelma -> toimenpide

- EV kaynnistyy ja pysahtyy liian usein:
  - Nosta ems_ev_hard_off_low_pv_cycles arvoa 2 -> 3.
  - Kasvata ems_deadband_w arvoa 50 -> 80.

- EV ei palaudu hard_offista toivotusti:
  - Tarkista etta PV on pysyvasti thresholdin ylapuolella.
  - Laske ems_adjustable_surplus_activation_w arvoa, jos release-kynnys on kaytannossa liian korkea.

- Akusto osallistuu liian aikaisin:
  - Nosta ems_adjustable_surplus_activation_w arvoa, esim 2500 -> 3000 W.

## 4. Combo B: primary HOME_BATTERY, surplus EV_CHARGER

### 4.1 Tyypillinen kayttotapaus

- Kohde, jossa halutaan ensisijaisesti hallita verkko-/akkutehoa ja EV on joustava lisa.
- Tavoite: akku pitaa net zero -tasapainon, EV liittyy mukaan vain riittavassa surplusissa.

### 4.2 Suositellut aloitusarvot

- ems_adjustable_primary_load = HOME_BATTERY
- ems_adjustable_surplus_load = EV_CHARGER
- ems_adjustable_surplus_activation_w = 2000-2600 W
- ems_adjustable_surplus_load_priority = 3 tai 4
- ems_ev_priority = 2 tai 3
- ems_surplus_relay1_priority = 2
- ems_surplus_relay2_priority = 1
- ems_ev_min_power_w = 1380 W
- ems_ev_max_power_w = 6440 W

### 4.3 Mitä odottaa kaytannossa

- Akun target seuraa jatkuvaa RPNZ-saatoa ensisijaisesti.
- EV aktivoituu dispatchin kautta vasta activation-ehdolla.
- Release tapahtuu deterministisesti aktiivisten kohteiden prioriteettijarjestyksessa.

### 4.4 Ongelma -> toimenpide

- EV ei aktivoidu vaikka tuotantoa on:
  - Laske ems_adjustable_surplus_activation_w arvoa, esim 2500 -> 2000 W.
  - Tarkista että required power consumption ylittaa activation-rajan riittavan pitkaan.

- EV aktivoituu liian herkästi:
  - Nosta ems_adjustable_surplus_activation_w arvoa.
  - Laske ems_adjustable_surplus_load_priority, jos releiden halutaan aktivoituvan ensin.

## 5. Kaytannon viritysjärjestys

Suositeltu jarjestys kenttakayttoon:

1. Valitse combo tavoitteen mukaan.
2. Aseta prioriteetit ja activation.
3. Aseta ramp ja deadband vakaaksi.
4. Aja 1-3 paivaa tuotantoa ja katso trace-kentat.
5. Tee yksi muutos kerrallaan ja seuraa vaikutus.

## 6. Minimiseuranta traceista

Vahintaan seuraa näitä kenttia ongelmanrajausta varten:

- surplus_dispatch_decision
- surplus_explanation
- ev_policy_mode
- ev_hard_off_active
- ev_low_pv_cycles
- battery_min_floor_reason
- primary_power_envelope_w
- adjustable_surplus_load
- adjustable_primary_load

## 7. Esimerkkiprofiilit

### Profiili P1: EV-ensin perheauto

- Combo A
- activation = 2500 W
- ev_current_step_a = 1 A
- hard_off_pv_threshold = 1.6 kW
- hard_off_low_pv_cycles = 2

Hyoty:
- EV latautuu aggressiivisesti paivalla, mutta matalassa PV:ssa loop-riski pysyy hallinnassa.

### Profiili P2: Akku-ensin vakaus

- Combo B
- activation = 2200 W
- ramp_max_w = 800 W
- deadband_w = 60 W

Hyoty:
- Net zero -saato pysyy pehmeana, EV tulee mukaan vain kun surplus on aidosti kaytettavissa.

## 8. Muistilista ennen tuotantoa

- Varmista, että primary ja surplus ovat eri kohteet.
- Tarkista prioriteetit (isompi numero = korkeampi).
- Tarkista, että activation vastaa kohteen todellista tuotantotasoa.
- Varmista, että hard_off-parametrit vastaavat kausivaihtelua.
