# Reviewed phase plan: reduce policy engine timer load

Paivays: 2026-07-02

Lahdedokumentti: `docs/dev/codex_task_reduce_policy_engine_timer_load_v2.md`

## Arvio suunnitelman toimivuudesta

Suunnitelman paalinja on toimiva ja vastaa havaintoa tuotantokuormasta:

1. Policy-paatokset kannattaa pitaa responsiivisina `interval_seconds=5`-tasolla.
2. Suuri `policy_diagnostics`-attribuuttipayload kannattaa julkaista harvemmin, ellei canonical-output, warning/error/input-quality tai manuaalinen ajo vaadi valitonta nakyvyytta.
3. Kiintean 2s schedulerin skip-polun tulee olla halpa. Nykyinen toteutus lukee config/runtime-contextin ennen skip-paatosta, joten skip ei viela ole aidosti kevyt.
4. E2E-polku tulee pitaa deterministisena pakottamalla diagnostiikan julkaisu `trigger_reason='e2e'` -ajoissa.

Nykytila tukee tata muutosta hyvin:

1. `CorePolicyEngineConfig.interval_seconds` on jo olemassa.
2. `ems.policy_engine.interval_seconds` validoidaan numeric constantina, default on 5 ja minimi 2.
3. `ems_policy_engine.py` kayttaa jo `@time_trigger('period(now, 2s)')` -mallia.
4. `ems_policy_engine_loop(trigger_reason='e2e')` on jo olemassa ja E2E harness kutsuu sita.
5. Canonical hashit on jo rajattu erillisiin helper-funktioihin niin, etta timer-diagnostiikka ei vaikuta ainakaan `device_policies_hash`iin.

Suunnitelmassa on kuitenkin muutama kohta, jotka kannattaa rajata tai tarkentaa:

1. "Publish canonical sensor only when hash changes" on isompi sopimusmuutos kuin pelkka diagnostiikan throttlaus. Writer/dispatch-triggerien semantiikka on hash-state-pohjainen, mutta sensorin attribuuttien muutoksen estaminen vaatii nykyisen publish-rakenteen tarkkaa auditointia. Tama kannattaa toteuttaa vaiheessa 4 vasta kun diagnostiikan throttlaus on lukittu.
2. `device_policies`-sensorille julkaistaan nykyisin sama laaja `attrs` kuin diagnostiikkaan. Jos siihen lisataan timing- ja publish-diagnostiikkaa ennen payloadien erottelua, canonical-sensorin attribuuttikuorma voi kasvaa. Ensimmainen toteutus ei saa pahentaa tata: uudet timing/publish-kentat lisataan vain `policy_diagnostics`-payloadiin tai erilliseen diagnostics-only attrs-kopioon.
3. Fast skip path tarvitsee cached interval -tilan. Koska skip-polku ei saa lukea configia, config-muutoksen soveltuminen voi viivastya seuraavaan oikeaan runiin. Tama on hyvaksyttava ja dokumentoitava tradeoff.
4. Warning/error/input-quality-signature kannattaa toteuttaa pienena ja vakaana. Ei timestamppeja, laskureita tai run-duration-arvoja signatureen.
5. Laajat phase timing -mittarit ovat hyodyllisia, mutta ensimmainen turvallinen minimi on `policy_engine_run_duration_ms` ja `policy_engine_publish_ms`.

Katselmointipalautteen jalkeen pakolliset tarkennukset ennen toteutusta:

1. Config-loaderin taytyy hylata virheellinen `diagnostics_interval_seconds`. Virheellista YAML-arvoa ei saa hiljaa defaultata 30 sekuntiin.
2. Runtime-helper saa olla defensiivinen vain jo validoidulle `CoreConfig`-oliolle tai testistubeille.
3. Warning/error/input-quality signature ei saa sisaltaa tavallisia, usein muuttuvia policy-selityskenttia.
4. Timing- ja publish-decision-kentat ovat diagnostics-only. Niita ei lisata canonical sensorien attrseihin eika canonical hashien inputteihin.
5. Previous hash/signature -tila paivitetaan vasta, kun run on paassyt publish-decision-vaiheeseen onnistuneesti.
6. Writer/dispatch trigger -sopimusta ja E2E business -odotusarvoja ei muuteta tassa tehtavassa.

