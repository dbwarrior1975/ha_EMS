# Hardcoded Not Read From YAML

Paivays: 2026-06-16

Tama dokumentti listaa ne device-mallin kohdat, jotka ovat edelleen joko
kovakoodattuja runtimeen tai johdettuja muusta konfiguraatiosta sen sijaan,
etta ne tulisivat aidosti geneerisena laitemallina `EMS_config.yaml`-tasolta.

Tarkoitus ei ole kuvata kaikkea "legacyksi", vaan erottaa:

1. mita YAML ohjaa jo suoraan
2. mita runtime johtaa edelleen tunnetun laitejoukon perusteella
3. mita deprecated adapter -polku yha kantaa mukanaan

## Nykyinen status

Nykytila on selkeasti aiempaa YAML-driven, mutta ei viela taysin
device-generic:

- grouped config ja structured config -polut ovat olemassa
- `config_loader.py` lukee ja validoi YAML-rakennetta
- `device_read_model.py` lukee nyt `CoreConfig`-polulla device-capabilities- ja
  policy-kenttia suoraan rakenteisesta konfiguraatiosta
- legacy `EmsConfig` -polku on olemassa vain deprecated scalar adapterina
- production runtime nojaa `CoreConfig.devices`-registryyn, ei legacy scalar
  parityyn

Tama tarkoittaa, etta read-model on jo kanoninen, ja legacy-scalar-view on
rajattu adapteripintaan.

## Mita YAML ohjaa jo suoraan

`CoreConfig`-polulla `build_device_configs()` lukee seuraavat kentat suoraan
device-rakenteesta:

### HOME_BATTERY

- `ems.devices.HOME_BATTERY.capabilities.can_absorb_w`
- `ems.devices.HOME_BATTERY.capabilities.can_produce_w`
- `ems.devices.HOME_BATTERY.capabilities.min_absorb_w`
- `ems.devices.HOME_BATTERY.capabilities.max_absorb_w`
- `ems.devices.HOME_BATTERY.capabilities.max_produce_w`
- `ems.devices.HOME_BATTERY.capabilities.step_w`
- `ems.devices.HOME_BATTERY.policy.priority`

### EV_CHARGER

- `ems.devices.EV_CHARGER.capabilities.can_absorb_w`
- `ems.devices.EV_CHARGER.capabilities.can_produce_w`
- `ems.devices.EV_CHARGER.capabilities.min_absorb_w`
- `ems.devices.EV_CHARGER.capabilities.max_absorb_w`
- `ems.devices.EV_CHARGER.capabilities.max_produce_w`
- `ems.devices.EV_CHARGER.capabilities.step_w`
- `ems.devices.EV_CHARGER.policy.priority`

### RELAY1 ja RELAY2

- `ems.devices.RELAY1.capabilities.*`
- `ems.devices.RELAY1.policy.priority`
- `ems.devices.RELAY2.capabilities.*`
- `ems.devices.RELAY2.policy.priority`

Lisaksi relayjen aktiivisen state-tehon mallinnus kayttaa `CoreConfig`-polulla
device capabilityn `max_absorb_w` -arvoa.

## Mika on edelleen aidosti kovakoodattua

### 1. Runtime nojaa edelleen tunnettuun device-kategoriaan, mutta ei legacy scalar -view'hun

Tiedosto:

- [modules/ems_adapter/device_read_model.py](/home/virtamik/code/ha_EMS/modules/ems_adapter/device_read_model.py)

CoreConfig-polulla runtime rakentaa laitteet registryssa olevista deviceista.
Nykyiset esimerkit kayttavat viela tuttua nimisarjaa:

- `HOME_BATTERY`
- `EV_CHARGER`
- `RELAY1`
- `RELAY2`

Nama id:t ovat edelleen esimerkkikonfiguraatiossa, mutta tuotantopolku ei enaa
riipu legacy EmsConfig -paritysta.

### 2. `response_kind` johdetaan edelleen runtime-logiikalla

Taman hetken read-model paattelee edelleen:

