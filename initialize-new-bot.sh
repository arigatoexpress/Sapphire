#!/bin/bash

# Sapphire Trade Bot Initialization Script
# Automatically creates new trading bots with proper Telegram and Aster DEX configuration

set -e

NAMESPACE="trading"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Show usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Initialize a new trading bot with proper configuration"
    echo ""
    echo "OPTIONS:"
    echo "  --name NAME          Bot name (required)"
    echo "  --strategy STRATEGY  Trading strategy (required)"
    echo "  --risk RISK_LEVEL    Risk level: low/medium/high (default: medium)"
    echo "  --capital AMOUNT     Capital allocation in USD (default: 500)"
    echo "  --dry-run           Show what would be created without applying"
    echo "  --help              Show this help message"
    echo ""
    echo "EXAMPLES:"
    echo "  $0 --name momentum-bot --strategy momentum --risk medium --capital 750"
    echo "  $0 --name sentiment-bot --strategy sentiment-analysis --risk low --capital 500"
    echo "  $0 --name momentum-bot --strategy momentum --dry-run"
}

# Validate inputs
validate_inputs() {
    if [ -z "$BOT_NAME" ]; then
        log_error "Bot name is required (--name)"
        exit 1
    fi
    
    if [ -z "$BOT_STRATEGY" ]; then
        log_error "Bot strategy is required (--strategy)"
        exit 1
    fi
    
    # Validate risk level
    case "$RISK_LEVEL" in
        low|medium|high) ;;
        *) log_error "Risk level must be: low, medium, or high"
           exit 1 ;;
    esac
    
    # Validate capital amount
    if ! [[ "$CAPITAL_ALLOCATION" =~ ^[0-9]+$ ]] || [ "$CAPITAL_ALLOCATION" -lt 100 ] || [ "$CAPITAL_ALLOCATION" -gt 5000 ]; then
        log_error "Capital allocation must be between 100 and 5000 USD"
        exit 1
    fi
    
    log_success "Input validation passed"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if namespace exists
    if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
        log_error "Namespace '$NAMESPACE' does not exist"
        exit 1
    fi
    
    # Check if required secrets exist
    if ! kubectl get secret aster-dex-credentials -n "$NAMESPACE" >/dev/null 2>&1; then
        log_error "Required secret 'aster-dex-credentials' not found"
        exit 1
    fi
    
    if ! kubectl get secret telegram-secret -n "$NAMESPACE" >/dev/null 2>&1; then
        log_error "Required secret 'telegram-secret' not found"
        exit 1
    fi
    
    # Check if bot already exists
    if kubectl get deployment "$BOT_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
        log_error "Bot '$BOT_NAME' already exists"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Generate bot configuration
generate_config() {
    log_info "Generating configuration for bot: $BOT_NAME"
    
    # Create temporary config file
    TEMP_CONFIG=$(mktemp)
    
    # Replace template variables
    sed -e "s/{{BOT_NAME}}/$BOT_NAME/g" \
        -e "s/{{BOT_STRATEGY}}/$BOT_STRATEGY/g" \
        -e "s/{{RISK_LEVEL}}/$RISK_LEVEL/g" \
        -e "s/{{CAPITAL_ALLOCATION}}/$CAPITAL_ALLOCATION/g" \
        bot-config-template.yaml > "$TEMP_CONFIG"
    
    log_success "Configuration generated"
    echo "$TEMP_CONFIG"
}

# Deploy bot
deploy_bot() {
    local config_file="$1"
    
    if [ "$DRY_RUN" = true ]; then
        log_info "DRY RUN: Would deploy the following configuration:"
        echo "---"
        cat "$config_file"
        echo "---"
        return 0
    fi
    
    log_info "Deploying bot: $BOT_NAME"
    
    # Apply the configuration
    if kubectl apply -f "$config_file" -n "$NAMESPACE"; then
        log_success "Bot deployment initiated"
    else
        log_error "Failed to deploy bot"
        return 1
    fi
    
    # Wait for deployment to be ready
    log_info "Waiting for bot to be ready..."
    if kubectl rollout status deployment/"$BOT_NAME" -n "$NAMESPACE" --timeout=300s; then
        log_success "Bot deployment completed successfully"
    else
        log_error "Bot deployment timed out"
        return 1
    fi
}

# Verify deployment
verify_deployment() {
    if [ "$DRY_RUN" = true ]; then
        log_info "DRY RUN: Skipping verification"
        return 0
    fi
    
    log_info "Verifying bot deployment..."
    
    # Check pod status
    if kubectl get pods -n "$NAMESPACE" -l "app=$BOT_NAME" --no-headers | grep -q Running; then
        log_success "Pod is running"
    else
        log_error "Pod is not running"
        kubectl get pods -n "$NAMESPACE" -l "app=$BOT_NAME"
        return 1
    fi
    
    # Check service
    if kubectl get service "$BOT_NAME-service" -n "$NAMESPACE" >/dev/null 2>&1; then
        log_success "Service is created"
    else
        log_error "Service creation failed"
        return 1
    fi
    
    # Check configuration
    if kubectl get configmap "$BOT_NAME-config" -n "$NAMESPACE" >/dev/null 2>&1; then
        log_success "Configuration is created"
    else
        log_error "Configuration creation failed"
        return 1
    fi
    
    # Test configuration injection
    log_info "Testing configuration injection..."
    if kubectl exec -n "$NAMESPACE" deployment/"$BOT_NAME" -- env | grep -q "BOT_NAME=$BOT_NAME"; then
        log_success "Configuration properly injected"
    else
        log_error "Configuration injection failed"
        return 1
    fi
    
    log_success "Bot verification completed"
}

# Main execution
main() {
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --name)
                BOT_NAME="$2"
                shift 2
                ;;
            --strategy)
                BOT_STRATEGY="$2"
                shift 2
                ;;
            --risk)
                RISK_LEVEL="$2"
                shift 2
                ;;
            --capital)
                CAPITAL_ALLOCATION="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --help)
                usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done
    
    # Set defaults
    RISK_LEVEL="${RISK_LEVEL:-medium}"
    CAPITAL_ALLOCATION="${CAPITAL_ALLOCATION:-500}"
    DRY_RUN="${DRY_RUN:-false}"
    
    echo "🤖 SAPPHIRE TRADE BOT INITIALIZER"
    echo "=================================="
    echo "Bot Name: $BOT_NAME"
    echo "Strategy: $BOT_STRATEGY"
    echo "Risk Level: $RISK_LEVEL"
    echo "Capital: \$$CAPITAL_ALLOCATION"
    if [ "$DRY_RUN" = true ]; then
        echo "Mode: DRY RUN"
    fi
    echo ""
    
    # Execute steps
    validate_inputs
    check_prerequisites
    
    CONFIG_FILE=$(generate_config)
    
    if deploy_bot "$CONFIG_FILE"; then
        if verify_deployment; then
            echo ""
            echo "🎉 BOT INITIALIZATION COMPLETE!"
            echo "================================"
            echo "✅ Bot: $BOT_NAME"
            echo "✅ Strategy: $BOT_STRATEGY"
            echo "✅ Configuration: Telegram + Aster DEX ready"
            echo "✅ Capital: \$$CAPITAL_ALLOCATION allocated"
            echo "✅ Status: Running and monitored"
            echo ""
            echo "🚀 Your new bot is ready for live trading!"
            
            # Cleanup temp file
            rm -f "$CONFIG_FILE"
            exit 0
        fi
    fi
    
    # Cleanup on failure
    rm -f "$CONFIG_FILE"
    log_error "Bot initialization failed"
    exit 1
}

# Run main function
main "$@"
