# EMS parametroinnin opas

Taman oppaan tavoite on antaa kaytannonlaheiset aloitusarvot ja viritysohjeet
n-device-konfiguraatiolle seka kahdelle yleiselle primary-asetelmalle.

## N-device konfiguraatio

EMS:n tuotantoraja tassa releasessa on:

1. yksi `HOME_BATTERY`
2. `0-n` `kind: RELAY` -laitetta
3. `0-n` `kind: EV_CHARGER` -laturia
4. useampi EV voi olla samassa surplus-kandidaattipoolissa ja saada oman `DevicePolicy`-tuloksen
5. proportional multi-EV power split ja EV-round-robin eivat kuulu tahan releaseen

### Device-id ei kanna semantiikkaa

`RELAY1`, `RELAY2` ja `EV_CHARGER` ovat edelleen valideja device-id:ita, mutta
uusi tuotantologiikka perustuu `kind`, `capabilities`, `policy` ja `adapter`
-kenttiin. Custom device-id voi olla esimerkiksi `RELAY_SAUNA`,
`RELAY_BOILER`, `EV_MAIN` tai `EV_GARAGE`.

Kanoninen runtime-pinta on device-id-pohjainen:

1. `sensor.ems_device_policies_pyscript`
2. `sensor.ems_surplus_dispatch_command_pyscript`
3. `sensor.ems_policy_state_pyscript`
4. `sensor.ems_policy_diagnostics_pyscript`
5. `sensor.ems_active_surplus_devices`
6. `sensor.ems_actuator_writer_trace` ja sen `devices`-map

`runtime.*` entity-id:t ovat kayttajan konfiguroitavia read target -pintoja.
`policy_outputs` ja `diagnostics_outputs` eivat ole kayttajakonfiguraatiota,
vaan EMS:n kiinteita canonical output- ja diagnostics-pintoja.

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

### 2 EV, yksi yhteinen surplus-kandidaattipooli

Useampi EV voi olla konfiguroituna ja jokainen `can_absorb_w=true` +
`policy.surplus_allowed=true` -EV voi osallistua samaan NET_ZERO-pooliin.
Jokaisella EV:lla on oma priority, `max_absorb_w`, force-on, lifecycle-tila ja
`DevicePolicy`-tulos. Julkinen diagnostics seuraa EV-laitteita device-ID-pohjaisesti
ilman selected-single-EV compatibility -kenttaa.

```yaml
ems:
  global_config:
    adjustable_primary_load: input_select.ems_adjustable_primary_load

  devices:
    EV_MAIN:
      kind: EV_CHARGER
      capabilities:
        can_absorb_w: true
        max_absorb_w: input_number.ems_ev_main_max_power_w
      policy:
        priority: input_number.ems_surplus_ev_main_priority
        surplus_allowed: input_boolean.ems_ev_main_surplus_allowed
        surplus_dispatch_mode: max_absorb
      adapter:
        enabled: switch.ev_main_enabled
        current_a: number.ev_main_current_a

    EV_GARAGE:
      kind: EV_CHARGER
      capabilities:
        can_absorb_w: true
        max_absorb_w: input_number.ems_ev_garage_max_power_w
      policy:
        priority: input_number.ems_surplus_ev_garage_priority
        surplus_allowed: input_boolean.ems_ev_garage_surplus_allowed
        surplus_dispatch_mode: max_absorb
      adapter:
        enabled: switch.ev_garage_enabled
        current_a: number.ev_garage_current_a
```

Tarvittavat HA-helperit uudelle EV-laturille ovat tyypillisesti:

1. `input_number.*_min_power_w`
2. `input_number.*_max_power_w`
3. `input_number.*_power_step_w`
4. `input_number.*_priority`
5. `input_boolean.*_surplus_allowed`
6. `surplus_dispatch_mode` YAML-policyssa (`max_absorb` tai `fixed`)
7. lifecycle-/hard-off-parametrit tarvittaessa
8. `switch.*_enabled`
9. `number.*_current_a`
10. EV-adapterin virta-, vaihe- ja janniteparametrit

