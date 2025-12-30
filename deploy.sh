#!/bin/bash

# Project OMEGA Deployment Script (Stage 19)
# Usage: ./deploy.sh

echo "🚀 Starting Project OMEGA Deployment..."

# 1. Check/Generate .env
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Generating secure defaults..."
    cat <<EOF > .env
PYTHONUNBUFFERED=1
POSTGRES_USER=admin
POSTGRES_PASSWORD=secure_password_please_change
POSTGRES_DB=omega_lake
RPC_ENDPOINT=https://api.mainnet-beta.solana.com
TELEGRAM_BOT_TOKEN=
GEYSER_ENDPOINT=
EOF
    echo "✅ .env created. PLEASE EDIT IT with your real secrets!"
fi

# 2. Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# 3. Build and Launch
echo "🐳 Building Docker images (this may take a while for Rust compilation)..."
docker-compose build

echo "🚢 Launching the Fleet..."
docker-compose up -d

# 4. Health Check
echo "🏥 Waiting for services to stabilize..."
sleep 10
docker ps

echo "✅ Deployment Triggered. Run 'docker-compose logs -f' to monitor."