## Tavoitetila

Konfiguraatio:

```yaml
ems:
  policy_engine:
    interval_seconds: 5
    diagnostics_interval_seconds: 30
```

Runtime-saanto:

```text
Timer-run:
  aja policy laskenta interval_seconds-cadencella
  julkaise canonical outputit normaalisti
  julkaise policy_diagnostics vain jos:
    - canonical output muuttui
    - warning/error/input-quality signature muuttui
    - diagnostics_interval_seconds on kulunut
    - kyseessa on ensimmainen onnistunut run

Manual/e2e-run:
  aja policy laskenta heti
  julkaise policy_diagnostics aina
```

Fast skip -saanto:

```text
2s tick, interval ei kulunut:
  time.time()
  paivita in-memory ticks/skips
  return

Ei config/runtime-context lukua.
Ei entity-lukua.
Ei hashia.
Ei publish_sensor-kutsua.
Ei policy-computea.
```

## Vaihe 0: suojaa nykytila

Tavoite: varmista, etta seuraava sessio erottaa lahdedokumentit, nykyiset untracked-tiedostot ja varsinaisen toteutusmuutoksen.

Toimenpiteet:

1. Aja `git status --short`.
2. Huomioi, etta ainakin seuraavat voivat olla untracked tai poistettuja sivutiedostoja:

```text
docs/dev/codex_task_reduce_policy_engine_timer_load_v2.md
docs/dev/codex_task_reduce_policy_engine_timer_load_v2.md:Zone.Identifier
docs/dev/*:Zone.Identifier
```

3. Ala ota `*:Zone.Identifier` -tiedostoja mukaan toteutuscommittiin.
4. Ennen koodimuutoksia aja nykyiset kohdistetut testit:

```bash
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_config_loader.py tests/unit/test_policy_engine_timer.py
```

Hyvaksynta:

```text
Nykyiset timer/config-testit joko menevat lapi tai tunnettu lahtotilan virhe kirjataan ennen muutoksia.
```

## Vaihe 1: config-malli ja validointi

Tavoite: lisaa `diagnostics_interval_seconds` samaan `ems.policy_engine` -sopimukseen kuin nykyinen `interval_seconds`.

Muokattavat tiedostot:

```text
modules/ems_core/domain/models.py
modules/ems_adapter/config_loader.py
tests/unit/test_config_loader.py
example_EMS_config.yaml
EMS_config.yaml jos projektissa kaytossa
tests/e2e_entity/**/EMS_config.yaml vain jos repo linjaa, etta kaikki fixturet nayttavat uuden kentan eksplisiittisesti
```

Toteutus:

1. Laajenna dataclass:

```python
@dataclass
class CorePolicyEngineConfig:
    interval_seconds: float = 5.0
    diagnostics_interval_seconds: float = 30.0
```

2. Laajenna `ALLOWED_POLICY_ENGINE_KEYS`:

```python
ALLOWED_POLICY_ENGINE_KEYS = frozenset(('interval_seconds', 'diagnostics_interval_seconds'))
```

3. Lisaa dedicated parser:

```python
def _parse_policy_engine_diagnostics_interval_seconds(raw_value):
    if raw_value is None:
        return 30.0
    if isinstance(raw_value, bool):
        raise ValueError('policy_engine.diagnostics_interval_seconds must be a numeric config constant')
    if not isinstance(raw_value, (int, float)):
        raise ValueError('policy_engine.diagnostics_interval_seconds must be a numeric config constant')
    interval_seconds = float(raw_value)
    if interval_seconds < 5.0:
        raise ValueError('policy_engine.diagnostics_interval_seconds must be >= 5 seconds')
    return interval_seconds
```

