# NoNail v2 — C++ Edition

Lightweight AI agent for OpenWrt routers and embedded Linux devices.

## Features
- **Chat / Run**: Talk to OpenAI or Anthropic models via CLI or Web UI
- **Web UI**: Responsive single-page app served from the router
- **Zombie Mode**: Master/slave control via WebSocket + Telegram/Discord/WhatsApp
- **Device Control**: Discover and manage devices on your LAN (ARP, SSH, SNMP)

## Build

### Native (development)
```bash
cd v2
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)
./build/nonail --help
```

### Cross-compile for OpenWrt (ramips/mt7621)
```bash
# Source OpenWrt SDK environment
source /path/to/openwrt/sdk/environment-setup-*
cmake -B build-openwrt \
    -DCMAKE_BUILD_TYPE=MinSizeRel \
    -DNONAIL_CROSS_COMPILE=ON \
    -DCMAKE_TOOLCHAIN_FILE=cmake/openwrt-mt7621.cmake
cmake --build build-openwrt -j$(nproc)
cmake --build build-openwrt --target strip-binary
```

### Dependencies
| Library | Purpose | Size |
|---------|---------|------|
| nlohmann/json | JSON parsing | ~50 KB |
| cpp-httplib | HTTP server + client | ~50 KB |
| libcurl | HTTP client (providers) | ~500 KB |
| SQLite3 | Cache + state | ~400 KB |
| OpenSSL | TLS | system |

## Configuration
```json
{
  "provider": "openai",
  "model": "gpt-4o",
  "api_key": "sk-...",
  "web": { "port": 8080, "enabled": true },
  "zombie": { "enabled": false, "port": 8765 }
}
```
Config file: `~/.nonail/config.json`

## Usage
```bash
# Interactive chat
nonail chat

# Single prompt
nonail run "explain DNS"

# Start web UI
nonail web --port 8080

# Zombie master
nonail zombie master --port 8765 --password secret

# Zombie slave
nonail zombie slave --host 192.168.1.1 --port 8765 --password secret

# Complex system task
nonail zombie task [--slave-id ID] [--wait SECONDS]

# Scan devices
nonail devices scan
```

## Complex zombie slave task

The `nonail zombie task` command temporarily spawns a master on the configured zombie port, waits for a slave (or the slave specified with `--slave-id`), and runs a scripted system analysis job. It sequentially executes the following commands on the slave and prints the aggregated output:

1. `uname -a` — kernel and build information
2. `uptime` — system uptime and load averages
3. `cat /proc/cpuinfo | head -n 20` — abbreviated CPU description
4. `cat /proc/meminfo` — current memory figures
5. `df -h` — human-readable disk usage
6. `lsblk` — block device topology
7. `ip address` — interface addresses
8. `ip route` — routing table
9. `ss -tuln` — listening sockets
10. `ps -eo pid,cmd,%cpu,%mem --sort=-%cpu | head -n 10` — hottest processes
11. `dmesg | tail -n 20` — recent kernel log lines
12. `cat /proc/sys/kernel/random/entropy_avail` — entropy pool depth

The task gives the AI-rich slave output for verification and proves that the zombie channel can deliver complex, multi-command payloads.

## License
MIT