Erillista `*_activation_threshold_w`-helperia ei tarvita.

Testatut referenssit:

1. `tests/e2e_entity/net_zero_two_ev_one_relay/EMS_config.yaml`
2. `tests/e2e_entity/custom_device_ids_selected_single_ev/EMS_config.yaml`

### Priority, max_absorb_w, capabilities ja surplus_allowed

`priority` maarittaa aktivointijarjestyksen: suurempi numero arvioidaan ennen
pienempaa. Vapautus tapahtuu aktiivisen stackin nykyisen priority-semanttiikan mukaan.

`max_absorb_w` on laitteen suurin sallittu kulutus-/latauspyynto watteina.
Releella sama arvo on usein nimellisteho; EV:lla se on laturin tai sovitun
latausrajan ylaraja; akulla se on latausraja.

**Surplus activation threshold on aina sama arvo:**

```text
surplus activation threshold = device.capabilities.max_absorb_w
```

Esimerkiksi:

```text
EV_GARAGE.max_absorb_w = 3680 W
→ activation threshold = 3680 W

EV_CHARGER.max_absorb_w = 6440 W
→ activation threshold = 6440 W

RELAY1.max_absorb_w = 2600 W
→ activation threshold = 2600 W
```

Erillista `policy.activation_threshold_w`-kenttaa ei ole. Vanha kentta hylataan
strict direct-v2 -parserissa, jotta rinnakkaista totuuslahdetta ei synny.

`capabilities.can_absorb_w=false` estaa positiivisen `target_w`-pyynnon.
`capabilities.can_produce_w=false` estaa negatiivisen `target_w`-pyynnon.
Nama ovat kovia runtime-rajoja, eivat vain dokumentaatiota.

`surplus_allowed` on laitteen kayttolupa surplus-policylle. Jos lupa on pois
paalta, laite voi olla konfiguroituna mutta se ei ole valittavissa
surplus-kohteeksi.

`surplus_dispatch_mode` on eksplisiittinen target-strategia:

1. `max_absorb` -> aktiivisen laitteen target on `max_absorb_w`
2. `fixed` -> aktiivinen kiintea kuorma kayttaa fixed absorb -tehoa; releella
   `min_absorb_w` ja `max_absorb_w` ovat tyypillisesti samat

Strict priority sailyy: korkeampi priority arvioidaan ensin, eika alempi kandidaatti
ohita blokattua ylempaa kandidaattia first-feasible-logiikalla. Taman vuoksi suuri
`max_absorb_w` korkean prioriteetin laitteella on samalla korkea activation gate.
`max_absorb_w`:ta ei pidä laskea pelkkana tuning-kikkana, ellei samalla haluta
rajoittaa laitteen todellista maksimidispatchia.

Lisaa kopioitavia minimiesimerkkeja on tiedostossa `docs/user/config_examples.md`.

## 1. Nopea valinta

Valitse singular primary-laite ja sen jalkeen laitekohtaiset surplus-policyt.
Surplus-poolissa ei ole enaa yhta `adjustable_surplus_load`-valintaa.

- Primary = EV_CHARGER
  - EV hoitaa jatkuvan primary-saannon.
  - HOME_BATTERY voi olla erillinen surplus-kandidaatti, jos sen oma
    `surplus_allowed=true` policy sallii sen.

- Primary = HOME_BATTERY
  - Akku hoitaa jatkuvan primary/residual-saannon.
  - EV voi olla samanaikaisesti surplus-kandidaatti omalla prioritylla ja
    `max_absorb_w`-kynnyksella.

## 2. Yhteiset perusparametrit

Nama kannattaa asettaa ensin kuntoon ennen primary-/priority-viritysta.

- `ems_ramp_max_w`
  - rajoittaa setpointin muutoksen nopeutta per sykli
  - aloitus tyypillisesti 800-1200 W

