# EMS Tilakaavio

Tama dokumentti kokoaa yhteen kaksi asiaa:

1. Guard-profiilien operaatiotilat
2. Surplus-dispatch-statejen paasiirtymat

## 1) Guard-tilojen kaavio

```mermaid
stateDiagram-v2
    [*] --> NORMAL_LIMITS

    NORMAL_LIMITS --> BATTERY_PROTECT: soc < protect_soc or min_cell < protect_v
    BATTERY_PROTECT --> NORMAL_LIMITS: soc >= protect_soc + margin and min_cell >= protect_v

    NORMAL_LIMITS --> STRICT_LIMITS: user selects STRICT_LIMITS
    STRICT_LIMITS --> NORMAL_LIMITS: user leaves STRICT_LIMITS

    NORMAL_LIMITS --> DEGRADED: stale/invalid battery inverter or soc
    BATTERY_PROTECT --> DEGRADED: stale/invalid battery inverter or soc
    STRICT_LIMITS --> DEGRADED: stale/invalid battery inverter or soc

    DEGRADED --> NORMAL_LIMITS: data fresh and valid, no protect trigger
    DEGRADED --> BATTERY_PROTECT: data fresh and battery protect trigger
```

Tulkitse kaavio nain:

1. `DEGRADED` on data-validiteettiin sidottu turvallisuustila.
2. `BATTERY_PROTECT` on akkukemiaan sidottu suojatila.
3. `STRICT_LIMITS` on kayttajan pakottama rajoitustila.
4. `NORMAL_LIMITS` on perusoptimointitila.

## 2) Surplus-dispatch-statejen kaavio

```mermaid
stateDiagram-v2
    [*] --> IDLE

    IDLE --> ACTIVE: ACTIVATE_*
    ACTIVE --> ACTIVE: ACTIVATE_* (same or next target)
    ACTIVE --> IDLE: RELEASE_* or CLEAR_ALL

    ACTIVE --> FROZEN: freeze_until_ts > now
    FROZEN --> ACTIVE: freeze expired and target still active
    FROZEN --> IDLE: RELEASE_* or CLEAR_ALL

    IDLE --> FROZEN: freeze created on force/activation edge
```

Tulkitse kaavio nain:

1. `ACTIVATE_*` nostaa kohteen aktiiviseksi.
2. `RELEASE_*` ja `CLEAR_ALL` pudottavat aktiivisuuden.
3. `FROZEN` estaa uusia aktivointeja freeze-ikkunan ajan.
4. Freeze voi syntya force- tai aktivointireunasta.

## Kaavioiden suhde pipelineen

EMS-ketju etenee aina jarjestyksessa:

1. policy engine
2. dispatch state applier
3. actuator applier

Siksi tilasiirtyma ja actuator-muutos eivat aina nay samassa 30 s stepissa.

Lisalukeminen:

1. `ems_step_model.md`
2. `arkkitehtuuri.md`
3. `operointi.md`
