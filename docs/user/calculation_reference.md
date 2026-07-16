# Laskentareferenssi

## 1. Varttitaseesta grid-targetiksi

```text
quarter_energy_balance_kwh = -0.068 kWh
remaining_quarter_s = 146 s
control_horizon_s = max(146, 30) = 146 s
```

```text
target_grid_w = -(-0.068 × 3 600 000 / 146)
              = +1676.7 W
rpnz_w        = +1677 W
```

## 2. RPC käyttää sekunteja

Kun mitattu grid on `-450 W`:

```text
rpc_w = target_grid_w - grid_power_w
      = +1676.7 - (-450)
      = +2126.7 W
      ≈ +2127 W
```

```text
required_power_consumption_kw = 2.127 kW
remaining_quarter_min = 146 / 60 = 2.4333 min
```

`remaining_quarter_min` on diagnostiikkaa eikä laskentasyöte. Viimeisten 30 sekunnin aikana sekä RPNZ että RPC käyttävät 30 sekunnin minimihorisonttia.

## 3. Primary fallback

```text
positive request = 900 W
EV min_absorb_w = 1840 W
```

```text
EV_CHARGER → skip: below_min_absorb_w
HOME_BATTERY → selected: 900 W, step/ramp-rajojen sisällä
```

Toteutumaton osa näkyisi `unserved_primary_consuming_w`:ssa, jos seuraavaakaan kandidaattia ei ole.

## 4. Producer ceiling

```text
desired signed target = -3200 W
producer request = 3200 W
battery effective hard ceiling = 1000 W
```

```text
allocated = 1000 W
final DevicePolicy.target_w = -1000 W
unserved_production_w = 2200 W
```

## 5. Fixed export-balance stop

Nykyisessä beta-versiossa RPC pakotetaan nollaan, jos:

```text
quarter_energy_balance_kwh >= +0.130 kWh
```

Tämä on kiinteä, ei-konfiguroitava suojapolku. RPNZ voi silti olla ei-nolla. Vaikutus ja perustelu on kuvattu [tunnetuissa rajoitteissa](known_limitations.md).

Yksityiskohtaiset regressiotapaukset ovat kehittäjädokumentissa [../dev/regression_reference.md](../dev/regression_reference.md).
