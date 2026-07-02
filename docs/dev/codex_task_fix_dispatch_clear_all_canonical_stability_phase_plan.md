# Phase plan: fix dispatch CLEAR_ALL canonical stability

Paivays: 2026-07-02

Lahdehavainto: `docs/dev/codex_task_fix_dispatch_clear_all_canonical_stability.md`

## Tavoite

Korjaa tuotantohavainto, jossa `policy_diagnostics` julkaistuu edelleen noin
5 sekunnin valein syyllä `canonical_changed`, vaikka
`diagnostics_interval_seconds=30` ja policy-tilanne on vakaa.

Todennakoinen varsinainen bugi ei ole diagnostiikan throttlaus vaan
canonical dispatch payloadin epavakaus:

```text
stable policy inactive state
-> dispatch action CLEAR_ALL
-> surplus_freeze_until_ts saa now_ts-arvon
-> dispatch_command_hash muuttuu joka policy-ajolla
-> canonical_changed=True
-> policy_diagnostics julkaistaan joka policy-ajolla
```

Korjauksen jalkeen vakaa `CLEAR_ALL` / inactive-policy -komento on idempotentti:
sen canonical attrsit ja `dispatch_command_hash` eivat muutu pelkan kellonajan
etenemisen takia.

## Nykykoodin havaittu kartta

Keskeiset kohdat:

```text
modules/ems_core/net_zero/engine.py
  compute_net_zero_engine_outputs()
  attrs['surplus_freeze_until_ts'] muodostetaan rivien ~1277 ymparilla

ems_policy_engine.py
  _dispatch_command_attrs()
  dispatch_command_hash sisaltaa surplus_freeze_until_ts

ems_dispatch_state_applier.py
  ems_dispatch_state_applier_loop()
  lukee canonical dispatch_command attrsista surplus_freeze_until_ts
  _set_freeze_until_ts() ei kirjoita, jos arvo on None / '' / unknown / unavailable
```

Nykyinen attrs-muodostus kayttaa fallbackia:

```python
'surplus_freeze_until_ts': (
    combo_change_freeze_until_ts
    if combo_change_freeze_until_ts is not None
    else (
        surplus_device_decision.freeze_until_ts
        if surplus_device_decision.freeze_until_ts is not None
        else effective_freeze_until_ts
    )
)
```

Riski: kun policy on inactive ja dispatch on `CLEAR_ALL`, `effective_freeze_until_ts`
voi olla `now_ts` tai muuten nykyhetkeen sidottu arvo. Talla arvolla ei ole
canonical clear-komennossa semanttista merkitysta, mutta se vaihtaa hashia.

## Rajaus

Tee vain canonical stability -bugfix.

Ala muuta:

```text
- NET_ZERO-kaavoja
- device policy -arvoja
- writer-semantiiikkaa
- dispatch-applier trigger-sopimusta
- policy_engine interval- tai diagnostics_interval_seconds-logiikkaa
- canonical entity ID:ita
- E2E business -odotuksia
```

Ala toteuta isoa dispatch state machine -uudelleensuunnittelua.

Salli edelleen oikeat tulevaisuuden freeze-ajastukset real action -komennoille,
esimerkiksi `ACTIVATE`, `RELEASE`, force-rising-edge freeze ja
`HAEO_COMBO_CHANGED`.

## Vaihe 0: suojaa lahtotila

Tavoite: uusi sessio erottaa taman korjauksen aiemmasta timer-load-tyosta,
untracked-suunnitelmista ja Windows Zone.Identifier -sivutiedostoista.

Toimenpiteet:

1. Aja:

```bash
git status --short
```

2. Huomioi, etta repo voi sisaltaa ennestaan muun tehtavan muutoksia ja
   untracked-tiedostoja, esimerkiksi:

```text
docs/dev/codex_task_fix_dispatch_clear_all_canonical_stability.md
docs/dev/codex_task_fix_dispatch_clear_all_canonical_stability.md:Zone.Identifier
docs/dev/*:Zone.Identifier
ems_production_*.zip
```

3. Ala ota `*:Zone.Identifier`-tiedostoja tai tuotantozippeja mukaan
   toteutuscommittiin.

4. Aja baseline-kohdistukset ennen koodimuutoksia:

