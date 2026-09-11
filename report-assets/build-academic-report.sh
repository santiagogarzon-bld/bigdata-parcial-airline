#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

mkdir -p build/report-assets build/report

for source in diagramas/*.drawio; do
  name="$(basename "$source" .drawio)"
  drawio --no-sandbox --export --format png --scale 2 --transparent \
    --output "build/report-assets/${name}.png" "$source"
done

dot -Tpng -Gdpi=180 report-assets/concurrency-flow.dot \
  -o build/report-assets/concurrency-flow.png

pandoc report-assets/academic-metadata.yaml FINAL_REPORT.md \
  --from gfm \
  --lua-filter report-assets/academic-filter.lua \
  --resource-path=. \
  --standalone \
  --toc \
  --number-sections \
  --metadata link-citations=true \
  --output build/report/Airline_Reservation_System_Final_Report.docx

libreoffice --headless --convert-to pdf \
  --outdir build/report \
  build/report/Airline_Reservation_System_Final_Report.docx >/dev/null

echo "Generated academic DOCX and PDF in build/report/"
