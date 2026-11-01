#!/bin/bash
# Caterva Web Server Startup Script

set -e

echo "📦 Building Caterva..."
npm run build

echo ""
echo "🚀 Starting Caterva Web Server..."
echo ""

node dist/src/web/server.js
