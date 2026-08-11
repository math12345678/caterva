#!/bin/bash
# Terrium Web Server Startup Script

set -e

echo "📦 Building Terrium..."
npm run build

echo ""
echo "🚀 Starting Terrium Web Server..."
echo ""

node dist/src/web/server.js