- battery -> `response_kind = 'continuous'`
- EV -> `response_kind = 'selector'`
- relay -> `response_kind = 'relay'`

Tama ei tule geneerisena kenttana YAML:sta, vaan tunnetun laitejoukon
semantiikasta.

## Mika on edelleen deprecated adapter -polun kuormaa

Kun kaytossa on vanha `EmsConfig`-adapteriview, capabilityt johdetaan edelleen
legacy scalar -kentista eika canonical `CoreConfig.devices`-rakenteesta.

### HOME_BATTERY legacy-polulla

Legacy-polulla kaytetaan edelleen seuraavia oletuksia:

- `response_kind = 'continuous'`
- `can_absorb_w = True`
- `can_produce_w = True`
- `min_absorb_w = 0`

Ja seuraavat rajat johdetaan vanhoista config-kentista:

- `max_absorb_w <- cfg.max_solar_charge_w`
- `max_produce_w <- cfg.max_battery_discharge_w`
- `priority <- cfg.adjustable_surplus_load_priority`

### EV_CHARGER legacy-polulla

Legacy-polulla kaytetaan edelleen:

- `response_kind = 'selector'`
- `can_absorb_w = True`
- `can_produce_w = False`
- `max_produce_w = 0`

Tehorajat johdetaan edelleen vanhoista config-kentista:

- `ev_min_current_a`
- `ev_max_current_a`
- `ev_current_step_a`
- `ev_charger_phases`

### RELAY1 ja RELAY2 legacy-polulla

Legacy-polulla relayt ovat edelleen kiinteita:

- `response_kind = 'relay'`
- `can_absorb_w = True`
- `can_produce_w = False`
- `max_produce_w = 0`

Relayjen tehot johdetaan edelleen legacy-configista:

- `relay1_power_kw`
- `relay2_power_kw`

## Mitka kohdat eivat viela ole taysin device-generic

Vaikka capability-luenta toimii nyt `CoreConfig`-polulla, seuraavat kohdat
eivat viela ole koko runtime-polun kanonista device-generic-toteutusta:

1. device-listan koko ja rakenne ovat yha example-konfiguraation ja domain-
   semantiikan ohjaamia
2. `response_kind` ei ole YAML:n eksplisiittinen kanoninen kentta
3. legacy `EmsConfig` -polku on edelleen adapterissa, ei production runtime -
   polussa
4. muut runtime-moduulit eivat viela ole taysin vapaita nimellisyhteensopivuuden
   helper-aliasista, vaikka canonical data tulee registrysta

## Device state -tasolla jaljella olevat runtime-oletukset

Device state -mallissa on edelleen oletuksia, jotka eivat ole konfiguraatiota
vaan ajonaikaista tulkintaa:

- EV: `available = True`
- RELAY1: `available = True`
- RELAY2: `available = True`
- BATTERY: `guard_state = 'OK'` tai `'STALE'`

Naita ei pideta varsinaisena YAML-puutteena, mutta ne muistuttavat siita, etta
kaikki device-state ei kuulu configiin.

## Refaktoroinnin kannalta olennaisin loppuluettelo

Jos halutaan vieda EMS aidosti siihen pisteeseen, etta laitteet ovat vain
konfiguraatiota, taman dokumentin ydin on nyt tassa:

1. canonical device-registry on tuotannon totuus, mutta nimialiasit elavat viela
   adaptereissa
2. `response_kind` on viela johdettu tunnetusta laitejoukosta
3. legacy `EmsConfig` -polku on rajoitettu deprecated adapteriin
4. muut tuotantopolun moduulit kayttavat jo registry/context -mallia, mutta osa
   nimialiasista on viela yhteensopivuussyista mukana
5. state-malli kantaa edelleen perusteltuja runtime-oletuksia, jotka eivat ole
   YAML:n device-dataa

Tama tekee dokumentista hyvan refaktorointilistan seuraaville vaiheille:

- ensin runtime-contextin compatibility-oletusten kaventaminen
- sitten tunnetun laitejoukon oletusten purku
- lopuksi aidosti geneerisempi laitemalli
