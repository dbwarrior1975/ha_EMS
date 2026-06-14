# EMS parametroitnin opas

Taman oppaan tavoite on antaa kaytannonlaheiset aloitusarvot ja viritysohjeet kahdelle tuetulle V2-kombolle.

## 1. Nopea valinta

Valitse kombinaatio kayttotavoitteen mukaan:

- Combo A: primary = EV_CHARGER, surplus = HOME_BATTERY
  - Paras kun EV halutaan ensisijaiseksi saato-/kulutuskohteeksi.
  - Akusto toimii taustalla smoothaajana ja lisakuormana.

- Combo B: primary = HOME_BATTERY, surplus = EV_CHARGER
  - Paras kun verkkoon vienti ja akun tehohallinta halutaan pitaa ensisijaisena.
  - EV tulee mukaan surplus-kohteena kun aktivointiehto tayttyy.

## 2. Yhteiset perusparametrit

Namma kannattaa asettaa ensin kuntoon ennen kombokohtaista viritysta.

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
- ems_adjustable_surplus_activation_kw = 2500 W
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

- HA-helperin nimi on `ems_adjustable_surplus_activation_kw`.
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
  - Laske ems_adjustable_surplus_activation_kw arvoa, jos release-kynnys on kaytannossa liian korkea.

- Akusto osallistuu liian aikaisin:
  - Nosta ems_adjustable_surplus_activation_kw arvoa, esim 2500 -> 3000 W.

## 4. Combo B: primary HOME_BATTERY, surplus EV_CHARGER

### 4.1 Tyypillinen kayttotapaus

- Kohde, jossa halutaan ensisijaisesti hallita verkko-/akkutehoa ja EV on joustava lisa.
- Tavoite: akku pitaa net zero -tasapainon, EV liittyy mukaan vain riittavassa surplusissa.

### 4.2 Suositellut aloitusarvot

- ems_adjustable_primary_load = HOME_BATTERY
- ems_adjustable_surplus_load = EV_CHARGER
- ems_adjustable_surplus_activation_kw = 2000-2600 W
- ems_adjustable_surplus_load_priority = 3 tai 4
- ems_ev_priority = 2 tai 3
- ems_surplus_relay1_priority = 2
- ems_surplus_relay2_priority = 1
- ems_ev_min_current_a = 6 A
- ems_ev_max_current_a = 28 A

### 4.3 Mitä odottaa kaytannossa

- Akun target seuraa jatkuvaa RPNZ-saatoa ensisijaisesti.
- EV aktivoituu dispatchin kautta vasta activation-ehdolla.
- Release tapahtuu deterministisesti aktiivisten kohteiden prioriteettijarjestyksessa.

### 4.4 Ongelma -> toimenpide

- EV ei aktivoidu vaikka tuotantoa on:
  - Laske ems_adjustable_surplus_activation_kw arvoa, esim 2500 -> 2000 W.
  - Tarkista että required power consumption ylittaa activation-rajan riittavan pitkaan.

- EV aktivoituu liian herkästi:
  - Nosta ems_adjustable_surplus_activation_kw arvoa.
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
