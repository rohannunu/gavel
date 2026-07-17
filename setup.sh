#!/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[setup]${NC} $1"; }
warn()    { echo -e "${YELLOW}[warn]${NC}  $1"; }
error()   { echo -e "${RED}[error]${NC} $1"; exit 1; }

echo ""
echo "=== Gavel Setup ==="
echo ""

# --- Prerequisites ---

if ! command -v python3 &>/dev/null; then
    error "Python 3 is required but not found. Install it from https://python.org"
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(sys.version_info.major * 10 + sys.version_info.minor)')
if [ "$PYTHON_VERSION" -lt 38 ]; then
    error "Python 3.8+ is required. Found: $(python3 --version)"
fi
info "Python: $(python3 --version)"

if ! command -v docker &>/dev/null; then
    error "Docker is required but not found. Install Docker Desktop from https://docker.com"
fi
info "Docker: $(docker --version)"

# --- Virtual environment ---

if [ ! -d ".venv" ]; then
    info "Creating virtual environment..."
    python3 -m venv .venv
else
    info "Virtual environment already exists, skipping."
fi

info "Activating virtual environment..."
source .venv/bin/activate

# --- Dependencies ---

info "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
info "Dependencies installed."

# --- Config ---

if [ ! -f "config.yaml" ]; then
    info "Creating config.yaml with local dev defaults..."
    cat > config.yaml << 'EOF'
admin_password: admin

email_from: "_unused_"
email_user: "_unused_"
email_password: "_unused_"

secret_key: "dev-secret-change-me-please-1234567890"

server_name: null
proxy: false

db_uri: "postgresql://postgres:postgres@localhost:5432/gavel"

broker_uri: null

use_sendgrid: false
sendgrid_api_key: null

min_views: 1
timeout: 5.0
stateless_logins: true

disable_email: true
email_auth_mode: "_unused_"
email_host: "_unused_"
email_port: 0
email_cc: []

send_stats: true
EOF
    info "config.yaml created."
else
    info "config.yaml already exists, skipping."
fi

# --- Docker Postgres ---

CONTAINER_NAME="gavel-postgres"
DB_NAME="gavel"
DB_USER="postgres"
DB_PASS="postgres"
DB_PORT="5432"

if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    info "Postgres container '$CONTAINER_NAME' is already running."
elif docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    info "Starting existing Postgres container '$CONTAINER_NAME'..."
    docker start "$CONTAINER_NAME"
else
    info "Creating Postgres container '$CONTAINER_NAME'..."
    docker run -d \
        --name "$CONTAINER_NAME" \
        -e POSTGRES_PASSWORD="$DB_PASS" \
        -e POSTGRES_DB="$DB_NAME" \
        -p "${DB_PORT}:5432" \
        postgres:15
fi

info "Waiting for Postgres to be ready..."
for i in $(seq 1 20); do
    if docker exec "$CONTAINER_NAME" pg_isready -U "$DB_USER" -q 2>/dev/null; then
        break
    fi
    if [ "$i" -eq 20 ]; then
        error "Postgres did not become ready in time."
    fi
    sleep 1
done
info "Postgres is ready."

# --- Database schema ---

info "Initializing database schema..."
python initialize.py
info "Schema initialized."

# --- Done ---

echo ""
echo "=== Setup complete! ==="
echo ""
echo "To run the server:"
echo ""
echo "  source .venv/bin/activate"
echo "  python runserver.py"
echo ""
echo "Then open http://localhost:5001/admin and log in with password: admin"
echo ""
