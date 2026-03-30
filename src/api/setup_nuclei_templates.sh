#!/bin/bash

# Setup script for nuclei templates repository
# This script ensures the nuclei templates repository is available for the API

set -e

echo "🔧 Setting up Nuclei Templates Repository"
echo "=========================================="

# Configuration
NUCLEI_REPO_URL="https://github.com/projectdiscovery/nuclei-templates.git"
NUCLEI_REPO_PATH="/opt/nuclei-templates"
NUCLEI_REPO_BRANCH="main"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if git is available
if ! command -v git &> /dev/null; then
    print_error "Git is not installed. Please install git first."
    exit 1
fi

# Check if we have write permissions to /opt
if [ ! -w "/opt" ]; then
    print_error "No write permission to /opt directory"
    exit 1
fi

# Function to clone repository
clone_repository() {
    print_status "Cloning nuclei templates repository..."
    
    if [ -d "$NUCLEI_REPO_PATH" ]; then
        print_warning "Repository already exists at $NUCLEI_REPO_PATH"
        print_status "Removing existing repository..."
        rm -rf "$NUCLEI_REPO_PATH"
    fi
    
    git clone --depth 1 --branch "$NUCLEI_REPO_BRANCH" "$NUCLEI_REPO_URL" "$NUCLEI_REPO_PATH"
    
    if [ $? -eq 0 ]; then
        print_status "Repository cloned successfully"
    else
        print_error "Failed to clone repository"
        exit 1
    fi
}

# Function to update repository
update_repository() {
    if [ ! -d "$NUCLEI_REPO_PATH" ]; then
        print_warning "Repository not found, cloning..."
        clone_repository
        return
    fi
    
    print_status "Updating nuclei templates repository..."
    
    cd "$NUCLEI_REPO_PATH"
    
    # Fetch latest changes
    git fetch origin
    
    # Reset to latest
    git reset --hard "origin/$NUCLEI_REPO_BRANCH"
    
    if [ $? -eq 0 ]; then
        print_status "Repository updated successfully"
    else
        print_error "Failed to update repository"
        exit 1
    fi
}

# Function to generate tree JSON
generate_tree_json() {
    print_status "Generating nuclei templates tree JSON..."
    
    if [ ! -d "$NUCLEI_REPO_PATH" ]; then
        print_error "Repository not found, cannot generate tree"
        return 1
    fi
    
    # Check if Python is available
    if ! command -v python3 &> /dev/null; then
        print_error "Python3 is not installed. Cannot generate tree JSON."
        return 1
    fi
    
    # Check if PyYAML is available
    if ! python3 -c "import yaml" &> /dev/null; then
        print_error "PyYAML is not installed. Installing..."
        pip3 install PyYAML
        if [ $? -ne 0 ]; then
            print_error "Failed to install PyYAML"
            return 1
        fi
    fi
    
    # Run the tree generation script
    cd "$(dirname "$0")"
    if [ -f "generate_nuclei_tree.py" ]; then
        python3 generate_nuclei_tree.py
        if [ $? -eq 0 ]; then
            print_status "Tree JSON generated successfully"
            
            # Check file size
            if [ -f "/opt/nuclei-templates-tree.json" ]; then
                FILE_SIZE=$(stat -c%s "/opt/nuclei-templates-tree.json")
                print_status "Tree JSON file size: $FILE_SIZE bytes"
            fi
        else
            print_error "Failed to generate tree JSON"
            return 1
        fi
    else
        print_error "Tree generation script not found"
        return 1
    fi
    
    return 0
}

# Function to check repository status
check_repository() {
    if [ ! -d "$NUCLEI_REPO_PATH" ]; then
        print_warning "Repository not found"
        return 1
    fi
    
    cd "$NUCLEI_REPO_PATH"
    
    # Check if it's a git repository
    if [ ! -d ".git" ]; then
        print_warning "Not a git repository"
        return 1
    fi
    
    # Get last commit info
    LAST_COMMIT=$(git log -1 --format="%cd" --date=iso 2>/dev/null)
    if [ $? -eq 0 ]; then
        print_status "Repository last updated: $LAST_COMMIT"
    else
        print_warning "Could not get last commit info"
    fi
    
    # Count templates
    TEMPLATE_COUNT=$(find . -name "*.yaml" | wc -l)
    print_status "Found $TEMPLATE_COUNT template files"
    
    # List categories
    CATEGORIES=$(find . -maxdepth 1 -type d -not -name "." -not -name ".git" | sed 's|./||' | sort)
    print_status "Available categories:"
    echo "$CATEGORIES" | while read category; do
        if [ -n "$category" ]; then
            CATEGORY_COUNT=$(find "./$category" -name "*.yaml" | wc -l)
            echo "  - $category ($CATEGORY_COUNT templates)"
        fi
    done
    
    # Check if tree JSON exists
    if [ -f "/opt/nuclei-templates-tree.json" ]; then
        TREE_SIZE=$(stat -c%s "/opt/nuclei-templates-tree.json")
        print_status "Tree JSON file exists: $TREE_SIZE bytes"
    else
        print_warning "Tree JSON file not found"
    fi
    
    return 0
}

# Main execution
case "${1:-setup}" in
    "setup")
        print_status "Setting up nuclei templates repository..."
        clone_repository
        generate_tree_json
        check_repository
        ;;
    "update")
        print_status "Updating nuclei templates repository..."
        update_repository
        generate_tree_json
        check_repository
        ;;
    "check")
        print_status "Checking nuclei templates repository..."
        check_repository
        ;;
    "generate-tree")
        print_status "Generating nuclei templates tree JSON..."
        generate_tree_json
        ;;
    "clean")
        print_status "Cleaning nuclei templates repository..."
        if [ -d "$NUCLEI_REPO_PATH" ]; then
            rm -rf "$NUCLEI_REPO_PATH"
            print_status "Repository removed"
        else
            print_warning "Repository not found"
        fi
        
        # Also remove tree JSON file
        if [ -f "/opt/nuclei-templates-tree.json" ]; then
            rm -f "/opt/nuclei-templates-tree.json"
            print_status "Tree JSON file removed"
        fi
        ;;
    *)
        echo "Usage: $0 {setup|update|check|generate-tree|clean}"
        echo ""
        echo "Commands:"
        echo "  setup        - Clone the nuclei templates repository and generate tree (default)"
        echo "  update       - Update the existing repository and regenerate tree"
        echo "  check        - Check repository status and list categories"
        echo "  generate-tree - Generate tree JSON file only"
        echo "  clean        - Remove the repository and tree JSON file"
        exit 1
        ;;
esac

print_status "Setup completed successfully!" 