#pragma once

#include <string>
#include <vector>
#include <map>
#include <nlohmann/json.hpp>

namespace nonail {

struct DeviceInfo {
    std::string ip;
    std::string mac;
    std::string hostname;
    std::string interface;
    bool reachable = false;
    double last_seen = 0.0;
};

class DeviceManager {
public:
    DeviceManager();
    ~DeviceManager();

    // Scan local network using ARP table
    std::vector<DeviceInfo> scan();

    // Refresh from /proc/net/arp
    void refresh_arp();

    // Execute command on device via SSH
    std::string ssh_exec(const std::string& ip,
                         const std::string& command,
                         const std::string& user = "root",
                         int port = 22);

    // Get device info
    DeviceInfo get_device(const std::string& ip) const;

    // Ping a device
    bool ping(const std::string& ip, int timeout_ms = 1000) const;

    nlohmann::json to_json() const;

private:
    std::map<std::string, DeviceInfo> devices_;
    double cache_ttl_ = 300.0;  // 5 minutes
    double last_scan_ = 0.0;

    void parse_arp_table();
};

} // namespace nonail
