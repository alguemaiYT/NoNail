cmake_minimum_required(VERSION 3.14)
project(nonail VERSION 0.2.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------
option(NONAIL_BUILD_TESTS   "Build unit tests"              ON)
option(NONAIL_BUILD_WEB     "Build embedded web UI"         ON)
option(NONAIL_BUILD_ZOMBIE  "Build zombie master/slave"     ON)
option(NONAIL_BUILD_DEVICES "Build device control module"   ON)
option(NONAIL_CROSS_COMPILE "Enable OpenWrt cross-compile"  OFF)

# ---------------------------------------------------------------------------
# Dependencies — header-only vendored in third_party/
# ---------------------------------------------------------------------------
# nlohmann/json  — single-header JSON library
# cpp-httplib    — single-header HTTP server/client
# Both fetched via FetchContent if not present.

include(FetchContent)

FetchContent_Declare(json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG        v3.11.3
    GIT_SHALLOW    TRUE
)
FetchContent_Declare(httplib
    GIT_REPOSITORY https://github.com/yhirose/cpp-httplib.git
    GIT_TAG        v0.18.3
    GIT_SHALLOW    TRUE
)

FetchContent_MakeAvailable(json httplib)

# System dependencies
find_package(CURL REQUIRED)
find_package(SQLite3 REQUIRED)
find_package(OpenSSL REQUIRED)

# ---------------------------------------------------------------------------
# Core library (agent + config + providers)
# ---------------------------------------------------------------------------
add_library(nonail-core STATIC
    src/core/config.cpp
    src/core/agent.cpp
    src/core/cache.cpp
    src/core/http_client.cpp
    src/providers/openai.cpp
    src/providers/anthropic.cpp
    src/providers/provider.cpp
    src/tools/tool_registry.cpp
    src/tools/shell_tool.cpp
    src/organizer/system_organizer.cpp
)
target_include_directories(nonail-core PUBLIC include)
target_link_libraries(nonail-core PUBLIC
    nlohmann_json::nlohmann_json
    CURL::libcurl
    SQLite::SQLite3
    OpenSSL::SSL
    OpenSSL::Crypto
)

# ---------------------------------------------------------------------------
# CLI executable
# ---------------------------------------------------------------------------
add_executable(nonail src/main.cpp)
target_link_libraries(nonail PRIVATE nonail-core)

# ---------------------------------------------------------------------------
# Web UI module
# ---------------------------------------------------------------------------
if(NONAIL_BUILD_WEB)
    add_library(nonail-web STATIC
        src/web/server.cpp
        src/web/api_routes.cpp
        src/web/ws_handler.cpp
    )
    target_include_directories(nonail-web PUBLIC include)
    target_link_libraries(nonail-web PUBLIC nonail-core httplib::httplib)
    target_link_libraries(nonail PRIVATE nonail-web)
    target_compile_definitions(nonail PRIVATE NONAIL_WEB=1)
endif()

# ---------------------------------------------------------------------------
# Zombie mode
# ---------------------------------------------------------------------------
if(NONAIL_BUILD_ZOMBIE)
    add_library(nonail-zombie STATIC
        src/zombie/master.cpp
        src/zombie/slave.cpp
        src/zombie/protocol.cpp
        src/zombie/messaging/telegram.cpp
        src/zombie/messaging/discord.cpp
        src/zombie/messaging/whatsapp.cpp
    )
    target_include_directories(nonail-zombie PUBLIC include)
    target_link_libraries(nonail-zombie PUBLIC nonail-core)
    target_link_libraries(nonail PRIVATE nonail-zombie)
    target_compile_definitions(nonail PRIVATE NONAIL_ZOMBIE=1)
endif()

# ---------------------------------------------------------------------------
# Device control
# ---------------------------------------------------------------------------
if(NONAIL_BUILD_DEVICES)
    add_library(nonail-devices STATIC
        src/devices/arp_scanner.cpp
        src/devices/ssh_executor.cpp
        src/devices/device_manager.cpp
    )
    target_include_directories(nonail-devices PUBLIC include)
    target_link_libraries(nonail-devices PUBLIC nonail-core)
    # libssh2 is optional — gracefully degrade if missing
    find_package(PkgConfig QUIET)
    if(PkgConfig_FOUND)
        pkg_check_modules(LIBSSH2 libssh2)
        if(LIBSSH2_FOUND)
            target_link_libraries(nonail-devices PUBLIC ${LIBSSH2_LIBRARIES})
            target_include_directories(nonail-devices PUBLIC ${LIBSSH2_INCLUDE_DIRS})
            target_compile_definitions(nonail-devices PUBLIC NONAIL_HAS_SSH=1)
        endif()
    endif()
    target_link_libraries(nonail PRIVATE nonail-devices)
    target_compile_definitions(nonail PRIVATE NONAIL_DEVICES=1)
endif()

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
if(NONAIL_BUILD_TESTS)
    enable_testing()
    FetchContent_Declare(googletest
        GIT_REPOSITORY https://github.com/google/googletest.git
        GIT_TAG        v1.14.0
        GIT_SHALLOW    TRUE
    )
    FetchContent_MakeAvailable(googletest)

    add_executable(nonail-tests
        tests/test_config.cpp
        tests/test_providers.cpp
        tests/test_agent.cpp
        tests/test_cache.cpp
    )
    target_link_libraries(nonail-tests PRIVATE nonail-core GTest::gtest_main)
    include(GoogleTest)
    gtest_discover_tests(nonail-tests)
endif()

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
install(TARGETS nonail RUNTIME DESTINATION bin)
if(EXISTS "${CMAKE_SOURCE_DIR}/assets")
    install(DIRECTORY assets/ DESTINATION share/nonail/assets)
endif()

# ---------------------------------------------------------------------------
# Strip target for embedded (manual)
# ---------------------------------------------------------------------------
add_custom_target(strip-binary
    COMMAND ${CMAKE_STRIP} $<TARGET_FILE:nonail>
    DEPENDS nonail
    COMMENT "Stripping nonail binary for embedded deployment"
)
