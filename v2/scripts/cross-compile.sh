#!/bin/bash
# Cross-compile NoNail v2 for OpenWrt ramips/mt7621
set -e

cd "$(dirname "$0")/.."

if [ -z "$OPENWRT_SDK" ]; then
    echo "❌ Set OPENWRT_SDK to your OpenWrt SDK root directory"
    echo "   export OPENWRT_SDK=/path/to/openwrt-sdk-ramips-mt7621_..."
    exit 1
fi

echo "🔨 Cross-compiling for OpenWrt (ramips/mt7621)..."

cmake -B build-openwrt \
    -DCMAKE_TOOLCHAIN_FILE=cmake/openwrt-mt7621.cmake \
    -DCMAKE_BUILD_TYPE=MinSizeRel \
    -DNONAIL_CROSS_COMPILE=ON \
    -DNONAIL_BUILD_TESTS=OFF \
    -DNONAIL_BUILD_WEB=ON \
    -DNONAIL_BUILD_ZOMBIE=ON \
    -DNONAIL_BUILD_DEVICES=ON

cmake --build build-openwrt -j$(nproc)
cmake --build build-openwrt --target strip-binary

echo ""
echo "✅ Cross-compile complete!"
echo "   Binary: build-openwrt/nonail"
echo ""
echo "📊 Binary size (stripped):"
ls -lh build-openwrt/nonail
echo ""
echo "Deploy: scp build-openwrt/nonail root@192.168.1.1:/usr/bin/"
