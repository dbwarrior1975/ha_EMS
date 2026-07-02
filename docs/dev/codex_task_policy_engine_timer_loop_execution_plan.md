# Policy engine timer loop execution plan

Paivays: 2026-07-02

## Tiivis arvio

Alkuperainen suunnitelma `docs/dev/codex_task_policy_engine_timer_loop.md` on
teknisesti perusteltu. Nykyinen `ems_policy_engine.py` lukee runtime entityt
grouped configin kautta, mutta Pyscript `@state_trigger` sitoo raw-inputit
edelleen kovakoodattuihin HA entityihin:

```text
sensor.average_active_power_2
sensor.hourly_energy_balance
sensor.pv_instant_power_2
```

Tama tekee `ems.runtime.*`-konfiguraatiosta osittain harhaanjohtavan: entity ID
on dynaaminen lukupolussa, mutta ei triggeripolussa.

Suositeltu toteutus on alkuperaisen suunnitelman "fixed 2s decorator +
internal skip gate". Pyscript-dekoraattorit rekisteroidaan load-timessa, joten
konfiguraatiosta rakennettu dynaaminen `@time_trigger(...)` on herkka
startup/reload-semanttiikalle. Kiintea 2 sekunnin tick ja configista luettava
sisainen gate on yksinkertaisempi, testattavampi ja tukee config reloadia.

## Paasuositus

Toteuta policy engine nain:

```text
@time_trigger('period(now, 2s)')
    -> ems_policy_engine_tick()
        -> read_runtime_context()
        -> lue cfg.policy_engine.interval_seconds
        -> jos interval ei ole kulunut: julkaise skip-diagnostiikka kevyesti tai palaa
        -> jos interval ei ole kulunut: palaa ilman canonical output -julkaisuja
        -> aja run_policy_loop(now_ts, cfg, entities, trigger_reason='timer')
```

`ems.policy_engine.interval_seconds` on minimi elapsed interval, joka
tarkistetaan kiintean 2s scheduler tickin yhteydessa. Se ei ole lupaus
tasmalleen 5.000 sekunnin cadenceista. Esimerkiksi intervalilla 5s ja
tickeilla `0, 2, 4, 6, ...` ajot voivat tapahtua kohdissa `0, 6, 12, ...`.

Pidä E2E-polku deterministisena erottamalla varsinainen policy-ajon runko
timer-gatesta:

```text
run_policy_loop(now_ts, trigger_reason='manual/e2e/timer')
```

Nykyinen E2E harness kutsuu `ems_policy_engine_loop()` suoraan. Muutoksen
jalkeen harness kannattaa paivittaa kutsumaan joko:

1. `run_policy_loop_for_test()` / `ems_policy_engine_loop()` joka ohittaa gaten
2. tai `ems_policy_engine_loop(trigger_reason='e2e')`, jos funktio pidetaan
   yhteensopivana wrapperina

Tarkeinta on, ettei E2E ala odottaa oikeaa seinakellotimeria.

## Tarkeat reunaehdot

1. `policy_engine` kuuluu nykyisen YAML-rakenteen sisaan `ems:`-osion alle:

   ```yaml
   ems:
     policy_engine:
       interval_seconds: 5
   ```

   Alkuperainen dokumentti sanoo "top-level grouped config section", mutta
   taman repon config-loader validoi `ems`-osion sisaisia top-level sectioneita.
   Jos `policy_engine` lisattaisiin YAML-rootiin, nykyinen loader ei kasittelisi
   sita luontevasti.

2. Minimum interval on 2 sekuntia, koska decorator tick on 2s. Jos config
   sallisi alle 2s, decorator olisi hitaampi kuin luvattu interval.

3. Profile-muutosten immediate `@state_trigger` kannattaa poistaa samassa
   muutoksessa, ellei loydy vahvaa syyta sailyttaa niita. Puhtain malli on:

   ```text
   policy engine samples all inputs on timer
   writer/dispatch react to canonical hash sensors
   ```

