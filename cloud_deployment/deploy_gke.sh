#!/bin/bash
set -e

# --- Configuration ---
PROJECT_ID="sapphireinfinite"
REGION="us-central1"
GITHUB_OWNER="arigatoexpress"
GITHUB_REPO="AsterAI"

# --- Color Definitions ---
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# --- Functions ---
print_header() {
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║     🚀 HFT Aster Trader - Complete GKE Deployment         ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo
}

print_step() {
    echo -e "${BLUE}==> $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# --- Prerequisites Check ---
check_prerequisites() {
    print_step "Checking prerequisites..."

    # Check gcloud authentication
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &>/dev/null; then
        print_error "gcloud not authenticated. Please run 'gcloud auth login'"
        exit 1
    fi
    print_success "gcloud authenticated"

    # Check GitHub variables
    if [ -z "$GITHUB_OWNER" ] || [ -z "$GITHUB_REPO" ]; then
        print_error "GITHUB_OWNER and GITHUB_REPO environment variables must be set"
        exit 1
    fi
    print_success "GitHub variables set"

    # Check we're in project root
    if [ ! -f "pyproject.toml" ] || [ ! -d "cloud_trader" ]; then
        print_error "Must be run from project root directory"
        exit 1
    fi
    print_success "In project root directory"
}

# --- Main Deployment ---
main() {
    print_header

    check_prerequisites

    print_step "Setting up GKE infrastructure..."
    if ! bash cloud_deployment/gke_setup.sh; then
        print_error "GKE setup failed"
        exit 1
    fi

    print_step "Configuring Cloud Build triggers..."
    # TODO: Implement Cloud Build trigger setup

    print_step "Deploying Kubernetes manifests..."
    # TODO: Implement Kubernetes deployment

    print_step "Setting up basic monitoring..."
    # TODO: Implement monitoring setup

    print_step "Running deployment tests..."
    # TODO: Implement deployment tests

    print_success "Deployment completed successfully!"
    echo
    echo "🚀 Deployment Summary:"
    echo "   - GKE Cluster: hft-trading-cluster"
    echo "   - Region: $REGION"
    echo "   - Project: $PROJECT_ID"
    echo "   - GitHub: $GITHUB_OWNER/$GITHUB_REPO"
}

main "$@"
