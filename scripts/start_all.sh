#!/usr/bin/env bash
# Start IP-SAKTI Sahayak locally and expose it publicly.
# Usage: scripts/start_all.sh          (idempotent: skips anything already running)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$ROOT/logs"; mkdir -p "$LOGS"
PY="$ROOT/.venv/bin/python"
up() { lsof -ti "tcp:$1" >/dev/null 2>&1; }
# Run a long-lived service in its own session so closing this terminal (or a cancelled parent) can't stop it.
detach() { local log="$1"; shift; nohup perl -MPOSIX -e 'POSIX::setsid(); exec @ARGV' "$@" >>"$log" 2>&1 </dev/null & }
wait_for() { for _ in $(seq 60); do curl -sf -o /dev/null "$1" && return 0; sleep 1; done; echo "  ✗ $1 did not come up — see $LOGS"; return 1; }

echo "1/6 Docker + Postgres (pgvector)"
docker info >/dev/null 2>&1 || { open -a Docker; for _ in $(seq 60); do docker info >/dev/null 2>&1 && break; sleep 2; done; }
docker compose -f "$ROOT/docker-compose.yml" up -d postgres >/dev/null
for _ in $(seq 30); do docker compose -f "$ROOT/docker-compose.yml" exec -T postgres pg_isready -U ipsakti >/dev/null 2>&1 && break; sleep 1; done

echo "2/6 Local LLM (Ollama)"
if grep -q '^LLM_PROVIDER=ollama' "$ROOT/.env"; then
  up 11434 || { open -a Ollama 2>/dev/null || detach "$LOGS/ollama.log" ollama serve; wait_for http://localhost:11434/api/version; }
  MODEL=$(grep '^LLM_MODEL=' "$ROOT/.env" | cut -d= -f2); MODEL=${MODEL:-llama3.2}
  ollama list | grep -q "^$MODEL" || ollama pull "$MODEL"
  curl -s -m 60 localhost:11434/api/generate -d "{\"model\":\"$MODEL\",\"prompt\":\"ok\",\"stream\":false,\"keep_alive\":\"2h\"}" >/dev/null || echo "  (model preload skipped — Ollama busy; first answer may be slower)"  # preload
fi

echo "3/6 Database migrations + seed (seed skips if already seeded)"
(cd "$ROOT/backend" && ../.venv/bin/alembic upgrade head >/dev/null && PYTHONPATH=.:.. "$PY" -m app.seed.run >/dev/null)

echo "4/6 Backend (FastAPI :8000)"
up 8000 || (cd "$ROOT/backend" && PYTHONPATH="$ROOT/backend:$ROOT" detach "$LOGS/backend.log" ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000)
wait_for http://localhost:8000/health

echo "5/6 Frontend (Next.js :3000)"
if ! up 3000; then
  [ -d "$ROOT/frontend/.next" ] || (cd "$ROOT/frontend" && npm run build >"$LOGS/build.log" 2>&1)
  (cd "$ROOT/frontend" && detach "$LOGS/frontend.log" npm run start)
fi
wait_for http://localhost:3000/login

echo "6/6 Public tunnel (Cloudflare) + keep Mac awake"
if ! pgrep -f "cloudflared tunnel --url http://localhost:3000" >/dev/null; then
  detach "$LOGS/tunnel.log" cloudflared tunnel --url http://localhost:3000
  for _ in $(seq 60); do grep -q trycloudflare.com "$LOGS/tunnel.log" 2>/dev/null && break; sleep 1; done
fi
TPID=$(pgrep -f "cloudflared tunnel --url http://localhost:3000" | head -1)
pgrep -f "caffeinate -dims -w $TPID" >/dev/null || detach /dev/null caffeinate -dims -w "$TPID"
URL=""
for port in $(lsof -Pan -p "$TPID" -iTCP -sTCP:LISTEN 2>/dev/null | awk 'NR>1{split($9,a,":");print a[2]}'); do
  h=$(curl -s -m 2 "localhost:$port/quicktunnel" | "$PY" -c "import sys,json;print(json.load(sys.stdin).get('hostname',''))" 2>/dev/null || true)
  [ -n "$h" ] && URL="https://$h" && break
done

echo
echo "✓ IP-SAKTI Sahayak is live"
echo "  Local:   http://localhost:3000"
echo "  Public:  ${URL:-see $LOGS/tunnel.log}"
echo "  API:     http://localhost:8000/docs"
curl -s localhost:8000/health/llm | "$PY" -c "import sys,json;d=json.load(sys.stdin)['data'];print('  LLM:    ',d.get('provider',d.get('llm')),d.get('detail',''))"
echo "  Login:   researcher@ipsakti.demo / Demo@12345  (admin@ipsakti.demo for admin)"
