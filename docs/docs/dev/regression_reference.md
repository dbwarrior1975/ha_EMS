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