4. Canonical output triggerit eivat kuulu tahan tehtavaan:

   ```text
   sensor.ems_device_policies_pyscript
   sensor.ems_surplus_dispatch_command_pyscript
   sensor.ems_policy_state_pyscript
   ```

5. Diagnostiikan tick-countereita ei saa sisallyttaa canonical
   `device_policies`- tai `dispatch_command`-hashien inputteihin.

6. Ensimmainen startup-tick saa ajaa heti, mutta se ei saa julkaista
   aggressiivisia actuator-komentoja puutteellisista runtime-inputeista. Jos
   required inputit ovat `unknown`, `unavailable`, `none` tai muuten
   kelvottomia, toteutuksen pitaa kayttaa olemassa olevaa safe-mode /
   input-quality -polkua, julkaista vain turvallinen NOOP/diagnostiikka tai
   jattaa command-julkaisu tekematta.

## Vaihe 0: siisteys ennen toteutusta

Tarkista worktree:

```bash
git status --short
```

Huomioi erityisesti:

1. `docs/dev/codex_task_policy_engine_timer_loop.md:Zone.Identifier` on
   Windows/selainperainen sivutiedosto. Sita ei kannata ottaa mukaan
   versionhallintaan.
2. `ems_production_*.zip`-tyyppiset paketit eivat kuulu tahan muutokseen.
3. Jos edellisesta docs-tyosta on untracked plan/doc-tiedostoja, paata
   erikseen otetaanko ne samaan vai eri committiin.

## Vaihe 1: config-malli

Muokkaa `modules/ems_core/domain/models.py`.

Lisa uusi dataclass:

```python
@dataclass
class CorePolicyEngineConfig:
    interval_seconds: float = 5.0
```

Lisa `CoreConfig`iin yksi canonical kentta:

```python
policy_engine: CorePolicyEngineConfig
```

Jos nykyinen dataclass-rakenne vaatii optional-kentan Pyscript-yhteensopivuuden
takia, `__post_init__` tai `_populate_core_config_derived_fields()` saa
tayttaa oletuksen niin, etta:

```text
cfg.policy_engine.interval_seconds == 5
```

Vältä erillista `cfg.policy_engine_interval_seconds` mirroria. Lisaa sellainen
vain jos olemassa oleva tyyli tai testit aidosti vaativat sita. Jos mirror
lisataan, dokumentoi se derived/compatibility-mirroriksi ja testaa, etta se
pysyy samana kuin `cfg.policy_engine.interval_seconds`.

Pidä dataclass Pyscript-yhteensopivana. Ala kayta `field(default_factory=...)`
ellei nykyinen Pyscript smoke -testi sallisi sita.

## Vaihe 2: config-loader validointi

Muokkaa `modules/ems_adapter/config_loader.py`.

Lisa:

```python
OPTIONAL_TOP_LEVEL_SECTIONS = (
    'role_constraints',
    'haeo',
    'policy_engine',
)

ALLOWED_POLICY_ENGINE_KEYS = frozenset(('interval_seconds',))
```

Toteuta validointi:

```text
ems.policy_engine puuttuu -> ok, default 5
ems.policy_engine ei ole mapping -> error
ems.policy_engine.interval_seconds puuttuu -> ok, default 5
interval_seconds ei ole numeric constant -> error
interval_seconds < 2 -> error "policy_engine.interval_seconds must be >= 2 seconds"
unknown field -> error
```

Koska nykyinen loader tukee monia entity-ref arvoja muissa sectioneissa, tee
tasta kentasta tarkoituksella numeric config constant. Timer-intervalin ei
saa riippua HA entitysta, koska se maarittaa itse schedulerin
luotettavuussemantiikan.

