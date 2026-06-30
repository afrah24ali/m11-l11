#!/usr/bin/env bash
set -euo pipefail

echo "Waiting for Neo4j container to be running ..."

for i in {1..60}; do
  if docker compose ps -q neo4j >/dev/null 2>&1 && [ -n "$(docker compose ps -q neo4j)" ]; then
    status="$(docker inspect -f '{{.State.Status}}' "$(docker compose ps -q neo4j)")"
    echo "neo4j status=$status"

    if [ "$status" = "running" ]; then
      break
    fi
  fi

  sleep 2
done

echo "Seeding Neo4j (loading api/seed.cypher via cypher-shell inside the neo4j container) ..."

docker compose exec -T neo4j cypher-shell \
  -u neo4j \
  -p "${NEO4J_PASSWORD:-devpassword}" \
  -f /var/lib/neo4j/import/seed.cypher

echo "Done."