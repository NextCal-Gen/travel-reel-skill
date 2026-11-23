#!/usr/bin/env bash
# Route-map base data from OpenStreetMap (ODbL; credit "© OpenStreetMap contributors").
# Major roads + rivers + lakes for the Bengaluru -> Kanakapura area. Retries with exponential
# backoff across public Overpass endpoints (servers ask for this when at capacity).
# Output: assets/map/osm_base.json
set -u
cd "$(dirname "$0")/.."
Q='[out:json][timeout:150];(way["highway"~"^(motorway|trunk|primary|secondary)$"](12.50,77.25,13.03,77.66);way["waterway"="river"](12.50,77.25,13.03,77.66);way["natural"="water"](12.50,77.25,13.03,77.66);relation["natural"="water"](12.50,77.25,13.03,77.66););out geom;'
EPS=(https://overpass-api.de/api/interpreter https://overpass.kumi.systems/api/interpreter https://overpass.private.coffee/api/interpreter)
wait=30
for attempt in 1 2 3 4 5; do
  for ep in "${EPS[@]}"; do
    code=$(curl -s -A "travel-reel-map/1.0" --max-time 200 -w "%{http_code}" --data-urlencode "data=$Q" "$ep" -o assets/map/_osm_try.json)
    if [ "$code" = "200" ] && head -c 1 assets/map/_osm_try.json | grep -q "{"; then
      mv assets/map/_osm_try.json assets/map/osm_base.json
      echo "OK attempt $attempt via $ep ($(wc -c < assets/map/osm_base.json) bytes)"; exit 0
    fi
    echo "attempt $attempt $ep -> HTTP $code"
  done
  echo "backoff ${wait}s"; sleep $wait; wait=$((wait * 2))
done
echo "FAILED after 5 rounds"; exit 1