Ala kayta `_resolve_core_config_value(..., read_entity, ...)` intervaliin.
Tama olisi vaarallinen, koska se sallisi kaytannossa HA-entityn ohjata
schedulerin cadencea.

Lisa config-loaderiin dedicated numeric parser, esimerkiksi:

```python
def _parse_policy_engine_interval_seconds(raw_value):
    if raw_value is None:
        return 5.0
    if isinstance(raw_value, bool):
        raise ValueError('policy_engine.interval_seconds must be numeric')
    if not isinstance(raw_value, (int, float)):
        raise ValueError('policy_engine.interval_seconds must be numeric')
    interval_seconds = float(raw_value)
    if interval_seconds < 2.0:
        raise ValueError('policy_engine.interval_seconds must be >= 2 seconds')
    return interval_seconds
```

Builderissa kayta parseria suoraan:

```python
policy_engine=CorePolicyEngineConfig(
    interval_seconds=_parse_policy_engine_interval_seconds(
        ems.get('policy_engine', {}).get('interval_seconds', 5.0)
    ),
)
```

Validoinnissa sama semantiikka pitaa palauttaa `ConfigValidationIssue`-virheina,
ei raakana `ValueError`ina.

## Vaihe 3: config-esimerkit

Paivita:

```text
EMS_config.yaml
example_EMS_config.yaml
tests/e2e_entity/**/EMS_config.yaml
docs/user/config_examples.md
mahdolliset docs/dev config-esimerkit
```

Lisa `ems:`-osion alle esimerkiksi heti `profiles`-osion jalkeen:

```yaml
  policy_engine:
    interval_seconds: 5
```

Tama on laaja mekaaninen YAML-muutos, mutta kayttaytyminen pysyy samana, koska
oletus on sama.

## Vaihe 4: policy engine -rakenne

Muokkaa `ems_policy_engine.py`.

Erottele nykyinen `ems_policy_engine_loop()` kahteen osaan:

```python
_POLICY_ENGINE_TIMER_STATE = {
    'last_run_ts': None,
    'ticks_seen': 0,
    'runs_seen': 0,
    'skipped_ticks': 0,
}

def _policy_engine_interval_seconds(cfg):
    ...

def _policy_engine_interval_elapsed(now_ts, interval_seconds):
    ...

def run_policy_loop(now_ts, cfg, entities, trigger_reason):
    ...

@time_trigger('period(now, 2s)')
def ems_policy_engine_tick():
    import time
    now_ts = time.time()
    cfg, entities = read_runtime_context(get_bool, get_float, get_int, get_str)
    interval_seconds = _policy_engine_interval_seconds(cfg)
    if not _policy_engine_interval_elapsed(now_ts, interval_seconds):
        return
    run_policy_loop(now_ts, cfg, entities, 'timer')

def ems_policy_engine_loop():
    import time
    now_ts = time.time()
    cfg, entities = read_runtime_context(get_bool, get_float, get_int, get_str)
    run_policy_loop(now_ts, cfg, entities, 'manual')
```

Pidä `ems_policy_engine_loop()` yhteensopivuuswrapperina E2E-harnessille ja
mahdollisille manuaalikutsuille. Pyscriptissa varsinainen timer-dekoroitu
funktio voi olla uusi `ems_policy_engine_tick()`.

Suositeltu wrapper-signature:

```python
def ems_policy_engine_loop(trigger_reason='manual'):
    import time
    now_ts = time.time()
    cfg, entities = read_runtime_context(get_bool, get_float, get_int, get_str)
    run_policy_loop(now_ts, cfg, entities, trigger_reason)
```

Paivita E2E harness kutsumaan:

```python
ems_policy_engine_loop(trigger_reason='e2e')
```

Tama tekee diagnostiikasta yksiselitteisen:

```text
timer  -> production timer run
manual -> explicit service/debug/manual call
e2e    -> deterministic scenario harness run
```