4. Kayta parseria seka validoinnissa etta `CoreConfig`-rakennuksessa.
5. Ala kayta `_resolve_core_config_value` -polkua tahan kenttaan.
6. Ala kasittele virheellista YAML-arvoa puuttuvana arvona. Vain puuttuva kentta saa defaultata 30 sekuntiin.

Testit:

```text
test_policy_engine_diagnostics_interval_defaults_to_30
test_policy_engine_diagnostics_interval_accepts_30
test_policy_engine_diagnostics_interval_accepts_minimum_5
test_policy_engine_diagnostics_interval_rejects_2
test_policy_engine_diagnostics_interval_rejects_0
test_policy_engine_diagnostics_interval_rejects_negative
test_policy_engine_diagnostics_interval_rejects_non_numeric
test_policy_engine_diagnostics_interval_rejects_bool
test_policy_engine_diagnostics_interval_rejects_entity_ref
test_diagnostics_interval_invalid_yaml_does_not_default_silently
test_policy_engine_interval_rejects_unknown_field paivitetty uudelle allowed-key-listalle
```

Hyvaksynta:

```bash
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_config_loader.py tests/unit/test_core_config.py
```

## Vaihe 2: nopea timer skip -polku

Tavoite: 2s schedulerin skip ei tee kallista tyota.

Muokattava tiedosto:

```text
ems_policy_engine.py
tests/unit/test_policy_engine_timer.py
```

Toteutus:

1. Laajenna timer state:

```python
_POLICY_ENGINE_TIMER_STATE = {
    'last_run_ts': None,
    'last_diagnostics_publish_ts': None,
    'effective_interval_seconds': 5.0,
    'effective_diagnostics_interval_seconds': 30.0,
    'scheduler_tick_seconds': 2.0,
    'ticks_seen': 0,
    'runs_seen': 0,
    'skipped_ticks': 0,
}
```

2. Lisaa cached gate -helper:

```python
def _policy_engine_interval_elapsed_fast(now_ts):
    interval_seconds = float(_POLICY_ENGINE_TIMER_STATE.get('effective_interval_seconds', 5.0) or 5.0)
    return _policy_engine_interval_elapsed(now_ts, interval_seconds)
```

3. Muuta `ems_policy_engine_tick()` jarjestys:

```python
@time_trigger('period(now, 2s)')
def ems_policy_engine_tick():
    import time
    now_ts = time.time()
    _note_policy_tick(now_ts)
    if not _policy_engine_interval_elapsed_fast(now_ts):
        _note_policy_skip()
        return

    cfg, entities = read_runtime_context(get_bool, get_float, get_int, get_str)
    _POLICY_ENGINE_TIMER_STATE['effective_interval_seconds'] = _policy_engine_interval_seconds(cfg)
    _POLICY_ENGINE_TIMER_STATE['effective_diagnostics_interval_seconds'] = _policy_engine_diagnostics_interval_seconds(cfg)

    if not _policy_engine_interval_elapsed(now_ts, _POLICY_ENGINE_TIMER_STATE['effective_interval_seconds']):
        _note_policy_skip()
        return

    _note_policy_run(now_ts)
    run_policy_loop(now_ts, cfg, entities, 'timer')
```

Toinen gate config-luvun jalkeen on tarkoituksellinen: se kasittelee tilanteen, jossa cached interval on vanhentunut config reloadin jalkeen.

4. `ems_policy_engine_loop(trigger_reason='manual'|'e2e')` saa edelleen ohittaa gaten ja lukea configin heti.
5. Kun manual/e2e lukee configin, paivita cached intervalit samalla.

Testit:

```text
test_policy_engine_fast_skip_uses_cached_interval
test_policy_engine_tick_skip_does_not_read_runtime_context
test_policy_engine_tick_skip_does_not_publish_sensor
test_policy_engine_tick_skip_does_not_call_hash_helpers
test_policy_engine_tick_skip_does_not_call_policy_compute
test_policy_engine_manual_run_updates_cached_intervals
```

Hyvaksynta:

```bash
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_policy_engine_timer.py
```

## Vaihe 3: diagnostiikan throttlaus

