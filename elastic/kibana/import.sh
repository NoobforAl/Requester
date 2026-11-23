#!/bin/sh
# Waits for Kibana, then imports the data views and dashboards (overwriting
# earlier versions). Runs in the one-shot `analytics-kibana-setup` service.
set -eu
KIBANA_URL="${KIBANA_URL:-http://kibana:5601}"
echo "Waiting for Kibana at $KIBANA_URL ..."
until curl -fsS "$KIBANA_URL/api/status" | grep -q '"level":"available"'; do sleep 5; done
curl -fsS -X POST "$KIBANA_URL/api/saved_objects/_import?overwrite=true" \
    -H "kbn-xsrf: requester" \
    --form file=@/setup/saved_objects.ndjson \
    | tee /tmp/import.json
echo
grep -q '"success":true' /tmp/import.json
echo "Kibana dashboards imported: $KIBANA_URL/app/dashboards"
