#!/usr/bin/env bash
set -euo pipefail

# Package EMS production runtime files into a zip archive.
# Default output: ems_production_YYYYMMDD_HHMMSS.zip
# Usage:
#   ./zippaa_ems.sh
#   ./zippaa_ems.sh -o my_ems.zip
#   ./zippaa_ems.sh --with-docs
#   ./zippaa_ems.sh -o my_ems.zip --with-docs

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

OUTPUT_FILE="ems_production_$(date +%Y%m%d_%H%M%S).zip"
WITH_DOCS=0
WITH_TESTS=1

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
    --no-tests)
      WITH_TESTS=0
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Käyttö:
  ./zippaa_ems.sh [--output tiedosto.zip] [--with-docs] [--no-tests]

Valinnat:
  -o, --output     Tulostiedoston nimi (oletus: ems_production_YYYYMMDD_HHMMSS.zip)
  --with-docs      Lisää mukaan käyttö- ja arkkitehtuuridokumentit
  --no-tests       Jätä tests-kansio pois paketista
  -h, --help       Näytä tämä ohje
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

# Minimal production runtime set.
INCLUDE_PATHS=(
  "ems_policy_engine.py"
  "ems_dispatch_state_applier.py"
  "ems_actuator_writers.py"
  "modules/ems_adapter"
  "modules/ems_core"
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
zip -r "$OUTPUT_FILE" "${EXISTING[@]}" -x '*/__pycache__/*' '*.pyc' '*.pyo'

echo "Valmis: $OUTPUT_FILE"
echo "Sisältö:"
for p in "${EXISTING[@]}"; do
  echo "  - $p"
done