- `ems_deadband_w`
  - vaimentaa pienta mittausmelua
  - aloitus tyypillisesti 50 W

- `ems_ev_current_step_a`
  - EV-virran porrastus EV-primary-polussa
  - aloitus 1 A tai 2 A

- `ems_ev_hard_off_pv_threshold_kw`
  - matalan PV:n raja hard_off-logiikalle

- `ems_ev_hard_off_low_pv_cycles`
  - perakkaisten low-PV-syklien maara ennen hard_offia

- `ems_ev_hard_off_release_cycles`
  - perakkaisten recovery-syklien maara ennen hard_off-vapautusta

### Surplus eligibility ja priority contract

- `HOME_BATTERY` ja `EV_CHARGER` voivat kumpikin olla samanaikaisesti
  `surplus_allowed=true`.
- `adjustable_surplus_load` on poistettu aktiivisesta global config/runtime -sopimuksesta.
- `adjustable_surplus_activation_w` on poistettu aktiivisesta global config/runtime -sopimuksesta.
- Priority kuuluu aina devicelle, ei adjustable-roolille.
- Allocator jarjestaa kaikki eligible-kandidaatit niiden oman device-priorityn perusteella.
- Activation threshold tulee aina saman laitteen `capabilities.max_absorb_w`:sta.
- HA-helper `ems_adjustable_surplus_load_priority` on yha legacy-niminen, mutta
  nykyisessa production bindingissa se omistaa vain HOME_BATTERYn device-priorityn.

## 3. Primary EV_CHARGER, HOME_BATTERY surplus-kandidaattina

### 3.1 Tyypillinen kayttotapaus

- EV halutaan jatkuvaksi saato-/kulutuskohteeksi.
- Akku voi osallistua surplus-stackiin oman policynsa mukaan.

### 3.2 Suositeltu perusasetelma

- `ems_adjustable_primary_load = EV_CHARGER`
- `HOME_BATTERY.policy.surplus_allowed = true|false` kayttotavoitteen mukaan
- `HOME_BATTERY.policy.priority` eksplisiittisesti
- `HOME_BATTERY.capabilities.max_absorb_w` fyysisen/sovitun latausrajan mukaan
- `ems_surplus_ev_priority` EV:n device-priorityksi, jos EV on myos jossain
  ei-primary-kombossa eligible-kandidaatti
- releille omat priorityt
- `ems_nz_battery_floor_ev_active_w` halutun EV-primary-floorin mukaan

Floor-semanttiikka:

- `ems_nz_battery_floor_default_w` on NET_ZERO:n yleinen akun minimi-floor.
- Kun `ems_adjustable_primary_load = EV_CHARGER`, akun floor tulee arvosta
  `ems_nz_battery_floor_ev_active_w`.

### 3.3 Mitä odottaa kaytannossa

- EV reagoi jatkuvasti primary-polussa.
- Hard_off estaa latauksen matalassa PV:ssa.
- HOME_BATTERYn surplus activation gate on sen oma `max_absorb_w`.
- Primary-only-laite ei saa toista erillista surplus-targetia samassa tickissa.

### 3.4 Ongelma -> toimenpide

- EV kaynnistyy ja pysahtyy liian usein:
  - nosta hard_off low-PV cycle -maaraa
  - kasvata deadbandia maltillisesti

- HOME_BATTERY ei aktivoidu surplus-stackiin:
  - tarkista `surplus_allowed`
  - tarkista priority order
  - tarkista `threshold_w` ja varmista, etta se vastaa `max_absorb_w`:ta
  - tarkista, ylittaako raw RPC saman rajan

## 4. Primary HOME_BATTERY, EV_CHARGER surplus-kandidaattina

### 4.1 Tyypillinen kayttotapaus

- Akku hallitsee jatkuvaa verkko-/akkutehoa.
- EV liittyy mukaan vasta, kun sen oma `max_absorb_w`-gate tayttyy.

### 4.2 Suositeltu perusasetelma

