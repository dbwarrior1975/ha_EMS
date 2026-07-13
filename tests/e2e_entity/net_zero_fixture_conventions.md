# NET_ZERO fixture conventions

Päiväys: 2026-07-12

## Yhteenveto

NET_ZERO E2E-stepit seedaavat production-equivalent raw runtime -inputit, eivät
suoria `rpnz_w`- tai `required_power_consumption_kw`-arvoja.

```python
runtime_inputs_for_net_zero_intent(
    ...,
    rpnz_w=11.0,
    required_power_consumption_kw=-6.4,
    at_s=120,
)
```

RPNZ/RPC ovat fixture-intent. Helper muodostaa niistä EMS:n lukemat raw-arvot:

```text
quarter_energy_balance_kwh
grid_power_w
pv_power_w (valinnainen)
```

## Runtime-polku

```text
fixture intent RPNZ/RPC
-> helper laskee raw runtime inputit sekuntihorisontilla
-> h.step() päivittää entityt
-> harness muodostaa strict v5 runtime packets
-> parse_tick_frame_v5() validoi contractin
-> derive_net_zero_inputs() laskee RPNZ/RPC:n tuotantokoodilla
-> expect_derived varmistaa intentin
-> policy / dispatch / writer assertit ajetaan
```

## Sekuntipohjainen derivointi

```text
remaining_s = seconds_until_next_quarter(at_s)
control_horizon_s = max(remaining_s, 30)
quarter_balance_kwh = -(rpnz_w / 1000) * control_horizon_s / 3600
target_grid_w = -(quarter_balance_kwh * 3 600 000 / control_horizon_s)
grid_power_w = target_grid_w - required_power_w
```

Odotettu diagnostics:

```text
remaining_quarter_s = remaining_s
remaining_quarter_min = remaining_s / 60
control_horizon_s = max(remaining_s, 30)
```

Kokonaisia template-minuutteja ei käytetä.

## Helper-esimerkki

```python
{
    'at_s': 120,
    'set': runtime_inputs_for_net_zero_intent(
        E,
        rpnz_w=11.0,
        required_power_consumption_kw=-6.4,
        at_s=120,
        pv_power_kw=1.4,
    ),
    'expect_derived': expect_derived_for_net_zero_intent(
        rpnz_w=11.0,
        required_power_consumption_kw=-6.4,
        at_s=120,
    ),
}
```

## Sama ilman helperia

```python
remaining_s = seconds_until_next_quarter(120)
balance = balance_for_rpnz_w(11.0, remaining_s)

{
    'at_s': 120,
    'set': {
        E['quarter_energy_balance_kwh']: balance,
        E['grid_power_w']: grid_power_for_required_power_kw(
            -6.4,
            balance,
            remaining_s,
        ),
        E['pv_power_w']: 1400.0,
    },
    'expect_derived': {
        'rpnz_w': 11,
        'required_power_w': -6400,
        'required_power_consumption_kw': -6.4,
        'remaining_quarter_s': remaining_s,
        'remaining_quarter_min': remaining_s / 60.0,
        'control_horizon_s': max(remaining_s, 30.0),
    },
}
```

## Virheen paikannus

Kun skenaario epäonnistuu:

1. tarkista `expect_derived` vastaan tuotannon derivointi
2. tarkista raw-inputtien merkit ja yksiköt
3. tarkista vasta sen jälkeen policy-, dispatch- ja writer-odotukset

Yksiköt:

```text
grid_power_w, pv_power_w, rpnz_w, required_power_w = W
required_power_consumption_kw = kW
quarter_energy_balance_kwh = kWh
remaining_quarter_s, control_horizon_s = s
```

Älä kirjoita fixture-stepin `set`-osaan suoraan `rpnz_w`,
`required_power_w`, `required_power_consumption_kw` tai `pv_power_kw` -avaimia.