Tavoite: `policy_diagnostics` julkaistaan vain tarpeeseen timer-runeissa, mutta aina manual/e2e-runeissa.

Muokattava tiedosto:

```text
ems_policy_engine.py
tests/unit/test_policy_engine_timer.py
```

Toteutus:

1. Lisaa helper:

```python
def _policy_engine_diagnostics_interval_seconds(cfg):
    policy_engine_cfg = getattr(cfg, 'policy_engine', None)
    if policy_engine_cfg is None:
        return 30.0
    interval_seconds = getattr(policy_engine_cfg, 'diagnostics_interval_seconds', 30.0)
    if interval_seconds in (None, ''):
        return 30.0
    if isinstance(interval_seconds, bool):
        return 30.0
    return float(interval_seconds)
```

Tama helper on defensiivinen runtime/testi-helper. Se ei korvaa config-loaderin tiukkaa validointia. Raw YAML -arvoille patee vaihe 1: boolit, stringit, entity-refit, nolla, negatiiviset ja alle 5 sekunnin arvot hylataan validoinnissa.

2. Lisaa pure publish-decision-helper:

```python
def _should_publish_policy_diagnostics(now_ts, trigger_reason, diagnostics_interval_seconds, canonical_changed, warning_state_changed):
    reason = str(trigger_reason or '')
    if reason == 'e2e':
        return True, 'e2e'
    if reason == 'manual':
        return True, 'manual'
    if _POLICY_ENGINE_TIMER_STATE.get('last_diagnostics_publish_ts') is None:
        return True, 'startup'
    if canonical_changed:
        return True, 'canonical_changed'
    if warning_state_changed:
        return True, 'warning_changed'
    last_ts = float(_POLICY_ENGINE_TIMER_STATE.get('last_diagnostics_publish_ts') or 0.0)
    if now_ts - last_ts >= float(diagnostics_interval_seconds):
        return True, 'interval'
    return False, 'throttled'
```

3. Lisaa warning/error/input-quality signature mahdollisimman pienenä:

```python
def _policy_warning_signature(attrs):
    return _payload_hash({
        'net_zero_input_quality': attrs.get('net_zero_input_quality', ''),
        'net_zero_input_warnings': attrs.get('net_zero_input_warnings', ()),
        'config_status': attrs.get('config_status', ''),
        'runtime_error': attrs.get('runtime_error', ''),
    })
```

Tarkista todelliset avainnimit `net_zero_attrs()`-payloadista ennen lukitsemista. Sisallyta `config_status` ja `runtime_error` vain jos ne ovat oikeasti olemassa ja vakaita. Jos vakaita warning/error/input-quality-avaimia ei loydy, ensimmainen hyvaksyttava toteutus on `warning_state_changed = False` ja TODO jatkotehtavaan.

Ala sisallyta ensimmaisessa toteutuksessa:

```text
dominant_limitation
normal policy reason -kentat
normal explanation -kentat
guard/profile -selityskentat, ellei niita todisteta warning/error-stateksi
timer counters
timestamps
run duration -arvot
publish decision -booleans
```

4. Laske canonical_changed nykyisten hashien perusteella:

```text
device_policies_hash != previous_device_policies_hash
dispatch_command_hash != previous_dispatch_command_hash
policy_state_hash != previous_policy_state_hash
```

Kayta in-memory `_POLICY_ENGINE_TIMER_STATE` -edellisarvoja, ei HA state -lukua. Tama pitaa throttlauspaatosen halvempana ja valttaa stale-read-ikkunaa.

5. Tee publish-decision vanhan in-memory hash/signature -tilan perusteella.
6. Yrita sensorijulkaisut.
7. Paivita edelliset canonical hashit ja warning signature vasta, kun run on paassyt publish-decision-vaiheeseen onnistuneesti.
8. Paivita `last_diagnostics_publish_ts` vain kun `policy_diagnostics` oikeasti julkaistaan.
9. `policy_engine_published_*`-booleans kuvaavat todellisia publish-yrityksia/tuloksia, eivat pelkkaa aiottua tilaa.
10. `trigger_reason='e2e'` ja `trigger_reason='manual'` julkaisevat diagnostiikan aina.

