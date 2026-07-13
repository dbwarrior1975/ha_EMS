# Testaus ja release-portit

## Ajo

```bash
pytest -q tests
```

Markerit:

```text
unit
scenario
smoke
```

## Kerrokset

### Unit

- config- ja runtime v5 -parserit
- sekuntipohjainen RPNZ/RPC ja 30 s horizon floor
- primary resolver
- producer allocation, ceiling, minimum ja step
- surplus eligibility ja dispatch
- EV lifecycle, FORCE_ON ja guardit
- writer fail-closed

### Contract

- grouped config
- runtime schema 5
- canonical sensorit
- template-attribuuttien muoto
- relay producer-defaultit
- Pyscript AST -yhteensopivuus

### E2E

- 0-primary
- no-EV / no-relay
- useita releitä ja EV-latureita
- custom device-ID:t
- guard- ja stale-data-skenaariot
- primary fallback ja HARD_OFF
- writer- ja dispatch-ketju

## Release gate

1. full suite työpuusta
2. Python compile
3. YAML parse
4. Markdown linkki- ja fence-audit
5. template/example contract audit
6. source term/legacy audit
7. staging ilman `.git`, cacheja ja bytecodea
8. ZIP integrity
9. extract uuteen tyhjään hakemistoon
10. full suite fresh extractista
11. SHA-256

## Dokumentaatioaudit

Aktiivisissa käyttäjädokumenteissa ei saa olla:

- vanhoja runtime schema -ohjeita
- yksittäistä singular primary-configia
- sisäisiä testifunktion nimiä käyttäjärajoitteen korvikkeena
- kopioitavalta näyttäviä mutta strict-schemaa rikkovia osittaisia paketteja
- paikallisen tuotantoympäristön entity-ID:itä aktiivisissa esimerkeissä

## Tunnettu expected failure

HAEO NET_ZERO -kombinaatiolla on yksi rajattu tunnettu expected failure. Käyttäjävaikutus dokumentoidaan `docs/user/known_limitations.md`:ssä. Testin odotusta ei saa löysentää ilman domain-päätöstä ja toteutusta.
