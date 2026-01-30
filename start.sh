#!/bin/bash
echo "🚀 Starting System..."
pkill -f uvicorn
pkill -f cloudflared

# Start Server
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
echo "✅ Backend started."

# Start Tunnel
nohup cloudflared tunnel --url http://localhost:8000 > tunnel.log 2>&1 &
echo "⏳ Generating public URL..."
sleep 8

TUNNEL_URL=$(grep -o 'https://[-0-9a-z]*\.trycloudflare\.com' tunnel.log | head -n 1)
echo "API_URL=$TUNNEL_URL" > .env.runtime
echo "✅ Public URL: $TUNNEL_URL"

# Start Bot
python bot/bot.py
