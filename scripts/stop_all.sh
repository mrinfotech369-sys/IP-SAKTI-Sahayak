#!/usr/bin/env bash
# Stop the app servers and public tunnel (Postgres and Ollama keep running).
for p in 8000 3000; do lsof -ti "tcp:$p" | xargs kill 2>/dev/null || true; done
pkill -f "cloudflared tunnel --url http://localhost:3000" 2>/dev/null || true
pkill -f "caffeinate -dims -w" 2>/dev/null || true
echo "Stopped backend, frontend and tunnel. (docker compose stop postgres to stop the DB)"
