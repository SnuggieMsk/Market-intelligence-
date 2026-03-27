#!/bin/bash
# Start both scanner (background) and dashboard (foreground)
# For single-container deployment (e.g., Render, Railway)

echo "Starting Market Intelligence System..."

# Initialize the database
python -c "from data.database import init_db; init_db()"

# Start scanner in background
python main.py --continuous &
SCANNER_PID=$!

# Start dashboard in foreground
streamlit run dashboard/app.py \
    --server.port 8501 \
    --server.headless true \
    --server.address 0.0.0.0 &
DASHBOARD_PID=$!

echo "Scanner PID: $SCANNER_PID"
echo "Dashboard PID: $DASHBOARD_PID"
echo "Dashboard: http://localhost:8501"

# Wait for either to exit
wait -n $SCANNER_PID $DASHBOARD_PID