Testit:

```text
trigger_reason=e2e -> publish, reason=e2e
trigger_reason=manual -> publish, reason=manual
first timer run -> publish, reason=startup
timer before diagnostics interval without changes -> no publish, reason=throttled
timer after diagnostics interval without changes -> publish, reason=interval
canonical_changed=True before interval -> publish, reason=canonical_changed
warning_state_changed=True before interval -> publish, reason=warning_changed
canonical_changed=True and interval elapsed -> reason=canonical_changed
warning_state_changed=True and interval elapsed -> reason=warning_changed
warning signature does not include volatile fields or ordinary policy explanation fields
```

Hyvaksynta:

```bash
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_policy_engine_timer.py
```

## Vaihe 4: publish payload -rajat ja timing-diagnostiikka

Tavoite: mittaa kuormaa ilman, etta canonical hashit tai canonical sensorien attrsit muuttuvat tarpeettomasti.

Toteutusjarjestys:

1. Erottele `policy_attrs` ja `diagnostics_attrs`:

```text
policy_attrs:
  canonical writer/dispatch/state payloadiin tarvittavat kentat

diagnostics_attrs:
  policy_attrs + selitykset + timing + publish decision -kentat
```

2. Jos taysi erottelu on liian iso, tee pienempi turvallinen muutos:

```text
attrs pysyy nykyisena canonical-publisheille
diagnostics_attrs = dict(attrs)
diagnostics_attrs.update(timing/publish-only fields)
policy_diagnostics julkaistaan diagnostics_attrsilla
canonical sensoreille ei lisata uusia volatile timing/publish-only kenttia
```

3. Lisaa minimimittarit:

```text
policy_engine_run_duration_ms
policy_engine_publish_ms
```

4. Lisaa publish-decision-kentat vain diagnostiikkaan:

```text
policy_engine_published_device_policies
policy_engine_published_dispatch_command
policy_engine_published_policy_state
policy_engine_published_policy_diagnostics
policy_engine_diagnostics_publish_reason
policy_engine_last_diagnostics_publish_ts
policy_engine_diagnostics_interval_seconds
```

5. Ala sisallyta timing/publish-decision-kenttia mihinkaan canonical hash inputtiin.
6. Canonical sensorien "publish only on hash change" voidaan tehda tassa vaiheessa vain jos testit osoittavat, ettei writer/dispatch-regressiota synny. Muuten kirjaa se jatkotehtavaksi.

Suositeltu rajaus ensimmaiseen toteutukseen:

```text
Throttlaa vain policy_diagnostics.
Jata canonical publish cadence ennalleen, ellei erillinen testi/auditointi kata writer/dispatch-triggerit.
Ala kasvata canonical sensorien attrs-payloadia uusilla volatile kentilla.
```

Testit:

```text
diagnostics-only timing fields do not change device_policies_hash
diagnostics-only timing fields do not change dispatch_command_hash
diagnostics-only timing fields do not change policy_state_hash
throttled diagnostics does not prevent canonical publish
canonical_changed forces diagnostics publish before diagnostics interval
timing fields are diagnostics-only
canonical sensors are not enlarged with new volatile timing/publish attrs
```

Hyvaksynta:

```bash
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_policy_engine_timer.py
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_engine.py tests/unit/test_writer_semantics.py
```

## Vaihe 5: dokumentaatio

Tavoite: paivita kayttaja- ja kehittajadokumentit vastaamaan uutta ajomallia.

Muokattavat tiedostot:

```text
README.md
docs/dev/arkkitehtuuri.md
docs/dev/ems_step_model.md
docs/dev/testausautomaatio.md
tests/e2e_entity/e2e_conventions.md
docs/user/config_examples.md
docs/user/operointi.md jos recorder-ohje kuuluu kayttoohjeeseen
```

Sisalto:

