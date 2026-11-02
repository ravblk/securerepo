#!/bin/bash

# Script to build all service Docker images for Kubernetes deployment
#
# Usage:
#   ./scripts/build-images.sh [tag]              — native build (Mac / local arch)
#   ./scripts/build-images.sh [tag] linux/amd64  — cross-build via buildx + --load (tag becomes [tag]-linux-amd64)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

IMAGE_TAG=${1:-latest}
BUILD_PLATFORM=${2:-}

# Cross-build tags include platform (e.g. v0.2.1 + linux/amd64 → v0.2.1-linux-amd64)
if [ -n "${BUILD_PLATFORM}" ]; then
    PLATFORM_SUFFIX="${BUILD_PLATFORM//\//-}"
    EFFECTIVE_TAG="${IMAGE_TAG}-${PLATFORM_SUFFIX}"
else
    EFFECTIVE_TAG="${IMAGE_TAG}"
fi

echo -e "${GREEN}Building SecureRepo Docker images for Kubernetes deployment${NC}"
echo -e "${GREEN}Using tag: ${EFFECTIVE_TAG}${NC}"
if [ -n "${BUILD_PLATFORM}" ]; then
    echo -e "${GREEN}Platform: ${BUILD_PLATFORM} (docker buildx --load)${NC}"
else
    echo -e "${GREEN}Platform: native (docker build)${NC}"
fi
echo ""

# Check if running in correct directory
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}Error: run this script from the project root directory${NC}"
    exit 1
fi

# Function to build an image
build_image() {
    local service=$1
    local image_name=$2
    local tag=$3

    echo -e "${YELLOW}Building ${service}...${NC}"
    if [ -n "${BUILD_PLATFORM}" ]; then
        if docker buildx build --platform "${BUILD_PLATFORM}" --load \
            -t "${image_name}:${tag}" "./services/${service}" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ ${service} built successfully with tag ${tag}${NC}"
        else
            echo -e "${RED}✗ ${service} build failed${NC}"
            exit 1
        fi
    else
        if docker build -t "${image_name}:${tag}" "./services/${service}" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ ${service} built successfully with tag ${tag}${NC}"
        else
            echo -e "${RED}✗ ${service} build failed${NC}"
            exit 1
        fi
    fi
}

# Build all service images
build_image "embedding-service" "xravil/securerepo-embedding-service" "${EFFECTIVE_TAG}"
build_image "api-service" "xravil/securerepo-api-service" "${EFFECTIVE_TAG}"
build_image "frontend-service" "xravil/securerepo-frontend-service" "${EFFECTIVE_TAG}"
build_image "internal-rules-ingestion" "xravil/securerepo-internal-rules-ingestion" "${EFFECTIVE_TAG}"
build_image "indexer-service" "xravil/securerepo-indexer-service" "${EFFECTIVE_TAG}"
build_image "audit-worker" "xravil/securerepo-audit-worker" "${EFFECTIVE_TAG}"

echo ""
echo -e "${GREEN}All images built successfully!${NC}"
echo ""
echo "Built images:"
echo "  xravil/securerepo-embedding-service:${EFFECTIVE_TAG}"
echo "  xravil/securerepo-api-service:${EFFECTIVE_TAG}"
echo "  xravil/securerepo-frontend-service:${EFFECTIVE_TAG}"
echo "  xravil/securerepo-internal-rules-ingestion:${EFFECTIVE_TAG}"
echo "  xravil/securerepo-indexer-service:${EFFECTIVE_TAG}"
echo "  xravil/securerepo-audit-worker:${EFFECTIVE_TAG}"
echo ""
echo "To tag for your registry, run:"
echo "  docker tag xravil/securerepo-<service>:${EFFECTIVE_TAG} your-registry.com/xravil/securerepo-<service>:${EFFECTIVE_TAG}"
echo ""
echo "To push to repository:"
echo "  docker push your-registry.com/xravil/securerepo-<service>:${EFFECTIVE_TAG}"
