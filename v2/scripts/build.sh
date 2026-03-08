#!/bin/bash
# Build NoNail v2 (native development build)
set -e

cd "$(dirname "$0")/.."

echo "🔨 Building NoNail v2 (C++ Edition)..."

# Install dependencies if on Debian/Ubuntu
if command -v apt-get &>/dev/null; then
    echo "📦 Checking build dependencies..."
    sudo apt-get install -y -qq cmake g++ libcurl4-openssl-dev libsqlite3-dev libssl-dev 2>/dev/null || true
fi

# Configure
cmake -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DNONAIL_BUILD_TESTS=ON \
    -DNONAIL_BUILD_WEB=ON \
    -DNONAIL_BUILD_ZOMBIE=ON \
    -DNONAIL_BUILD_DEVICES=ON

# Build
cmake --build build -j$(nproc)

echo ""
echo "✅ Build complete!"
echo "   Binary:  build/nonail"
echo "   Tests:   build/nonail-tests"
echo ""

# Run tests
echo "🧪 Running tests..."
cd build && ctest --output-on-failure && cd ..

echo ""
echo "📊 Binary size:"
ls -lh build/nonail

echo ""
echo "Run with: ./build/nonail --help"
