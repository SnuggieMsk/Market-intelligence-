#!/bin/bash
# ══════════════════════════════════════════════════════════════════════════════
# Oracle Cloud Free Tier Deployment Script
# Run this on your Oracle Cloud VM (Ubuntu/Oracle Linux)
# ══════════════════════════════════════════════════════════════════════════════

set -e

echo "═══ Market Intelligence — Oracle Cloud Setup ═══"

# 1. Install system dependencies
echo "[1/6] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv git docker.io docker-compose-v2 2>/dev/null || \
sudo yum install -y python3 python3-pip git docker docker-compose 2>/dev/null

# 2. Clone the repo
echo "[2/6] Cloning repository..."
if [ ! -d "Market-intelligence-" ]; then
    git clone https://github.com/SnuggieMsk/Market-intelligence-.git
fi
cd Market-intelligence-

# 3. Set up Python virtual environment
echo "[3/6] Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Set up .env
echo "[4/6] Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  IMPORTANT: Edit .env with your actual API keys!           ║"
    echo "║  nano .env                                                  ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
fi

# 5. Run tests
echo "[5/6] Running validation tests..."
python test_setup.py || echo "Some tests failed — check output above"

# 6. Open firewall for dashboard
echo "[6/6] Opening port 8501 for dashboard..."
sudo iptables -I INPUT -p tcp --dport 8501 -j ACCEPT 2>/dev/null || true
# For Oracle Cloud, also need to open in the VCN security list via the console

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo " Setup complete! Next steps:"
echo ""
echo " 1. Edit your API keys:  nano .env"
echo " 2. Run tests:           python test_setup.py"
echo " 3. Run scanner:         python main.py"
echo " 4. Run continuously:    nohup python main.py --continuous &"
echo " 5. Run dashboard:       nohup streamlit run dashboard/app.py \\"
echo "                           --server.port 8501 \\"
echo "                           --server.headless true \\"
echo "                           --server.address 0.0.0.0 &"
echo ""
echo " Dashboard URL: http://<your-vm-ip>:8501"
echo ""
echo " OR use Docker:"
echo "   docker compose up -d"
echo "═══════════════════════════════════════════════════════════════"
