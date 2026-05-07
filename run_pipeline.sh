#!/bin/bash
# VIDYUT AI — Full Pipeline Runner
# Usage:
#   ./run_pipeline.sh setup      # Install deps, generate data, train models (~30 min)
#   ./run_pipeline.sh start      # Start backend + frontend
#   ./run_pipeline.sh retrain    # Retrain models with latest data
#   ./run_pipeline.sh demo       # Start + open browser
#
# Flags:
#   --skip-rl                    # Skip RL agent training (for faster setup)

set -euo pipefail
trap 'print_error "Command failed at line $LINENO: $BASH_COMMAND"; exit 1' ERR

# ════════════════════════════════════════════════════════════════════════════════
# COLORS & FORMATTING
# ════════════════════════════════════════════════════════════════════════════════
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ════════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════════

print_header() {
    echo -e "\n${BLUE}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}${BOLD}  $1${NC}"
    echo -e "${BLUE}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

print_step() {
    echo -e "${CYAN}📌 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BOLD}ℹ️  $1${NC}"
}

# Time a command and print duration
time_command() {
    local start_time
    local end_time
    local duration
    start_time=$(date +%s)
    "$@"
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    echo -e "${YELLOW}⏱️  Duration: ${duration}s${NC}\n"
}

run_timed_step() {
    local title="$1"
    local success_message="$2"
    shift 2
    print_step "$title"
    time_command "$@"
    print_success "$success_message"
}

# Check if directory exists
check_dir() {
    if [ ! -d "$1" ]; then
        print_error "Directory not found: $1"
        exit 1
    fi
}

# Check if file exists
check_file() {
    if [ ! -f "$1" ]; then
        print_error "File not found: $1"
        exit 1
    fi
}

# ════════════════════════════════════════════════════════════════════════════════
# SETUP MODE
# ════════════════════════════════════════════════════════════════════════════════

setup_mode() {
    print_header "VIDYUT AI SETUP"
    
    # Parse flags
    local skip_rl=false
    for arg in "$@"; do
        if [ "$arg" = "--skip-rl" ]; then
            skip_rl=true
        fi
    done
    
    if [ "$skip_rl" = true ]; then
        print_warning "Skipping RL agent training (--skip-rl flag set)"
    fi
    
    # Step 1: Install backend dependencies
    check_dir "backend"
    check_file "backend/requirements.txt"
    run_timed_step "Installing backend dependencies..." \
        "Backend dependencies installed" \
        pip install -r backend/requirements.txt
    
    # Step 2: Install frontend dependencies
    check_dir "frontend"
    check_file "frontend/package.json"
    run_timed_step "Installing frontend dependencies..." \
        "Frontend dependencies installed" \
        bash -c "cd frontend && npm install"
    
    # Step 3: Generate synthetic data
    check_file "backend/scripts/generate_synthetic_data.py"
    run_timed_step "Generating synthetic data..." \
        "Synthetic data generated: feeder_load (8.7M rows), ev_sessions (450K rows)..." \
        python backend/scripts/generate_synthetic_data.py
    
    # Step 4: Feature engineering
    check_file "backend/scripts/feature_engineering.py"
    run_timed_step "Engineering features..." \
        "Features engineered: forecast_features.parquet (52 features)" \
        python backend/scripts/feature_engineering.py
    
    # Step 5: Train forecasting models
    check_file "backend/scripts/train_models.py"
    run_timed_step "Training forecasting models (6 zones × 3 models)..." \
        "Forecasting models trained: 18 total (6 zones × 3 models + ensemble)" \
        python backend/scripts/train_models.py --zone all --horizon all
    
    # Step 6: Train RL agent (optional)
    if [ "$skip_rl" = false ]; then
        check_file "backend/scripts/train_rl_agent.py"
        run_timed_step "Training RL agent (PPO, 200k steps)..." \
            "RL agent trained: PPO with 200k steps" \
            python backend/scripts/train_rl_agent.py --timesteps 200000
    else
        print_info "Skipping RL agent training"
    fi
    
    # Step 7: Score sites
    check_file "backend/scripts/site_scoring.py"
    run_timed_step "Scoring sites for solar feasibility..." \
        "Sites scored: 198 wards" \
        python backend/scripts/site_scoring.py
    
    # Step 8: Calculate carbon credits
    check_file "backend/scripts/carbon_credit_calc.py"
    run_timed_step "Computing carbon credit history..." \
        "Carbon history computed: 18 months" \
        python backend/scripts/carbon_credit_calc.py
    
    # Final summary
    print_header "VIDYUT AI SETUP COMPLETE"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}VIDYUT AI SETUP COMPLETE${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}Models trained: 18 (6 zones × 3 models + ensemble)${NC}"
    if [ "$skip_rl" = false ]; then
        echo -e "${GREEN}RL Agent: PPO (200k steps)${NC}"
    else
        echo -e "${YELLOW}RL Agent: skipped${NC}"
    fi
    echo -e "${GREEN}Sites scored: 198 wards${NC}"
    echo -e "${GREEN}Carbon history: 18 months${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${BOLD}Run:${NC} ${CYAN}./run_pipeline.sh start${NC}"
    echo ""
}

# ════════════════════════════════════════════════════════════════════════════════
# START MODE
# ════════════════════════════════════════════════════════════════════════════════

