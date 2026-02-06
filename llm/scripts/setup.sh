#!/bin/bash

# GeoDataAnalytics Setup Script
# This script sets up the development environment

set -e  # Exit on any error

echo "🚀 Setting up GeoDataAnalytics development environment..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    print_success "Docker and Docker Compose are installed"
}

# Check if Python is installed
check_python() {
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed. Please install Python 3.8+ first."
        exit 1
    fi
    
    python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    print_success "Python $python_version is installed"
}

# Create environment file
setup_env() {
    if [ ! -f .env ]; then
        print_status "Creating .env file from template..."
        cp .env.example .env
        print_success ".env file created. Please update it with your configuration."
    else
        print_warning ".env file already exists. Skipping creation."
    fi
}

# Create necessary directories
create_directories() {
    print_status "Creating necessary directories..."
    
    directories=(
        "data/fixtures"
        "data/samples"
        "data/external"
        "reports/html"
        "reports/json"
        "reports/logs"
        "docs/api"
        "docs/deployment"
        "docs/user_guide"
        "logs"
        "backups"
        "temp"
    )
    
    for dir in "${directories[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            print_status "Created directory: $dir"
        fi
    done
    
    print_success "All directories created"
}

# Install Python dependencies
install_python_deps() {
    print_status "Installing Python dependencies..."
    
    if [ -f "python/requirements.txt" ]; then
        pip3 install -r python/requirements.txt
        print_success "Python dependencies installed"
    else
        print_warning "python/requirements.txt not found. Skipping Python dependencies."
    fi
}

# Build and start Docker containers
setup_docker() {
    print_status "Building and starting Docker containers..."
    
    # Build the PostgreSQL image
    docker-compose build postgres
    
    # Start the services
    docker-compose up -d
    
    print_success "Docker containers are starting up"
    
    # Wait for PostgreSQL to be ready
    print_status "Waiting for PostgreSQL to be ready..."
    sleep 10
    
    # Check if PostgreSQL is ready
    max_attempts=30
    attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if docker-compose exec -T postgres pg_isready -U postgres -d geodata_analytics; then
            print_success "PostgreSQL is ready!"
            break
        fi
        
        print_status "Attempt $attempt/$max_attempts: PostgreSQL not ready yet..."
        sleep 2
        ((attempt++))
    done
    
    if [ $attempt -gt $max_attempts ]; then
        print_error "PostgreSQL failed to start within expected time."
        exit 1
    fi
}

# Initialize database schema
init_database() {
    print_status "Initializing database schema..."
    
    # The schema should be automatically initialized by the init.sql script
    # But we can run additional setup if needed
    
    print_success "Database schema initialized"
}

# Run initial tests
run_tests() {
    print_status "Running initial tests to verify setup..."
    
    if [ -f "python/test_runner.py" ]; then
        python3 python/test_runner.py --connection "postgresql://postgres:postgres@localhost:5432/geodata_analytics" --category FLOOD --verbose
        print_success "Initial tests completed"
    else
        print_warning "test_runner.py not found. Skipping initial tests."
    fi
}

# Display setup summary
display_summary() {
    echo ""
    echo "🎉 GeoDataAnalytics setup completed successfully!"
    echo ""
    echo "📋 Next steps:"
    echo "1. Review and update the .env file with your configuration"
    echo "2. Start the development environment: docker-compose up -d"
    echo "3. Access the services:"
    echo "   - PostgreSQL: localhost:5432"
    echo "   - Redis: localhost:6379"
    echo "   - MinIO: http://localhost:9000 (admin/minioadmin)"
    echo "   - Jupyter: http://localhost:8888 (token: geodata)"
    echo "4. Run tests: python3 python/test_runner.py --help"
    echo ""
    echo "📚 Documentation:"
    echo " - README.md: Project overview and usage"
    echo " - setup_tasks.md: Detailed setup tasks and directory structure"
    echo " - docs/: Additional documentation"
    echo ""
    echo "🐳 Docker commands:"
    echo " - View logs: docker-compose logs -f"
    echo " - Stop services: docker-compose down"
    echo " - Restart services: docker-compose restart"
    echo ""
}

# Main setup function
main() {
    echo "GeoDataAnalytics Setup Script"
    echo "============================="
    echo ""
    
    check_docker
    check_python
    setup_env
    create_directories
    install_python_deps
    setup_docker
    init_database
    run_tests
    display_summary
}

# Handle script interruption
trap 'print_error "Setup interrupted. Cleaning up..."; docker-compose down; exit 1' INT

# Run main function
main "$@"