#!/bin/bash
#
# Script to fix church bot permissions and SSH key issues
#

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Output formatting functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_warning "This script needs to be run with sudo or as root."
    log_info "Please run: sudo $0"
    exit 1
fi

# Define directories to fix
DOCKER_DIR="$(pwd)"
BACKUPS_DIR="/app/backups"
DATA_DIR="/app/data"
SSH_DIR="/app/ssh"
PROJECT_DIR="/app/project"

log_info "Starting permission fixes for the church bot..."

# Fix directory creation and permissions
log_info "Creating necessary directories with proper permissions..."
mkdir -p "$BACKUPS_DIR" "$DATA_DIR" "$SSH_DIR"

# Set correct ownership and permissions
log_info "Setting correct ownership and permissions..."
chown -R botuser:botuser "$BACKUPS_DIR" "$DATA_DIR" "$SSH_DIR" 2>/dev/null || \
  chown -R 1000:1000 "$BACKUPS_DIR" "$DATA_DIR" "$SSH_DIR"

chmod -R 755 "$BACKUPS_DIR" "$DATA_DIR"
chmod -R 700 "$SSH_DIR"

# Fix SSH key issues
log_info "Checking SSH key..."

# Copy SSH key if it exists in the docker/ssh directory
if [[ -f "${DOCKER_DIR}/ssh/id_rsa" && ! -f "${SSH_DIR}/id_rsa" ]]; then
    log_info "Copying SSH key from ${DOCKER_DIR}/ssh/id_rsa to ${SSH_DIR}/id_rsa"
    cp "${DOCKER_DIR}/ssh/id_rsa" "${SSH_DIR}/id_rsa"
    chmod 600 "${SSH_DIR}/id_rsa"
    log_success "SSH key copied and permissions set"
elif [[ ! -f "${SSH_DIR}/id_rsa" ]]; then
    log_warning "No SSH key found in ${SSH_DIR}/id_rsa or ${DOCKER_DIR}/ssh/id_rsa"
    
    # Check if we have a PPK file that needs conversion
    if [[ -f "${DOCKER_DIR}/ssh/mobakey.ppk" ]]; then
        log_info "PuTTY .ppk key found at ${DOCKER_DIR}/ssh/mobakey.ppk"
        log_info "You need to convert it to OpenSSH format using puttygen:"
        log_info "puttygen mobakey.ppk -O private-openssh -o id_rsa"
        log_info "Then copy the id_rsa file to ${SSH_DIR}/id_rsa"
    else
        log_error "No SSH key files found. Please create an SSH key and place it in ${SSH_DIR}/id_rsa"
        log_info "Make sure to set proper permissions: chmod 600 ${SSH_DIR}/id_rsa"
    fi
else
    log_info "SSH key exists at ${SSH_DIR}/id_rsa"
    # Make sure it has correct permissions
    chmod 600 "${SSH_DIR}/id_rsa"
    log_success "SSH key permissions set correctly"
fi

# Check if the SSH key belongs to the correct user
log_info "Setting SSH key ownership..."
chown botuser:botuser "${SSH_DIR}/id_rsa" 2>/dev/null || \
  chown 1000:1000 "${SSH_DIR}/id_rsa" 2>/dev/null
  
# Test if container can access the key
log_info "Testing container access to the key..."
if docker ps | grep -q "church-schedule-bot"; then
    docker exec church-schedule-bot ls -la /app/ssh/id_rsa 2>/dev/null
    if [ $? -eq 0 ]; then
        log_success "Container can access the SSH key"
    else
        log_error "Container cannot access the SSH key. Please check container mount points."
    fi
else
    log_warning "Container church-schedule-bot is not running. Can't test key access."
fi

# Fix index.html permissions
if [[ -f "${PROJECT_DIR}/index.html" ]]; then
    log_info "Setting correct permissions for index.html..."
    chmod 644 "${PROJECT_DIR}/index.html"
    chown botuser:botuser "${PROJECT_DIR}/index.html" 2>/dev/null || \
      chown 1000:1000 "${PROJECT_DIR}/index.html" 2>/dev/null
    log_success "index.html permissions fixed"
else
    log_warning "index.html not found at ${PROJECT_DIR}/index.html"
fi

log_success "Permission fixes completed!"
log_info "If issues persist, you may need to restart the bot container:"
log_info "docker-compose restart church-bot"
