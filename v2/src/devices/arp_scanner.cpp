#include "devices/device_manager.hpp"

#include <fstream>
#include <sstream>
#include <cstring>
#include <ctime>
#include <cstdio>
#include <array>

// For ping
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>

namespace nonail {

DeviceManager::DeviceManager() {
    refresh_arp();
}

DeviceManager::~DeviceManager() = default;

void DeviceManager::parse_arp_table() {
    std::ifstream ifs("/proc/net/arp");
    if (!ifs.good()) return;

    std::string line;
    std::getline(ifs, line);  // skip header

    while (std::getline(ifs, line)) {
        std::istringstream iss(line);
        std::string ip, hw_type, flags, mac, mask, iface;
        iss >> ip >> hw_type >> flags >> mac >> mask >> iface;

        if (ip.empty() || mac.empty() || mac == "00:00:00:00:00:00") continue;

        DeviceInfo info;
        info.ip = ip;
        info.mac = mac;
        info.interface = iface;
        info.last_seen = static_cast<double>(std::time(nullptr));
        info.reachable = (flags != "0x0");  // 0x0 = incomplete

        // Try to resolve hostname
        char buf[256];
        std::string cmd = "getent hosts " + ip + " 2>/dev/null | awk '{print $2}'";
        FILE* pipe = popen(cmd.c_str(), "r");
        if (pipe) {
            if (fgets(buf, sizeof(buf), pipe)) {
                info.hostname = buf;
                while (!info.hostname.empty() &&
                       (info.hostname.back() == '\n' || info.hostname.back() == '\r'))
                    info.hostname.pop_back();
            }
            pclose(pipe);
        }

        devices_[ip] = info;
    }
}

void DeviceManager::refresh_arp() {
    devices_.clear();
    parse_arp_table();
    last_scan_ = static_cast<double>(std::time(nullptr));
}

std::vector<DeviceInfo> DeviceManager::scan() {
    double now = static_cast<double>(std::time(nullptr));
    if (now - last_scan_ > cache_ttl_) {
        refresh_arp();
    }

    std::vector<DeviceInfo> result;
    result.reserve(devices_.size());
    for (auto& [_, info] : devices_) {
        result.push_back(info);
    }
    return result;
}

DeviceInfo DeviceManager::get_device(const std::string& ip) const {
    auto it = devices_.find(ip);
    if (it != devices_.end()) return it->second;
    return DeviceInfo{ip, "", "", "", false, 0.0};
}

bool DeviceManager::ping(const std::string& ip, int timeout_ms) const {
    std::string cmd = "ping -c 1 -W " + std::to_string(timeout_ms / 1000 + 1) +
                      " " + ip + " >/dev/null 2>&1";
    return system(cmd.c_str()) == 0;
}

std::string DeviceManager::ssh_exec(const std::string& ip,
                                     const std::string& command,
                                     const std::string& user,
                                     int port) {
#ifdef NONAIL_HAS_SSH
    // libssh2 implementation would go here
    // For now, fall back to system ssh
#endif
    std::string cmd = "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -p " +
        std::to_string(port) + " " + user + "@" + ip + " " +
        "'" + command + "' 2>&1";

    std::array<char, 4096> buf;
    std::string output;
    FILE* pipe = popen(cmd.c_str(), "r");
    if (!pipe) return "Failed to execute SSH";

    while (fgets(buf.data(), buf.size(), pipe)) {
        output += buf.data();
    }
    pclose(pipe);
    return output;
}

nlohmann::json DeviceManager::to_json() const {
    nlohmann::json arr = nlohmann::json::array();
    for (auto& [ip, d] : devices_) {
        arr.push_back({
            {"ip", d.ip},
            {"mac", d.mac},
            {"hostname", d.hostname},
            {"interface", d.interface},
            {"reachable", d.reachable},
            {"last_seen", d.last_seen}
        });
    }
    return arr;
}

} // namespace nonail
