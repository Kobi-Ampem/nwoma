#!/usr/bin/env bash
# Generate synthetic patients with a pinned Synthea release.
# Usage: datagen/run_synthea.sh [population] [seed]
set -euo pipefail

SYNTHEA_VERSION="v3.3.0"
POPULATION="${1:-200}"
SEED="${2:-42}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SYNTHEA_DIR="$ROOT/synthea"
JAR="$SYNTHEA_DIR/synthea-$SYNTHEA_VERSION.jar"
OUT="$ROOT/data/synthea"

mkdir -p "$SYNTHEA_DIR"
if [[ ! -f "$JAR" ]]; then
  curl -fsSL -o "$JAR" \
    "https://github.com/synthetichealth/synthea/releases/download/$SYNTHEA_VERSION/synthea-with-dependencies.jar"
fi

rm -rf "$OUT"
# CSV only: lighter than FHIR JSON and read directly by pandas.
# -Xmx1g keeps the JVM within the laptop's memory budget.
java -Xmx1g -jar "$JAR" \
  -p "$POPULATION" \
  -s "$SEED" \
  -cs "$SEED" \
  --exporter.baseDirectory "$OUT" \
  --exporter.csv.export true \
  --exporter.fhir.export false \
  --exporter.hospital.fhir.export false \
  --exporter.practitioner.fhir.export false \
  --exporter.years_of_history 5 \
  --generate.only_alive_patients true
