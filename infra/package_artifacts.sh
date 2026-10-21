#!/usr/bin/env bash
# Pack the build inputs the repository cannot hold and upload them to the private bucket.
# Run once, and again only when the model, LOINC table or ICD-10 file changes:
#   infra/package_artifacts.sh                     # writes data/nwoma-artifacts.tar.gz only
#   infra/package_artifacts.sh <bucket> <profile>  # and uploads it with that AWS profile
# The LOINC table's licence forbids redistribution, so it goes to a private bucket, never git.
set -euo pipefail

BUCKET="${1:-}"
PROFILE="${2:-}"
cd "$(dirname "$0")/.."
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT

mkdir -p "$OUT/models" "$OUT/data/loinc/LoincTable" "$OUT/data/loinc/AccessoryFiles/LinguisticVariants" \
  "$OUT/data/icd10cm/Code Descriptions" "$OUT/data/cache" "$OUT/hf/hub"
cp -r models/ner "$OUT/models/ner"
cp data/loinc/LoincTable/Loinc.csv "$OUT/data/loinc/LoincTable/"
cp data/loinc/AccessoryFiles/LinguisticVariants/frFR*.csv "$OUT/data/loinc/AccessoryFiles/LinguisticVariants/"
cp "data/icd10cm/Code Descriptions/icd10cm_order_2027.txt" "$OUT/data/icd10cm/Code Descriptions/"
cp data/cache/loinc_names-*.npy data/cache/icd10_names-*.npy "$OUT/data/cache/"
# The embedding model, from the Hugging Face cache, with its symlinks resolved.
cp -rL ~/.cache/huggingface/hub/models--intfloat--multilingual-e5-small "$OUT/hf/hub/"

tar -czf data/nwoma-artifacts.tar.gz -C "$OUT" models data hf
ls -lh data/nwoma-artifacts.tar.gz
if [[ -n "$BUCKET" && -n "$PROFILE" ]]; then
  aws s3 cp data/nwoma-artifacts.tar.gz "s3://$BUCKET/nwoma-artifacts.tar.gz" --profile "$PROFILE"
else
  echo "Upload data/nwoma-artifacts.tar.gz to the build-inputs bucket (S3 console > Upload)."
fi