- `ems_adjustable_primary_load = HOME_BATTERY`
- `EV_CHARGER.policy.surplus_allowed = true`
- `EV_CHARGER.policy.priority` haluttuun strict-priority-jarjestykseen
- `EV_CHARGER.capabilities.max_absorb_w` todellisen/sovitun maksimilataustehon mukaan
- releille omat priorityt ja `max_absorb_w`-arvot

Esimerkki:

```text
EV_CHARGER.max_absorb_w = 6440 W
→ EV activation threshold = 6440 W

RELAY1.max_absorb_w = 2600 W
→ RELAY1 activation threshold = 2600 W
```

### 4.3 Mitä odottaa kaytannossa

- Akun target seuraa jatkuvaa RPNZ-saatoa ensisijaisesti.
- EV aktivoituu dispatchin kautta vasta, kun raw RPC ylittaa EV:n
  `max_absorb_w`-rajan ja strict-priority-ehdot sallivat aktivoinnin.
- Release tapahtuu deterministisesti aktiivisen stackin semantiikan mukaan.

### 4.4 Ongelma -> toimenpide

- EV ei aktivoidu vaikka tuotantoa on:
  - tarkista `surplus_allowed`
  - tarkista candidate stack ja priority
  - tarkista `threshold_w`; sen pitaa vastata EV:n `max_absorb_w`:ta
  - tarkista ylittaako raw RPC kynnyksen

- Alempi kandidaatti ei aktivoidu vaikka sen oma teho mahtuisi:
  - tarkista blokkaako korkeampi priority strict-priority-semanticsilla
  - muuta prioritya vain, jos haluttu liiketoimintajarjestys on toinen

- EV:n 6.44 kW gate on kaytannossa liian korkea:
  - arvioi halutaanko EV:n todellinen max dispatch myos pienemmaksi
  - jos kylla, pienempi `max_absorb_w` alentaa seka maksimidispatchia etta activation gatea
  - jos ei, tama on erillinen tuote-/allocator-semanttiikan paatos; erillista
    threshold-overridea ei tassa release-sopimuksessa ole

## 5. Kaytannon viritysjarjestys

1. Valitse primary tavoitteen mukaan.
2. Maarita jokaiselle surplus-laitteelle truthful `max_absorb_w`.
3. Maarita `surplus_allowed`, priority ja dispatch mode per device.
4. Aseta ramp ja deadband vakaaksi.
5. Aja tuotantoa ja seuraa generic candidate diagnostics -kenttia.
6. Tee yksi muutos kerrallaan.

## 6. Minimiseuranta traceista

Vahintaan seuraa naita kenttia ongelmanrajausta varten:

- `surplus_dispatch_action`
- `surplus_explanation`
- `surplus_candidate_device_ids`
- `surplus_candidate_stack`
- `surplus_active_device_ids`
- `surplus_next_device_id`
- `surplus_release_device_id`
- `device_policies` (lopulliset per-device wattitargetit)
- kandidaattien `threshold_w`
- kandidaattien `threshold_source` (odotus: `device_capabilities.max_absorb_w`)
- `device_lifecycle_states`
- `surplus_dispatch_device_id`
- `surplus_candidates`
- `previous_device_states`
- `device_lifecycle_states`

## 6.1 Quarter balance ja RPNZ

- EMS:n kanoninen runtime-avain on `quarter_energy_balance_kwh`.
- Se voi edelleen osoittaa ulkoiseen HA-entityyn `sensor.hourly_energy_balance`.
- `rpnz_w` kuvaa vartin tasapainotusta ja voidaan johtaa kvartaalitaseesta ja jaljella olevasta varttiajasta.
- Esimerkkireuna: `quarter_energy_balance_kwh = -0.001 kWh` vartin alussa tuottaa noin `+4 W` RPNZ:n.
- Tassa tilanteessa `10 W` release-deadband vapauttaa aktiivisen kW-luokan EV:n tai releen, vaikka kynnys on vain `10 W`.

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