```bash
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_engine.py tests/unit/test_policy_engine_timer.py tests/unit/test_dispatch_state_applier.py
PYTHONPATH=modules python3 -m pytest -q tests/contract/test_grouped_config_runtime_parity.py
```

Hyvaksynta:

```text
Baseline-testit ovat vihreat tai tunnettu lahtotilan virhe kirjataan ennen muutoksia.
```

## Vaihe 1: todista bugi pienella testilla

Tavoite: lukitse nykyinen regressio ennen korjausta.

Suositellut testit:

```text
tests/unit/test_engine.py
  test_policy_inactive_clear_all_freeze_until_is_stable_across_now_ts

tests/unit/test_policy_engine_timer.py tai tests/contract/test_grouped_config_runtime_parity.py
  test_dispatch_command_hash_stable_for_repeated_clear_all_with_only_now_ts_change
```

Ensimmainen testi:

```text
Given:
  profiles.control = MANUAL tai muu policy inactive -tila
  goal = NET_ZERO
  equivalent runtime inputs
  now_ts = 100 ja now_ts = 105

When:
  compute_net_zero_engine_outputs() ajetaan molemmilla ajoilla

Then:
  surplus_device_dispatch_action == CLEAR_ALL
  surplus_device_dispatch_decision == CLEAR_ALL
  surplus_freeze_until_ts on None / stable neutral value molemmissa
  canonical dispatch command payload on sama
```

Toinen testi voidaan rakentaa suoraan `_dispatch_command_attrs()`-helperiin:

```python
attrs_100 = {
    'surplus_device_dispatch_action': 'CLEAR_ALL',
    'surplus_device_dispatch_decision': 'CLEAR_ALL',
    'surplus_device_dispatch_device_id': '',
    'surplus_device_dispatch_target': '',
    'surplus_device_targets': (),
    'surplus_freeze_until_ts': 100.0,
    'surplus_state_clear_reason': '',
}
attrs_105 = dict(attrs_100, surplus_freeze_until_ts=105.0)

assert _dispatch_command_attrs(attrs_100)['dispatch_command_hash'] == (
    _dispatch_command_attrs(attrs_105)['dispatch_command_hash']
)
assert _dispatch_command_attrs(attrs_100)['surplus_freeze_until_ts'] is None
```

Huomio: tama testi on tarkoituksella canonical normalization -suoja. Vaikka
engine korjataan, hash-helperin ei pidaisi paastaa CLEAR_ALL:n now-ts-arvoa
canonical hashiin.

## Vaihe 2: korjaa engine attrs -semantiikka

Tavoite: `compute_net_zero_engine_outputs()` ei nayta harhaanjohtavaa nykyhetken
freeze-arvoa `CLEAR_ALL` / inactive-policy -tilassa.

Lisa engineen pieni helper, esimerkiksi:

```python
def _canonical_surplus_freeze_until_ts_for_output(
    dispatch_action,
    dispatch_decision,
    combo_change_freeze_until_ts,
    decision_freeze_until_ts,
    effective_freeze_until_ts,
):
    if combo_change_freeze_until_ts is not None:
        return combo_change_freeze_until_ts
    action = str(dispatch_action or '')
    decision = str(dispatch_decision or '')
    if action == 'CLEAR_ALL' and decision == 'CLEAR_ALL':
        return None
    if action == 'NOOP':
        return effective_freeze_until_ts
    if decision_freeze_until_ts is not None:
        return decision_freeze_until_ts
    return effective_freeze_until_ts
```

Tarkennus:

```text
- CLEAR_ALL + HAEO_COMBO_CHANGED saa edelleen kayttaa combo_change_freeze_until_ts:aa,
  koska se on oikea tulevaisuuden freeze ja surplus_state_clear_reason kertoo miksi.
- policy inactive CLEAR_ALL ilman clear reasonia palauttaa None.
- NOOP saa edelleen kantaa olemassa olevaa stable freezea, jos se edustaa aktiivista
  freeze-ikkunaa aiemman oikean activation/release/force-tapahtuman jalkeen.
```

Korvaa attrs-rakennuksen nykyinen inline fallback helperilla.

Hyvaksynta:

```text
Stable inactive CLEAR_ALL ei sisalla now_ts-arvoa surplus_freeze_until_ts-attribuutissa.
Oikeat future freeze -polut eivat muutu.
```

