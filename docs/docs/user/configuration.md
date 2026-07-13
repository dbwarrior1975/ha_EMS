# Konfigurointi

## Konfiguraatiokerrokset

| Kerros | Vastuu |
|---|---|
| `/config/EMS_config.yaml` | staattinen topologia, kindit, suunnat, roolit ja cadence |
| `sensor.ems_policy_config_runtime` | hitaasti muuttuva strict v5 policy config ja entity registry |
| `sensor.ems_measurements_runtime` | nopeat mittaukset ja actuator-state |
| `sensor.ems_policy_state_runtime` | lifecycle-, HAEO- ja jatkuvuustila |

Pakollisen kentän puuttuminen failaa suljetusti. Älä rakenna puuttuville lähteille hiljaista nollafallbackia.

## Signed target

```text
+W = kuluta / absorboi / lataa
-W = tuota / pura
 0 = ei tehopyyntöä
```

Varmista grid-mittauksen merkki käytännön testillä. Dokumentaation laskenta olettaa, että negatiivinen grid-teho tarkoittaa vientiä ja positiivinen tuontia.

## Primary-consuming fallback

Canonical kenttä on järjestetty lista:

```yaml
primary_consuming_device_ids:
  - EV_CHARGER
  - HOME_BATTERY
```

Kandidaatilla pitää olla:

```yaml
can_absorb_w: true
supports_primary_consuming_regulation: true
```

Resolveri valitsee ensimmäisen juuri sillä tickillä toteutuskelpoisen laitteen. EV voidaan ohittaa esimerkiksi HARD_OFFin, activation blockin tai alle `min_absorb_w`:n jäävän pyynnön vuoksi. Tyhjä lista on validi 0-primary-topologia.

EMS ei valitse listan ulkopuolista laitetta automaattisesti.

### Suositus EV + akku

```yaml
primary_consuming_device_ids:
  - EV_CHARGER
  - HOME_BATTERY
```

EV ottaa suuremman toteutuskelpoisen pyynnön. Akku toimii hienosäätö- ja availability-fallbackina.

## `surplus_allowed`

`surplus_allowed` koskee vain discretionary surplus -poolia. Se ei portita primary-authorityä. Effective primary poistetaan surplus-poolista saman policy-ajon ajaksi.

Normaali asetus voi siksi olla:

```yaml
policy:
  surplus_allowed: true
```

sekä EV:lle että akulle.

## EV capabilityt ja adapteri

EV tarvitsee vähintään:

```yaml
capabilities:
  can_absorb_w: true
  can_produce_w: false
  uses_hard_off_lifecycle: true
  supports_primary_consuming_regulation: true
  supports_producing_regulation: false
  min_absorb_w: 1840
  max_absorb_w: 7400
  min_produce_w: 0
  max_produce_w: 0
  step_w: 230
policy:
  priority: 40
  producing_priority: 0
  surplus_allowed: true
  force_on: false
  low_pv_threshold_w: 1600
  hard_off_low_pv_cycles: 15
  hard_off_release_cycles: 3
  surplus_dispatch_mode: max_absorb
adapter:
  enabled: switch.ems_ev_charger_enabled
  current_a: number.ems_ev_charger_current_a
  current_step_a: 1
  phases: 1
  voltage_v: 230
```

Esimerkki on rakenneote. Kopioitava täydellinen policy-paketti on `template.yaml`-tiedostossa.

EV:n alle-minimipyyntöä ei nosteta minimiin; resolveri kokeilee seuraavaa primary-kandidaattia.

## Battery capabilityt, guard ja adapteri

```yaml
capabilities:
  can_absorb_w: true
  can_produce_w: true
  uses_hard_off_lifecycle: false
  supports_primary_consuming_regulation: true
  supports_producing_regulation: true
  min_absorb_w: 0
  max_absorb_w: 3500
  min_produce_w: 0
  max_produce_w: 4000
  step_w: 100
policy:
  priority: 10
  producing_priority: 100
  surplus_allowed: true
  force_on: false
  surplus_dispatch_mode: max_absorb
```

Akun guard-lähteiden pitää sisältää SOC, min-cell ja heartbeat. Producer hard ceiling voi mennä nollaan guardin vuoksi, vaikka feedback tunnistaa purkutarpeen.

## Producer-pooli

Producer-jäsenyys vaatii:

```text
can_produce_w = true
supports_producing_regulation = true
```

Suurempi `producing_priority` käsitellään ensin. `min_produce_w` ja `max_produce_w` ovat positiivisia magnitudeja, vaikka final target on purkusuunnassa negatiivinen.

Zero-ceiling tai unavailable producer ohitetaan. Toteutumaton pyyntö näkyy `unserved_production_w`:ssa.

## Releet

Ei-tuottavalle releelle määritä eksplisiittisesti:

```yaml
capabilities:
  can_absorb_w: true
  can_produce_w: false
  supports_primary_consuming_regulation: false
  supports_producing_regulation: false
  min_absorb_w: 2700
  max_absorb_w: 2700
  step_w: 2700
  min_produce_w: 0
  max_produce_w: 0
policy:
  priority: 30
  producing_priority: 0
  surplus_allowed: true
  force_on: false
  surplus_dispatch_mode: fixed
```

`priority` määrittää surplus-järjestyksen. Se ei ole sama kuin primary-listan järjestys tai `producing_priority`.

## Controllerin perusarvot

Suositeltu beta-aloitus:

```text
policy interval = 5 s
diagnostics interval = 30 s
```

Keskeiset parametrit:

- `deadband_w`: estää pienen virheen jatkuvaa sahausta
- `ramp_w`: rajoittaa targetin muutosta yhdellä ajolla
- `step_w`: laitekohtainen toteutusaskel
- `surplus_freeze_s`: antaa mittauksille aikaa settleä dispatchin jälkeen
- `strict_limit_w`: eksplisiittinen kokonaisraja `STRICT_LIMITS`-tilassa

Älä aloita alle viiden sekunnin cadencella ilman suorituskykymittausta.

## Guardit

- `NORMAL_LIMITS`: normaali optimointi
- `BATTERY_PROTECT`: estää haitallisen purun ja voi käyttää charge-flooria
- `STRICT_LIMITS`: clampaa targetit käyttäjän rajaan
- `DEGRADED`: stale/invalid data; producer authority estetään

## Konfiguraation hyväksymiskriteerit

- `runtime_input_contract = direct_tick_frame_v5`
- runtime packet schema on 5
- `policy_engine_runtime_packet_missing_fields = 0`
- configured primary -listassa on vain tunnettuja capability-yhteensopivia device-ID:itä
- jokaisella writerin ohjaamalla laitteella on entity registry -mapping
- releillä ja EV:illä on `min_produce_w: 0` ja `max_produce_w: 0`
- akun max-produce on positiivinen magnitude
- kaikki mittausyksiköt ja merkit on testattu
