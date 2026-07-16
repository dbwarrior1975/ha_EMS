# Regressiolaskentojen referenssi

Tämä dokumentti säilyttää kehittäjälle tärkeät numeeriset invariantit ilman käyttäjäoppaan vaihehistoriaa.

## Sekuntipohjainen RPC

```text
19:57:34
balance = -0.068 kWh
grid = -450 W
remaining = 146 s
```

Odotus:

```text
control_horizon_s = 146
rpnz_w = 1677
required_power_w = 2127
required_power_consumption_kw = 2.127
```

Tasaminuutin 19:57:59 → 19:58:00 ei pidä tehdä whole-minute-horizon-hyppyä.

## Final 30 seconds

Kun `remaining_quarter_s < 30`, sekä RPNZ että RPC käyttävät `control_horizon_s = 30`. Diagnostics säilyttää todellisen remaining-arvon.

## Primary below minimum

```text
request = 900 W
EV min = 1840 W
fallback battery step = 100 W
```

Odotus:

```text
EV skipped: below_min_absorb_w
battery selected
unserved = 0
```

## Producer ceiling

```text
request = 3200 W
producer ceiling = 1000 W
```

Odotus:

```text
allocated = 1000 W
final target = -1000 W
unserved = 2200 W
```

## Producer priority ja step-jäännös

Alempaa produceria ei avata pelkän ylemmän producerin step-jäännöksen vuoksi, jos ylemmän reachable hard ceiling kattaisi koko pyynnön. Zero-ceiling tai unavailable producer sen sijaan ohitetaan.

## Guard

```text
producer_requested_w > 0
effective ceiling = 0
```

Odotus:

```text
allocation = 0
unserved = request
```

## FORCE_ON

EV:n FORCE_ON-commandia ei vähennetä erikseen grid-feedbackista. Toteutunut kuorma näkyy grid-mittauksessa; erillinen vähennys double-counttaisi sen.

## Low-PV saturation

Kun `hard_off_low_pv_cycles = N`:

```text
N-1 → N → N → N
```

Persisted arvo `> N` normalisoituu ensimmäisellä ajolla arvoon `N`. Vakaa HARD_OFF ei saa muuttaa Policy State keytä.


## PV-only HARD_OFF release

Kun EV on HARD_OFFissa ja `hard_off_release_cycles = 2`:

```text
tick 1: PV >= threshold, RPC alle EV-kynnyksen → release_ready = 1, HARD_OFF true
tick 2: PV >= threshold, alempi relay voi olla aktiivinen → release_ready = 2, HARD_OFF false
```

Vapautumistickillä EV:n surplus-DevicePolicy pysyy pois päältä, ellei EV ole jo persisted active -listassa tai FORCE_ON. Myöhempi `ACTIVATE EV_CHARGER` syntyy vasta RPC:n ja priorityn täyttyessä. PV:n putoaminen kynnyksen alle tai `activation_blocked=true` nollaa release-counterin.

## Incremental n−1 surplus release

Esimerkki:

```text
activation order: EV_CHARGER 4000 W → RELAY1 2700 W
RPNZ: positiivinen
RPC: -2700 W
```

RELAY1 on uusin n−1-portaan laite. Sen marginaali on `max(100, 0.05 × 2700) = 135 W`, joten release-kynnys on `2565 W`. Koska excess on `2700 W`, päätös on `RELEASE RELAY1`. Päätös asettaa measurement-settle-freezen; EV jää anchoriksi.

Rajatestit:

```text
RPC -2564 W → hold RELAY1
RPC -2565 W → release RELAY1
```

Kun jäljellä on vain EV-anchor, `RPNZ <= 10 W` voi vapauttaa sen nykyisen konservatiivisen säännön mukaan. Positiivinen RPNZ ei estä n−1-releaseä, jos negatiivinen RPC osoittaa uusimman lisäportaan suuruisen ylikulutuksen.

