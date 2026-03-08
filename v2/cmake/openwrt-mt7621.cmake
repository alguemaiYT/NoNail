# OpenWrt cross-compilation toolchain for ramips/mt7621 (MIPS)
#
# Usage:
#   cmake -B build-openwrt \
#       -DCMAKE_TOOLCHAIN_FILE=cmake/openwrt-mt7621.cmake \
#       -DCMAKE_BUILD_TYPE=MinSizeRel \
#       -DNONAIL_CROSS_COMPILE=ON
#
# Prerequisites:
#   Download OpenWrt SDK from https://downloads.openwrt.org/
#   Set OPENWRT_SDK to the SDK root directory

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR mipsel)

# Adjust this to your OpenWrt SDK location
if(NOT DEFINED ENV{OPENWRT_SDK})
    message(FATAL_ERROR "Set OPENWRT_SDK env var to your OpenWrt SDK root")
endif()

set(OPENWRT_SDK $ENV{OPENWRT_SDK})
set(TOOLCHAIN_PREFIX mipsel-openwrt-linux-musl-)

set(CMAKE_C_COMPILER   ${OPENWRT_SDK}/staging_dir/toolchain-mipsel_24kc_gcc-*/bin/${TOOLCHAIN_PREFIX}gcc)
set(CMAKE_CXX_COMPILER ${OPENWRT_SDK}/staging_dir/toolchain-mipsel_24kc_gcc-*/bin/${TOOLCHAIN_PREFIX}g++)
set(CMAKE_STRIP         ${OPENWRT_SDK}/staging_dir/toolchain-mipsel_24kc_gcc-*/bin/${TOOLCHAIN_PREFIX}strip)

set(CMAKE_SYSROOT ${OPENWRT_SDK}/staging_dir/target-mipsel_24kc_musl/)

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)

# Optimize for size
set(CMAKE_C_FLAGS   "-Os -pipe -mno-branch-likely -mips32r2 -mtune=24kc" CACHE STRING "")
set(CMAKE_CXX_FLAGS "-Os -pipe -mno-branch-likely -mips32r2 -mtune=24kc -fno-exceptions -fno-rtti" CACHE STRING "")
set(CMAKE_EXE_LINKER_FLAGS "-s -static-libstdc++ -static-libgcc" CACHE STRING "")