```text
Policy engine computes on policy_engine.interval_seconds.
Policy diagnostics publish immediately on canonical output change or warning/error/input-quality change.
Otherwise timer-run diagnostics publish at most once per policy_engine.diagnostics_interval_seconds.
Manual and E2E runs force diagnostics publication.
The 2s scheduler skip path intentionally does not read config/runtime context.
Config interval changes may apply on next real policy run or manual/reload.
```

Recorder-suositus:

```yaml
recorder:
  exclude:
    entities:
      - sensor.ems_policy_diagnostics_pyscript
```

Muotoile suositus operatiivisena kuormanvähennyksenä, ei correctness-vaatimuksena.

## Vaihe 6: regressiot ja grep-tarkistukset

Aja kohdistetut testit:

```bash
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_config_loader.py
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_core_config.py
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_policy_engine_timer.py
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_engine.py tests/unit/test_writer_semantics.py
PYTHONPATH=modules python3 -m pytest -q tests/e2e_entity
```

Aja koko suite, jos aika sallii:

```bash
PYTHONPATH=modules python3 -m pytest -q
```

Grep-tarkistukset:

```bash
rg "diagnostics_interval_seconds|policy_engine_run_duration_ms|policy_engine_publish_ms" EMS_config.yaml example_EMS_config.yaml docs tests modules ems_*.py
rg "last_tick_ts|ticks_seen|skipped_ticks|run_duration_ms|publish_ms" ems_*.py modules tests
rg "sensor\.ems_policy_diagnostics_pyscript" README.md docs
```

Odotus:

```text
diagnostics_interval_seconds loytyy configista, docseista ja testeista.
timing/publish-only kentat ovat diagnostiikkaa tai testeja, eivat canonical hash inputteja.
recorder exclude -suositus loytyy aktiivisista docseista.
```

## Lopulliset acceptance criteria

Functional:

```text
ems.policy_engine.diagnostics_interval_seconds on olemassa.
Default diagnostics interval on 30 sekuntia.
Minimum diagnostics interval on 5 sekuntia.
Invalid diagnostics interval -arvot failaavat validoinnissa.
Timer skip path ei lue config/runtime-contextia eika julkaise sensoreita.
Timer real run laskee policyn normaalisti.
Timer-run diagnostics throttlautuu muuttumattomassa tilassa.
Canonical-output muutos julkaisee diagnostiikan heti.
Warning/error/input-quality muutos julkaisee diagnostiikan heti.
Manual/e2e julkaisee diagnostiikan aina.
E2E-odotusarvoja ei muuteta business-logiikan takia.
```

Performance/observability:

```text
policy_engine_run_duration_ms nakyy diagnostiikassa.
policy_engine_publish_ms tai vastaava minimi nakyy diagnostiikassa.
diagnostics publish reason nakyy diagnostiikassa.
published/not-published booleans nakyvat diagnostiikassa.
```

Safety:

```text
NET_ZERO-kaavoja ei muuteta.
Canonical output entity ID:t eivat muutu.
Writer/dispatch-triggerien sopimusta ei muuteta samassa vaiheessa ilman erillisia testejä.
Diagnostics-only kentat eivat vaikuta canonical hasheihin.
Recorder exclusion on suositus, ei toiminnallinen riippuvuus.
Invalid diagnostics_interval_seconds config values fail validation and do not silently default.
Warning/error/input-quality signature does not include volatile fields or ordinary policy explanation fields.
Timing and publish-decision fields are diagnostics-only.
Canonical sensors are not enlarged with new volatile timing/publish attrs.
Previous hash/signature state is updated only after the run reaches the publish-decision phase successfully.
No E2E business expected values changed.
```

## Seuraavan session suositeltu aloituskomento

```bash
git status --short
PYTHONPATH=modules python3 -m pytest -q tests/unit/test_config_loader.py tests/unit/test_policy_engine_timer.py
```

Jos testit ovat vihreat, aloita vaiheesta 1. Jos ne eivat ole vihreat, kirjaa lahtotilan virhe ennen toteutusmuutoksia.