Poista policy engine -funktion `@state_trigger(...)` kokonaan, tai vahvista
erikseen testilla ettei se sisalla raw runtime entityja. Suositus: poista se
kokonaan ja anna policy engine -paatosten syntya vain timerilta/manual-kutsulta.

## Vaihe 5: gate-logiikan yksityiskohdat

Ensimmainen tick saa ajaa heti:

```text
last_run_ts is None -> run
```

Muut tickit:

```text
now_ts - last_run_ts >= interval_seconds -> run
muuten skip
```

Koska tick on kiintea 2s, todellinen run tapahtuu ensimmaisella scheduler
tickilla sen jalkeen kun configured interval on kulunut. Dokumentoi tama
minimum elapsed interval -semantiikkana, ei exact cadence -semantiikkana.

Kayta `time.time()` riittaa tassa Pyscript-ymparistossa, koska nykyinen
policy-loop ja E2E-harness jo fakeavat `time.time()`. `time.monotonic()` olisi
periaatteessa parempi elapsed timeen, mutta se vaikeuttaisi nykyista harnessia
ilman selvää hyotya.

Muista paivittaa `last_run_ts` vasta kun run todella tapahtuu.

## Vaihe 6: diagnostiikka

Lisa `attrs`-diagnostiikkaan ennen `publish_sensor(entities['policy_diagnostics'], ...)`:

```python
attrs.update({
    'policy_engine_trigger_mode': 'timer',
    'policy_engine_scheduler_tick_seconds': 2,
    'policy_engine_interval_seconds': interval_seconds,
    'policy_engine_last_tick_ts': now_ts,
    'policy_engine_last_run_reason': trigger_reason,
    'policy_engine_ticks_seen': _POLICY_ENGINE_TIMER_STATE.get('ticks_seen', 0),
    'policy_engine_runs_seen': _POLICY_ENGINE_TIMER_STATE.get('runs_seen', 0),
    'policy_engine_skipped_ticks': _POLICY_ENGINE_TIMER_STATE.get('skipped_ticks', 0),
})
```

Jos skip-tickeilla halutaan julkaista diagnostiikkaa, tee se vain
`policy_diagnostics`-sensorille. Ala julkaise `device_policies`- tai
`dispatch_command`-sensoreita skipissa.

Yksinkertaisin ensitoteutus: skip ei julkaise mitaan. Tällöin
`policy_engine_skipped_ticks` nakyy seuraavan onnistuneen runin diagnostiikassa.

`policy_engine_trigger_mode` voi olla `timer`, vaikka yksittaisen runin
`policy_engine_last_run_reason` olisi `manual` tai `e2e`; ensimmainen kertoo
production scheduling -mallin, jalkimmainen viimeisimman ajon syyn.

## Vaihe 7: hash-rajaus

Nykyinen `_device_policies_hash(attrs)` hashittaa vain `device_policies`.
Nykyinen `_dispatch_command_attrs(attrs)` hashittaa vain dispatch-kentat.

Sailyta tama rajaus. Ala lisa tick-countereita, timestamppeja tai
trigger-reasoneita hashien inputteihin.

Lisa tarvittaessa testi, joka todentaa ettei pelkka diagnostiikkakentta muuta
device policy -hashia.

## Vaihe 8: testit

### Config tests

Lisa `tests/unit/test_config_loader.py`:

```text
test_policy_engine_interval_defaults_to_5
test_policy_engine_interval_accepts_5
test_policy_engine_interval_accepts_minimum_2
test_policy_engine_interval_rejects_1
test_policy_engine_interval_rejects_0
test_policy_engine_interval_rejects_negative
test_policy_engine_interval_rejects_non_numeric
test_policy_engine_interval_rejects_unknown_field
test_policy_engine_interval_rejects_entity_ref
test_policy_engine_interval_rejects_bool
```

Jos numeric parser erotetaan omaksi helperiksi, testaa se suoraan:

```text
int accepted
float accepted
bool rejected
entity ref rejected
plain non-numeric string rejected
```

Lisa myos `tests/unit/test_core_config.py`iin mapping-testi, jos siella jo
varmistetaan top-level sectioneiden siirtyminen `CoreConfig`iin.

### Trigger/source tests

Lisaa uusi yksikkotesti esimerkiksi `tests/unit/test_policy_engine_timer.py`.

Tavoitteet:

```text
1. policy engineissa on @time_trigger('period(now, 2s)')
2. policy engineissa ei ole raw input @state_trigger -entityja:
   - sensor.average_active_power_2
   - sensor.hourly_energy_balance
   - sensor.pv_instant_power_2
3. policy engineissa ei ole state_triggeria input_select profileihin, jos
   valitaan puhdas timer-only malli
```

Jos toteutus jattaa jonkin profile `@state_trigger`in, dokumentoi miksi ja
rajaa testi vain raw-input-triggerien poistoon.

### Gate tests

Yksikkotestaa puhdas helper:

```text
interval=5:
  t=0 run
  t=2 skip
  t=4 skip
  t=6 run

interval=2:
  t=0 run
  t=2 run
  t=4 run

lisaksi:
  first tick runs when last_run_ts is None
  last_run_ts updates only on real run
  skipped_ticks increments only on skip
  runs_seen increments only on run
```

Pidä helper ilman Pyscript-riippuvuuksia, jotta testi on tavallinen unit test.

### E2E

Nykyiset E2E:t saavat jatkaa step-kohtaista deterministic runia. Paivita
`tests/e2e_entity/scenario_harness.py` kutsumaan
`ems_policy_engine_loop(trigger_reason='e2e')`, jos wrapper saa
`trigger_reason`-parametrin.

E2E-odotusarvoja ei pidä muuttaa scheduling-muutoksen takia.

### Startup safety test

Lisa tai paivita testi, joka simuloi ensimmaista timer-tickia tilanteessa,
jossa required runtime inputit ovat unavailable/missing.

Odotus:

```text
- unsafe actuator commandia ei julkaista
- diagnostiikka kertoo missing/unavailable runtime input -tilan
- jos nykyinen input-quality/safe-mode-polku jo tekee taman, testi lukitsee sen
```

### Hash boundary test

Lisa tai sailyta testi, joka todentaa:

```text
policy_engine_ticks_seen, policy_engine_last_tick_ts tai muut
timer-diagnostiikat eivat muuta device_policies_hashia tai
dispatch_command_hashia.
```

## Vaihe 9: dokumentaatio

Paivita ainakin:

```text
README.md
docs/dev/arkkitehtuuri.md
docs/dev/ems_step_model.md
docs/dev/testausautomaatio.md
tests/e2e_entity/e2e_conventions.md
```

Kirjaa lyhyesti:

```text
Production policy engine samples runtime inputs every
ems.policy_engine.interval_seconds seconds. Default 5, minimum 2.

Runtime entity IDs are config-driven read targets, not Pyscript
state-trigger targets.

The fixed scheduler tick is 2 seconds. interval_seconds is a minimum elapsed
interval checked on that scheduler tick; the actual run happens on the first
tick after the configured interval has elapsed.

E2E steps simulate one policy-engine sampling tick after applying step inputs.
```

Paivita vanhat docs-kohdat, jotka edelleen sanovat raw runtime entityjen olevan
state-trigger contract. Erityisesti:

```text
docs/dev/codex_task_derive_net_zero_inputs_inside_ems.md
docs/dev/codex_review_notes_derive_net_zero_inputs_phase_plan.md
```

Naita ei tarvitse poistaa, mutta jos ne jaavat aktiiviseen docs/dev-kansioon,
niihin kannattaa lisata "historical after timer-loop migration" -huomio tai
siirtaa archiveen erillisessa docs-siivouksessa.

## Vaihe 10: tarkistuskomennot