## Vaihe 3: normalisoi canonical dispatch hash ja attrs varmistukseksi

Tavoite: vaikka joku tuleva path tuottaisi CLEAR_ALL:lle vaihtuvan
`surplus_freeze_until_ts`-arvon, canonical dispatch output pysyy stabiilina.

Muokattava tiedosto:

```text
ems_policy_engine.py
```

Lisaa helper lahelle `_dispatch_command_attrs()`:

```python
def _canonical_surplus_freeze_until_ts_for_dispatch(attrs):
    action = str(attrs.get('surplus_device_dispatch_action') or '')
    decision = str(attrs.get('surplus_device_dispatch_decision') or '')
    clear_reason = str(attrs.get('surplus_state_clear_reason') or '')
    freeze_until_ts = attrs.get('surplus_freeze_until_ts')

    if action == 'CLEAR_ALL' and decision == 'CLEAR_ALL' and clear_reason != 'HAEO_COMBO_CHANGED':
        return None
    return freeze_until_ts
```

Kayta normalisoitua arvoa seka hash-inputissa etta palautettavassa
`dispatch_command_attrs` payloadissa:

```python
freeze_until_ts = _canonical_surplus_freeze_until_ts_for_dispatch(attrs)

command_hash = _payload_hash({
    ...
    'surplus_freeze_until_ts': freeze_until_ts,
    ...
})

return {
    ...
    'surplus_freeze_until_ts': freeze_until_ts,
    ...
}
```

Perustelu:

```text
dispatch_command on canonical command/state pinta. CLEAR_ALL ilman real freeze
reasonia ei saa sisaltaa kellonaikaan sidottua arvoa.
```

Varo:

```text
Ala normalisoi ACTIVATE/RELEASE freeze-arvoja pois.
Ala normalisoi HAEO_COMBO_CHANGED CLEAR_ALL -future freezea pois, ellei testit
osoita, etta sekin kuuluu erottaa erilliseksi non-canonical kentaksi.
```

## Vaihe 4: lukitse diagnostiikan throttlausregressio

Tavoite: todista, etta stable CLEAR_ALL ei enaa pakota diagnostics-julkaisua
5 sekunnin valein.

Lisa tai laajenna testi:

```text
tests/unit/test_policy_engine_timer.py
  test_policy_diagnostics_throttled_for_repeated_policy_inactive_clear_all
```

Testimalli voi kayttaa jo olemassa olevia `run_policy_loop`-stubeja.

Scenario:

```text
1. Ensimmainen timer run t=100:
   dispatch action CLEAR_ALL
   surplus_freeze_until_ts=100.0 ennen normalisointia
   diagnostics julkaistaan startup/canonical_changed-syysta

2. Toinen timer run t=105:
   sama semantic dispatch CLEAR_ALL
   surplus_freeze_until_ts=105.0 ennen normalisointia

Expected:
   dispatch_command_hash sama molemmilla ajoilla
   policy_diagnostics ei julkaistu toisella ajolla
   last_diagnostics_publish_ts jai arvoon 100.0
```

Jos testi ei helposti pysty ajamaan koko loopia, lukitse minimi:

```text
_dispatch_command_attrs(CLEAR_ALL ts=100).dispatch_command_hash ==
_dispatch_command_attrs(CLEAR_ALL ts=105).dispatch_command_hash

_should_publish_policy_diagnostics(
    now_ts=105,
    trigger_reason='timer',
    diagnostics_interval_seconds=30,
    canonical_changed=False,
    warning_state_changed=False,
) == (False, 'throttled')
```

## Vaihe 5: suojaa real freeze -polut

Tavoite: estaa ylikorjaus, joka poistaisi oikeat freeze timestampit.

Vahvista olemassa olevat testit tai lisaa tarvittaessa:

```text
tests/unit/test_engine.py
  test_engine_force_rising_edge_sets_freeze_and_blocks_immediate_activation
  test_engine_force_without_rising_edge_allows_activation_without_new_freeze

tests/e2e_entity/net_zero_priority_order_quarter*/...
  ACTIVATE-polut, joissa surplus_freeze_until_ts == now_ts + freeze_s

tests/e2e_entity/haeo_02_net_zero_homebattery_primary_ev_adjustable/...
  HAEO_COMBO_CHANGED CLEAR_ALL saa edelleen future freeze -arvon, jos nykyinen
  business-odotus niin vaatii
```

