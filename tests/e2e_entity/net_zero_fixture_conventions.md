# NET_ZERO fixture conventions

Paivays: 2026-07-01

## One-minute summary

NET_ZERO E2E-stepit seedaavat EMS:lle production-equivalent raw runtime
inputit, eivat suoria `rpnz_w`- tai `required_power_consumption_kw`-arvoja.

Kun testissa nakyy:

```python
runtime_inputs_for_net_zero_intent(..., rpnz_w=11.0, required_power_consumption_kw=-6.4)
```

se tarkoittaa fixture intentia. Helper laskee siita raw runtime entityt, joita
EMS oikeasti lukee.

NET_ZERO raw runtime fixtureiden ja `expect_derived`-kaytannon malli on:

```text
RPNZ/RPC shown in helper arguments
    -> fixture helper calculates raw EMS inputs
    -> h.step() applies quarter_energy_balance_kwh, grid_power_w, pv_power_w
    -> harness materializes strict measurements/policy_state/policy_config v3 packets
    -> parse_tick_frame_v3() validates and parses the same runtime contract as production
    -> EMS production code derives RPNZ/RPC internally
    -> expect_derived verifies fixture intent
    -> policy / dispatch / writer expectations are checked
```

## Production runtime contract

Tuotanto-EMS lukee NET_ZERO-derivointiin raw runtime -syotteina ainakin:

1. `quarter_energy_balance_kwh`
2. `grid_power_w`
3. `pv_power_w` silloin kun PV on skenaariossa olennainen

Johdetut arvot kuten:

1. `rpnz_w`
2. `required_power_w`
3. `required_power_consumption_kw`

syntyvat tuotannon derivointilogiikassa, eivat fixture-stepin `set`-osassa.

## Why RPNZ/RPC still appear in tests

RPNZ/RPC ovat edelleen testien kirjoittajalle kayteva tapa ilmaista haluttu
liiketoimintatilanne:

1. paljonko quarter-balance derivoinnin halutaan tuottavan `rpnz_w`:na
2. mika raw-kuorma- tai tuotantotilanne halutaan tulkittavan
   `required_power_consumption_kw`:na

Ne ovat siis fixture intentin shorthand, eivat tuotannon runtime contract.

## What `runtime_inputs_for_net_zero_intent()` returns

`runtime_inputs_for_net_zero_intent()` palauttaa sanakirjan, joka sisaltaa:

1. `quarter_energy_balance_kwh`
2. `grid_power_w`
3. valinnaisesti `pv_power_w`

Helper:

1. laskee `quarter_energy_balance_kwh` arvosta `rpnz_w` ja vartin
   jaljella olevasta ajasta
2. laskee `grid_power_w` arvosta `required_power_consumption_kw`,
   quarter-balance-arvosta ja vartin jaljella olevista minuuteista
3. muuntaa tarvittaessa `pv_power_kw` -> `pv_power_w`

## What `expect_derived` validates

`expect_derived_for_net_zero_intent()` rakentaa odotetun derivointituloksen
samalle fixture intentille.

Runner vertaa sita tuotannon `derive_net_zero_inputs()`-funktion tulokseen.

Jos vertailu epaonnistuu, ensisijainen tulkinta on:

1. fixture on rakennettu vaarin
2. yksikoissa on virhe (`W` vs `kW`)
3. raw runtime -arvot eivat vastaa aiottua business intentia

Vasta taman jalkeen kannattaa epailla policy-, dispatch- tai writer-regressiota.

## Example with helper

```python
{
    'at_s': 120,
    'note': (
        't120 intent: RPNZ=11 W, RPC=-6.4 kW, PV=1.4 kW. '
        'Low PV cannot sustain EV burn, so release/hard-off path is eligible.'
    ),
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

Tassa helper piilottaa sen, miten `quarter_energy_balance_kwh` ja
`grid_power_w` rakennetaan.

## Same example without helper

Sama idea voidaan kirjoittaa auki ilman helperia:

```python
{
    'at_s': 120,
    'set': {
        E['quarter_energy_balance_kwh']: balance_for_rpnz_w(11.0, seconds_until_next_quarter(120)),
        E['grid_power_w']: grid_power_for_required_power_kw(
            -6.4,
            balance_for_rpnz_w(11.0, seconds_until_next_quarter(120)),
            float(remaining_template_minutes(120)),
        ),
        E['pv_power_w']: 1400.0,
    },
    'expect_derived': {
        'rpnz_w': 11,
        'required_power_w': -6400,
        'required_power_consumption_kw': -6.4,
        'remaining_quarter_s': seconds_until_next_quarter(120),
        'remaining_quarter_min': float(remaining_template_minutes(120)),
    },
}
```

Oleellinen havainto: raw-input-versiossakaan `set` ei kirjoita `rpnz_w`- tai
`required_power_consumption_kw`-avaimia EMS:lle.

## Fixture error vs policy regression

Kayta seuraavaa jarjestysta, kun NET_ZERO E2E epaonnistuu:

1. tarkista `expect_derived` vastaan tuotannon derivointi
2. tarkista raw runtime -syotteiden yksikot ja merkit
3. vasta sitten tarkista `expect_policy`, `expect_device_policies`,
   `expect_dispatch_state` ja writer-odotukset

Jos `expect_derived` jo pettää, policy-tason assertit ovat usein vain
seurausvirheita.

## What not to do

Ala tee NET_ZERO E2E-steppeihin suoria runtime-kirjoituksia avaimille:

1. `rpnz_w`
2. `required_power_consumption_kw`
3. `required_power_w`
4. `pv_power_kw`

Ala muuta policy-, dispatch- tai writer-odotusarvoja vain siksi, etta
raw-input-migraatio tai dokumentaatiomuutos menee lapi.

Muista yksikot:

1. `grid_power_w`, `pv_power_w`, `rpnz_w`, `required_power_w` ovat watteja
2. `required_power_consumption_kw` on kilowatteja
3. `quarter_energy_balance_kwh` on kilowattitunteja

## Migration-status caveat

Kaikki olemassa olevat NET_ZERO-stepit eivat viela kayta eksplisiittista
`intent: RPNZ=..., RPC=..., PV=...` note-tyylia. Uusissa tai muuten
kosketetuissa steppeissa sita kannattaa suosia, mutta taman dokumentin tavoite
on ensisijaisesti selittaa nykyinen fixture-konventio ilman laajaa
massaeditointia.
