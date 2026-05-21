#!/bin/bash
# Quick start script for SYNAPSE v3.0 using uv

echo "🚀 Starting SYNAPSE v3.0 with uv..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found. Please copy .env.example to .env and configure it."
    exit 1
fi

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv not found. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Install dependencies with uv
echo "📦 Installing dependencies with uv..."
uv sync

# Initialize database
echo "🗄️ Initializing database..."
uv run python -m schema.setup

# Start backend in background
echo "🔧 Starting backend server..."
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8082 &
BACKEND_PID=$!

# Wait for backend to start
sleep 5

# Check backend health
echo "🏥 Checking backend health..."
curl -s http://localhost:8082/api/v1/health > /dev/null
if [ $? -eq 0 ]; then
    echo "✅ Backend is healthy"
else
    echo "❌ Backend failed to start"
    kill $BACKEND_PID
    exit 1
fi

# Start frontend
echo "🎨 Starting frontend..."
cd frontend
npm run dev &
FRONTEND_PID=$!

echo "🎉 SYNAPSE is running!"
echo "📱 Frontend: http://localhost:5173"
echo "🔧 Backend: http://localhost:8082"
echo "📚 API Docs: http://localhost:8082/docs"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for Ctrl+C
trap "echo '🛑 Stopping services...'; kill $BACKEND_PID $FRONTEND_PID; exit" INT
wait
