#!/usr/bin/env bash
set -euo pipefail

# Package EMS production runtime files into a zip archive.
# Default output: ems_production_YYYYMMDD_HHMMSS.zip
# Usage:
#   ./zippaa_ems.sh
#   ./zippaa_ems.sh -o my_ems.zip
#   ./zippaa_ems.sh --with-docs
#   ./zippaa_ems.sh --with-tests
#   ./zippaa_ems.sh -o my_ems.zip --with-docs --with-tests

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

OUTPUT_FILE="ems_production_$(date +%Y%m%d_%H%M%S).zip"
WITH_DOCS=0
WITH_TESTS=0
RUN_PREFLIGHT=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output)
      if [[ $# -lt 2 ]]; then
        echo "Virhe: --output vaatii tiedostonimen" >&2
        exit 1
      fi
      OUTPUT_FILE="$2"
      shift 2
      ;;
    --with-docs)
      WITH_DOCS=1
      shift
      ;;
    --with-tests)
      WITH_TESTS=1
      shift
      ;;
    --no-tests)
      WITH_TESTS=0
      shift
      ;;
    --no-preflight)
      RUN_PREFLIGHT=0
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Kaytto:
  ./zippaa_ems.sh [--output tiedosto.zip] [--with-docs] [--with-tests] [--no-preflight]

Valinnat:
  -o, --output     Tulostiedoston nimi (oletus: ems_production_YYYYMMDD_HHMMSS.zip)
  --with-docs      Lisaa mukaan kaytto-, arkkitehtuuri- ja refaktorointidokumentit
  --with-tests     Lisaa tests-kansio mukaan pakettiin
  --no-tests       Jata tests-kansio pois paketista (oletus)
  --no-preflight   Ohita Pyscript-yhteensopivuuden smoke-tarkistus
  -h, --help       Nayta tama ohje
EOF
      exit 0
      ;;
    *)
      echo "Virhe: tuntematon argumentti: $1" >&2
      exit 1
      ;;
  esac
done

if ! command -v zip >/dev/null 2>&1; then
  echo "Virhe: 'zip' komentoa ei löytynyt. Asenna zip-paketti ensin." >&2
  exit 1
fi

if [[ ! -f "EMS_config.yaml" ]]; then
  echo "Virhe: EMS_config.yaml puuttuu. Tuotantopaketti vaatii grouped config -tiedoston." >&2
  exit 1
fi

if [[ ! -f "requirements.txt" ]]; then
  echo "Virhe: requirements.txt puuttuu. Tuotantopaketti vaatii riippuvuuslistan." >&2
  exit 1
fi

if [[ $RUN_PREFLIGHT -eq 1 ]]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Virhe: python3 komentoa ei loytynyt, Pyscript-preflightia ei voida ajaa." >&2
    exit 1
  fi
  echo "Ajetaan Pyscript-yhteensopivuuden preflight..."
  python3 -m pytest -q tests/smoke/test_pyscript_ast_compat.py
fi

# Minimal production runtime set.
INCLUDE_PATHS=(
  "ems_policy_engine.py"
  "ems_dispatch_state_applier.py"
  "ems_actuator_writers.py"
  "modules/ems_adapter"
  "modules/ems_core"
  "requirements.txt"
  "EMS_config.yaml"
)

if [[ $WITH_TESTS -eq 1 ]]; then
  INCLUDE_PATHS+=("tests")
fi

# Optional operational docs for production handover/use.
if [[ $WITH_DOCS -eq 1 ]]; then
  INCLUDE_PATHS+=(
    "README.md"
    "operointi.md"
    "arkkitehtuuri.md"
    "EMS_parametrointi_guide.md"
    "tests/e2e_entity/e2e_refactoring.md"
  )
fi

MISSING=()
EXISTING=()
for p in "${INCLUDE_PATHS[@]}"; do
  if [[ -e "$p" ]]; then
    EXISTING+=("$p")
  else
    MISSING+=("$p")
  fi
done

if [[ ${#EXISTING[@]} -eq 0 ]]; then
  echo "Virhe: mitään pakattavaa ei löytynyt." >&2
  exit 1
fi

if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "Huom: seuraavia polkuja ei löytynyt, ohitetaan:" >&2
  for p in "${MISSING[@]}"; do
    echo "  - $p" >&2
  done
fi

rm -f "$OUTPUT_FILE"
zip -r "$OUTPUT_FILE" "${EXISTING[@]}" \
  -x '*/__pycache__/*' \
  -x '*.pyc' \
  -x '*.pyo' \
  -x '.pytest_cache/*' \
  -x '*/.pytest_cache/*' \
  -x '.git/*' \
  -x '*.zip'

if command -v zipinfo >/dev/null 2>&1; then
  ZIP_ENTRIES="$(zipinfo -1 "$OUTPUT_FILE")"
  for required_entry in \
    "ems_policy_engine.py" \
    "ems_dispatch_state_applier.py" \
    "ems_actuator_writers.py" \
    "modules/ems_adapter/" \
    "modules/ems_core/" \
    "requirements.txt" \
    "EMS_config.yaml"; do
    if ! printf '%s\n' "$ZIP_ENTRIES" | grep -Fx -- "$required_entry" >/dev/null; then
      echo "Virhe: paketin pakollinen sisältö puuttuu: $required_entry" >&2
      exit 1
    fi
  done
fi

echo "Valmis: $OUTPUT_FILE"
echo "Sisältö:"
for p in "${EXISTING[@]}"; do
  echo "  - $p"
done