start_mode() {
    print_header "STARTING VIDYUT AI"
    
    check_dir "backend"
    check_dir "frontend"
    
    # Cleanup on exit
    cleanup() {
        print_warning "Stopping VIDYUT AI..."
        if [ -n "${BACKEND_PID:-}" ]; then
            kill $BACKEND_PID 2>/dev/null || true
        fi
        if [ -n "${FRONTEND_PID:-}" ]; then
            kill $FRONTEND_PID 2>/dev/null || true
        fi
        print_success "VIDYUT AI stopped"
        exit 0
    }
    
    trap cleanup SIGINT SIGTERM
    
    # Start backend
    print_step "Starting FastAPI backend (port 8000)..."
    (cd backend && uvicorn main:app --reload --port 8000 2>&1 | sed "s/^/${BLUE}[BACKEND]${NC} /" ) &
    BACKEND_PID=$!
    sleep 3
    
    # Check if backend started
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        print_error "Failed to start backend"
        exit 1
    fi
    print_success "Backend started (PID: $BACKEND_PID)"
    
    # Start frontend
    print_step "Starting React frontend (port 5173)..."
    (cd frontend && npm run dev 2>&1 | sed "s/^/${YELLOW}[FRONTEND]${NC} /" ) &
    FRONTEND_PID=$!
    sleep 5
    
    # Check if frontend started
    if ! kill -0 $FRONTEND_PID 2>/dev/null; then
        print_error "Failed to start frontend"
        kill $BACKEND_PID 2>/dev/null || true
        exit 1
    fi
    print_success "Frontend started (PID: $FRONTEND_PID)"
    
    # Print running info
    echo ""
    echo -e "${GREEN}VIDYUT AI running at http://localhost:5173 | API at http://localhost:8000/docs${NC}"
    print_info "Press Ctrl+C to stop"
    echo ""
    
    # Wait for processes
    wait
}

# ════════════════════════════════════════════════════════════════════════════════
# RETRAIN MODE
# ════════════════════════════════════════════════════════════════════════════════

retrain_mode() {
    print_header "RETRAINING MODELS"
    
    # Parse flags
    local skip_rl=false
    for arg in "$@"; do
        if [ "$arg" = "--skip-rl" ]; then
            skip_rl=true
        fi
    done
    
    # Step 1: Generate new data
    print_step "Generating fresh synthetic data..."
    check_file "backend/scripts/generate_synthetic_data.py"
    python backend/scripts/generate_synthetic_data.py
    print_success "Synthetic data refreshed"
    
    # Step 2: Feature engineering
    print_step "Re-engineering features..."
    check_file "backend/scripts/feature_engineering.py"
    python backend/scripts/feature_engineering.py
    print_success "Features re-engineered"
    
    # Step 3: Retrain models
    print_step "Retraining forecasting models..."
    check_file "backend/scripts/train_models.py"
    time_command python backend/scripts/train_models.py --zone all --horizon all
    print_success "Models retrained"
    
    # Step 4: Retrain RL agent (optional)
    if [ "$skip_rl" = false ]; then
        print_step "Retraining RL agent..."
        check_file "backend/scripts/train_rl_agent.py"
        time_command python backend/scripts/train_rl_agent.py --timesteps 200000
        print_success "RL agent retrained"
    fi
    
    print_header "RETRAINING COMPLETE"
    echo -e "${GREEN}Ready to run: ${BOLD}./run_pipeline.sh start${NC}"
    echo ""
}

# ════════════════════════════════════════════════════════════════════════════════
# DEMO MODE
# ════════════════════════════════════════════════════════════════════════════════

demo_mode() {
    # Detect OS and open browser
    open_browser() {
        local url="http://localhost:5173"
        if command -v xdg-open &> /dev/null; then
            # Linux
            xdg-open "$url" &
        elif command -v open &> /dev/null; then
            # macOS
            open "$url" &
        elif command -v cmd.exe &> /dev/null; then
            # Windows (Git Bash / WSL)
            cmd.exe /c start "" "$url"
        else
            print_warning "Could not automatically open browser. Visit: $url"
        fi
    }
    
    # Give backend time to start before opening browser
    print_step "Starting VIDYUT AI (will open browser in 8s)..."
    (
        sleep 8
        open_browser
    ) &
    
    # Start normally
    start_mode
}

# ════════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════════

main() {
    if [ $# -eq 0 ]; then
        print_error "No mode specified"
        echo ""
        echo "Usage:"
        echo "  ${BOLD}./run_pipeline.sh setup${NC}      Install deps, generate data, train models"
        echo "  ${BOLD}./run_pipeline.sh start${NC}      Start backend + frontend"
        echo "  ${BOLD}./run_pipeline.sh retrain${NC}    Retrain models with latest data"
        echo "  ${BOLD}./run_pipeline.sh demo${NC}       Start + open browser"
        echo ""
        echo "Flags:"
        echo "  ${BOLD}--skip-rl${NC}                    Skip RL agent training (faster setup)"
        echo ""
        exit 1
    fi
    
    local mode="$1"
    shift
    
    case "$mode" in
        setup)
            setup_mode "$@"
            ;;
        start)
            start_mode "$@"
            ;;
        retrain)
            retrain_mode "$@"
            ;;
        demo)
            demo_mode "$@"
            ;;
        *)
            print_error "Unknown mode: $mode"
            exit 1
            ;;
    esac
}

main "$@"
