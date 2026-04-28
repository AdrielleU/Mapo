#!/usr/bin/env bash
#
# Convert a Webshare proxy CSV download into a mapo.yaml `proxy:` block.
#
# Webshare gives you the file at https://proxy.webshare.io/proxy/list/download/.
# Format is one proxy per line, header on the first line:
#
#     proxy_address,port,username,password,valid,last_verification,country_code,city_name
#     1.2.3.4,6540,abcuser-1,abcpass-1,True,2026-04-01,US,Ashburn
#     ...
#
# Usage:
#   scripts/webshare-import.sh proxies.csv                       # print yaml to stdout
#   scripts/webshare-import.sh proxies.csv random                # use random rotation
#   scripts/webshare-import.sh proxies.csv > proxies.yaml        # save to file
#   scripts/webshare-import.sh proxies.csv | tee -a mapo.yaml    # append to mapo.yaml
#
# To use the output, replace your existing `proxy:` block in mapo.yaml with
# the printed one, then restart: `docker compose up -d --force-recreate`.

set -euo pipefail

if [ $# -lt 1 ] || [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  cat <<EOF >&2
usage: $0 PROXY_CSV [round_robin|random|geo_match]

  PROXY_CSV   path to the file you downloaded from
              https://proxy.webshare.io/proxy/list/download/

  rotation    optional, defaults to round_robin. one of:
                round_robin  cycle through proxies in order (default)
                random       pick a random proxy per request
                geo_match    pick a proxy whose country matches the search

Output is the mapo.yaml proxy block on stdout. No files are modified.
EOF
  exit 2
fi

csv=$1
rotation=${2:-round_robin}

case "$rotation" in
  round_robin|random|geo_match) ;;
  *) echo "error: rotation must be round_robin, random, or geo_match (got: $rotation)" >&2; exit 2 ;;
esac

if [ ! -r "$csv" ]; then
  echo "error: cannot read $csv" >&2
  exit 1
fi

# Count rows for the trailing comment (helps verify nothing was dropped).
total=$(tail -n +2 "$csv" | awk -F',' 'NF >= 4 && $1 != "" {n++} END {print n+0}')

if [ "$total" -eq 0 ]; then
  echo "error: no valid proxy rows found in $csv (expected: ip,port,user,pass,...)" >&2
  exit 1
fi

cat <<EOF
# --- Generated from $(basename "$csv") on $(date -u +"%Y-%m-%dT%H:%M:%SZ") ---
# $total proxies imported. Replace your existing 'proxy:' block in mapo.yaml.
proxy:
  enabled: true
  rotation: $rotation
EOF

# geo_match needs per-proxy country codes — emit them as inline comments so
# the operator can see which IPs map to which country and tune if needed.
if [ "$rotation" = "geo_match" ]; then
  echo "  geo_match: true"
fi

echo "  urls:"

tail -n +2 "$csv" | awk -F',' '
  NF < 4 { next }
  $1 == "" { next }
  {
    gsub(/\r/, "")
    # Field positions: 1=ip, 2=port, 3=user, 4=pass, 7=country (if present)
    country = (NF >= 7 && $7 != "") ? "  # " $7 : ""
    printf "    - \"http://%s:%s@%s:%s\"%s\n", $3, $4, $1, $2, country
  }
'