Lisa eksplisiittinen unit-testi hash-helperille:

```text
test_dispatch_command_hash_keeps_activate_freeze_until_ts
```

Scenario:

```text
ACTIVATE_ADJUSTABLE ts=130 ja ACTIVATE_ADJUSTABLE ts=135 tuottavat eri
dispatch_command_hashit, koska real future freeze on osa semanttista commandia.
```

## Vaihe 6: dokumentoi pieni sopimustarkennus

Paivita vain tarvittaessa:

```text
docs/dev/arkkitehtuuri.md
docs/user/operointi.md
tests/e2e_entity/e2e_conventions.md
```

Suositeltu teksti:

```text
CLEAR_ALL ilman erillista future-freeze syyta on idempotentti canonical command:
se ei kanna now_ts-pohjaista surplus_freeze_until_ts-arvoa eika vaihda
dispatch_command_hashia pelkan kellonajan takia.
ACTIVATE/RELEASE ja dokumentoidut future-freeze -polut voivat edelleen kantaa
freeze timestampia.
```

Pidä dokumentointi lyhyena, koska kyse on bugikorjauksesta.

## Vaihe 7: regressiot ja grep-tarkistukset

Aja kohdistetut testit:

```bash
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_engine.py
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_policy_engine_timer.py
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_dispatch_state_applier.py
PYTHONPATH=modules python3 -m pytest -q tests/contract/test_grouped_config_runtime_parity.py
```

Aja E2E:

```bash
PYTHONPATH=modules python3 -m pytest -q tests/e2e_entity
```

Aja koko suite, jos kohdistetut ovat vihreat:

```bash
PYTHONPATH=modules python3 -m pytest -q
```

Grep-tarkistukset:

```bash
rg "freeze_until_ts=.*now|now_ts.*freeze|CLEAR_ALL|policy_active" modules ems_*.py tests
rg "dispatch_command_hash|surplus_freeze_until_ts" modules ems_*.py tests
```

Hyvaksynta:

```text
- CLEAR_ALL / policy inactive ei aseta canonical surplus_freeze_until_ts:aa now_ts-arvoon.
- dispatch_command_hash on sama, kun vain now_ts muuttuu stable CLEAR_ALL -tilassa.
- policy_diagnostics ei julkaise joka 5s stable inactive CLEAR_ALL -tilassa.
- diagnostics julkaisee edelleen heti aidon canonical muutoksen yhteydessa.
- diagnostics julkaisee edelleen diagnostics_interval_seconds-cadencella ilman muutoksia.
- ACTIVATE/RELEASE ja real future-freeze -polut sailyvat.
```

## Tuotantovalidointi korjauksen jalkeen

Konfiguraatio:

```yaml
ems:
  policy_engine:
    interval_seconds: 5
    diagnostics_interval_seconds: 30
```

Vakaa manual-control / policy inactive -tila, seuraa ainakin 60 sekuntia:

```text
device_policies_hash pysyy samana.
surplus_device_dispatch_action == CLEAR_ALL.
surplus_device_dispatch_decision == CLEAR_ALL.
surplus_freeze_until_ts on None tai muuten stabiili, ei policy_engine_last_tick_ts.
dispatch_command_hash pysyy samana t=5..t=25 ajoissa.
policy_engine_diagnostics_publish_reason ei ole canonical_changed joka 5s.
policy_diagnostics paivittyy noin 30s valein reason=interval.
```

Jos `canonical_changed` jatkuu joka policy-ajolla, tarkista seuraavat kentat
perakkaisista sampleista:

```text
device_policies_hash
dispatch_command_hash
policy_state_hash
surplus_freeze_until_ts
surplus_state_clear_reason
surplus_device_targets
prev_force_on_device_ids
```

## Ei-tavoitteet

Tassa sessiossa ei tarvitse:

```text
- muuttaa recorder-ohjeita
- muuttaa policy_diagnostics throttlausalgoritmia
- julkaista canonical sensoreita vain hash-muutoksilla
- erotella koko policy_attrs / diagnostics_attrs -rakennetta uudelleen
- kasitella muita volatile canonical kenttia, ellei testit osoita samaa bugia
```