Aja vaiheittain:

```bash
python3 -m pytest -q tests/unit/test_config_loader.py
python3 -m pytest -q tests/unit/test_core_config.py
python3 -m pytest -q tests/unit/test_policy_engine_timer.py
python3 -m pytest -q tests/smoke/test_pyscript_ast_compat.py
python3 -m pytest -q tests/contract
python3 -m pytest -q tests/e2e_entity
python3 -m pytest -q
```

Grep-tarkistukset:

```bash
rg "average_active_power_2|hourly_energy_balance|pv_instant_power_2" ems_*.py modules tests docs
rg "policy_engine:|interval_seconds" EMS_config.yaml example_EMS_config.yaml docs tests
rg "state_trigger|time_trigger" ems_*.py
```

Hyvaksyttavat osumat:

```text
- raw runtime entity ID:t configeissa ja dokumenteissa
- docs-kohdat, jotka selittavat historiallista migraatiota
- writer ja dispatch canonical output triggerit
```

Epailyttavat osumat:

```text
- ems_policy_engine.py @state_trigger raw input entityille
- dokumentaatio, joka vaittaa runtime input entity ID:ta edelleen
  trigger-contractiksi nykytilassa
```

## Hyvaksymiskriteerit

1. `ems.policy_engine.interval_seconds` toimii ja default on 5.
2. Alle 2 sekunnin intervalit hylataan validoinnissa.
3. Policy engine ei triggeroidy raw runtime input entityjen state-muutoksista.
4. Policy engine lukee runtime entity ID:t grouped configista jokaisella
   varsinaisella runilla.
5. `ems_policy_engine_tick()` kay 2s fixed Pyscript timerilla, mutta varsinainen
   policy ajo tapahtuu configured intervalin mukaan.
6. E2E-skenaariot ajavat edelleen deterministisesti ilman oikeaa timeria.
7. Canonical writer/dispatch triggerit sailyvat ennallaan.
8. Diagnostiikka kertoo timer-moodin, scheduler tickin, intervalin ja viimeisen
   run reasonin.
9. Tick-counterit ja timestampit eivat vaikuta canonical output hasheihin.
10. Ensimmainen startup-tick puutteellisilla inputeilla ei julkaise unsafe
    actuator-komentoja.
11. Full pytest menee lapi.

## Riskit ja mitigoinnit

### Startup latency

Timer-only-malli tarkoittaa, etta profile-muutos ei valttamatta aja policya
heti. Oletusintervalilla pahin viive on noin 5s. Tama on hyvaksyttava tradeoff,
jos tavoite on yhtenainen sampling-malli.

### Config reload

Koska `read_runtime_context()` cachaa configin file-signaturen perusteella,
interval muuttuu seuraavalla tickilla kun tiedoston mtime/size muuttuu. Fixed
2s decorator tukee tata ilman Pyscript reloadia.

### Pyscript AST

Pidä uusi helper-koodi yksinkertaisena. Valta generator/list/dict
comprehensioneita runtime-polussa, koska smoke-testit rajaavat Pyscript AST
-subsetia.

### Skip-diagnostiikka

Jos skipissa ei julkaista mitaan, kayttaja ei nae skippeja ennen seuraavaa
varsinaista runia. Tämä on hyväksyttävä ensitoteutus. Reaaliaikainen
skip-diagnostiikka voidaan lisata myohemmin vain `policy_diagnostics`-pintaan.

## Ei tavoitteita

Tassa tehtavassa ei pidä:

1. muuttaa NET_ZERO-laskentakaavoja
2. muuttaa device-policy-, dispatch- tai writer-odotusarvoja
3. tehda writer trigger entityista dynaamisia
4. poistaa canonical hash-state sensoreita
5. sallia alle 2 sekunnin intervaleja
6. yhdistaa tata muutosta release-pakettien tai zip-tiedostojen siivoukseen
