# Ensikäynnistyksen tarkistuslista

## Vaihe 1: turvallinen tila

- aseta control `MANUAL_SAFE`
- aseta akku, EV ja releet turvallisiin manuaalisiin tiloihin
- varmista, ettei toinen automaatio kirjoita samoja actuator-entiteettejä

## Vaihe 2: runtime-contract

Tarkista `sensor.ems_policy_diagnostics_pyscript`:

```text
config_runtime_ok: true
config_grouped_production_ready: true
runtime_input_contract: direct_tick_frame_v5
policy_engine_runtime_packet_schema_version: 5
policy_engine_runtime_packet_missing_fields: 0
```

Runtime policy revisionin pitää olla numeerinen ja pysyä vakaana, kun helperit eivät muutu.

## Vaihe 3: mittausmerkit

Testaa tunnetulla tilanteella:

- verkkotuonti näkyy odotetulla merkillä
- verkkovienti näkyy vastakkaisella merkillä
- akun positiivinen target tarkoittaa latausta
- akun negatiivinen target tarkoittaa purkua
- PV on watteina
- varttitase on kilowattitunteina

Väärä merkki voi tehdä ohjauksesta positiivisen feedback-loopin.

## Vaihe 4: device registry ja writer

Tarkista writer trace:

```text
writer_policy_contract: devices
actuator_writes_suppressed: false
error_code: tyhjä
```

Varmista jokaiselle laitteelle:

- oikea `device_id`
- oikea kind
- oikea actuator entity
- writerin target vastaa DevicePolicy-targetia

## Vaihe 5: primary resolver

Tarkista:

```text
configured_primary_consuming_device_ids
ordered_primary_consuming_device_ids
effective_primary_consuming_device_id
effective_primary_consuming_reason
primary_consuming_skipped_by_id
unserved_primary_consuming_w
```

Kokeile pientä pyyntöä, joka jää EV:n minimin alle. Odotettu tulos EV → skip ja akku → effective primary, jos akku on fallback-listassa.

## Vaihe 6: surplus ilman actuator-kytkentää

Pidä surplus-laitteiden `surplus_allowed` pois päältä tai prioriteetit nollassa, kunnes primary-säätö on validoitu. Aktivoi laitteet yksi kerrallaan ja tarkista:

```text
surplus_next_device_id
surplus_next_threshold_kw
surplus_dispatch_action
surplus_active_device_ids
```

## Vaihe 7: producer

Testaa pienellä, turvallisella purkurajalla:

```text
producer_requested_w
producer_effective_hard_ceiling_w_by_id
producer_allocated_w_by_id
unserved_production_w
```

Guardin tai SOC-rajan pitää pystyä tekemään ceilingistä 0 W.

## Vaihe 8: HARD_OFF

Testaa EV:n lifecycle hallitusti:

- low-PV counter kasvaa vain konfiguroituun kynnykseen
- HARD_OFF pysyy latchattuna
- vakaa HARD_OFF ei julkaise Policy Statea joka tickillä
- release counter kasvaa vain palautumisehdon aikana
- FORCE_ON toimii odotetulla precedence-säännöllä

## Vaihe 9: automaattitila

Vaihda `AUTOMATIC`-tilaan vasta, kun kaikki yllä olevat kohdat ovat kunnossa. Seuraa ensimmäiset vartit aktiivisesti ja pidä rollback valmiina.
