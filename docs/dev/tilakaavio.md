# EMS Tilakaavio

Tama dokumentti kokoaa yhteen EMS:n keskeiset tilasiirtymat:

1. Guard-profiilien operaatiotilat
2. Surplus-dispatch-statejen paasiirtymat
3. EV policy anti-flap/hard_off -tilasiirtymat
4. EV-primary + battery-target authority -siirtymat

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

    IDLE --> ACTIVE: ACTIVATE device_id
    ACTIVE --> ACTIVE: ACTIVATE next device_id
    ACTIVE --> IDLE: RELEASE device_id or CLEAR_ALL

    ACTIVE --> FROZEN: freeze_until_ts > now
    FROZEN --> ACTIVE: freeze expired and target still active
    FROZEN --> IDLE: RELEASE device_id or CLEAR_ALL

    IDLE --> FROZEN: freeze created on force/activation edge
```

Tulkitse kaavio nain:

1. `ACTIVATE` nostaa kanonisen `device_id`-kohteen aktiiviseksi.
2. `RELEASE` ja `CLEAR_ALL` pudottavat aktiivisuuden.
3. `FROZEN` estaa uusia aktivointeja freeze-ikkunan ajan.
4. Freeze voi syntya force- tai aktivointireunasta.

## 3) EV policy anti-flap / hard_off -kaavio

```mermaid
stateDiagram-v2
    [*] --> RESTORE_MIN

    RESTORE_MIN --> BURN: burn_active true (RPNZ/policy path allows)
    BURN --> RESTORE_MIN: burn_active false

    RESTORE_MIN --> HARD_OFF: low PV persistence reached and hard_off_allowed
    BURN --> HARD_OFF: low PV persistence reached and hard_off_allowed

    HARD_OFF --> HARD_OFF: release condition not met
    HARD_OFF --> BURN: release ready cycles >= required and release condition true

    RESTORE_MIN --> RESTORE_MIN: low_pv counter update without threshold crossing
    BURN --> BURN: envelope/step update while burn continues
```

Tulkitse kaavio nain:

1. `RESTORE_MIN` on anti-flap valitila ennen mahdollista hard_offia tai burnia.
2. `HARD_OFF` pysyy aktiivisena kunnes release-ehdot tayttyvat (PV + RPC + hysteresis-syklit).
3. `BURN` on aktiivinen EV-ohjauspolku, jossa EV-current paivittyy envelope/step-saantojen mukaan.

## 4) EV-primary ja battery-target authority -kaavio

```mermaid
stateDiagram-v2
    [*] --> BATTERY_NET_ZERO_CONTROLLER

    BATTERY_NET_ZERO_CONTROLLER --> BATTERY_FLOOR_HOLD: use_ev_primary_mode and ev_policy_mode in (burn, restore_min) and charger_on=true
    BATTERY_FLOOR_HOLD --> BATTERY_NET_ZERO_CONTROLLER: charger_on=false or EV policy no longer active

    BATTERY_FLOOR_HOLD --> BATTERY_FLOOR_HOLD: keep floor while EV actually charging
    BATTERY_NET_ZERO_CONTROLLER --> BATTERY_NET_ZERO_CONTROLLER: normal candidate_sp_net_zero path
```

Tulkitse kaavio nain:

1. EV-primary ei yksin riita lukitsemaan battery flooria, vaan toteutunut lataustila (`charger_on`) ratkaisee restore_min-haaran.
2. `restore_min + charger_on=false` sallii battery-targetin jatkaa normaalia NET_ZERO-saatoa.
3. `restore_min + charger_on=true` aktivoi floor-hold -kayttaytymisen.

## Kaavioiden suhde pipelineen

EMS-ketju etenee aina jarjestyksessa:

1. policy engine
2. dispatch state applier
3. actuator writer loop

Siksi tilasiirtyma ja actuator-muutos eivat aina nay samassa 30 s stepissa.

Huomio aikajarjestykseen:

1. Policy tuottaa saman syklin aikana seka dispatch-paatoksen etta policy-targetit.
2. Dispatch state applier paivittaa aktiivisuusstateja/freezea.
3. Writer paivittaa fyysiset actuatorit, jolloin havaittava laitetila voi muuttua vasta ketjun viimeisessa vaiheessa.

Lisalukeminen:

1. `docs/dev/ems_step_model.md`
2. `docs/dev/arkkitehtuuri.md`
3. `docs/user/operointi.md`
