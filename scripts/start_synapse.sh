#!/bin/bash
# Quick start script for SYNAPSE v3.0

echo "🚀 Starting SYNAPSE v3.0..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found. Please copy .env.example to .env and configure it."
    exit 1
fi

# Check Python dependencies
echo "📦 Checking Python dependencies..."
pip install -e . > /dev/null 2>&1

# Initialize database
echo "🗄️ Initializing database..."
python -m schema.setup

# Start backend in background
echo "🔧 Starting backend server..."
uvicorn api.main:app --reload --host 0.0.0.0 --port 8082 &
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
