#include "zombie/master.hpp"

#include <iostream>
#include <thread>
#include <chrono>
#include <cstring>
#include <ctime>
#include <openssl/hmac.h>
#include <openssl/sha.h>

// For sockets (POSIX)
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>

namespace nonail {

ZombieMaster::ZombieMaster(const std::string& password,
                           const std::string& host, int port)
    : password_(password), host_(host), port_(port)
{}

ZombieMaster::~ZombieMaster() {
    stop();
}

void ZombieMaster::stop() {
    running_ = false;
}

bool ZombieMaster::authenticate(const std::string& token) const {
    // HMAC-SHA256 verification
    unsigned char digest[SHA256_DIGEST_LENGTH];
    unsigned int len = 0;

    // Expected: HMAC(password, timestamp) where timestamp is within 60s
    // Simple protocol: token = "timestamp:hmac_hex"
    auto colon = token.find(':');
    if (colon == std::string::npos) return false;

    std::string ts_str = token.substr(0, colon);
    std::string provided_hmac = token.substr(colon + 1);

    // Check timestamp freshness (±60 seconds)
    long ts = std::stol(ts_str);
    long now = static_cast<long>(std::time(nullptr));
    if (std::abs(now - ts) > 60) return false;

    HMAC(EVP_sha256(),
         password_.data(), static_cast<int>(password_.size()),
         reinterpret_cast<const unsigned char*>(ts_str.data()),
         ts_str.size(), digest, &len);

    // Convert to hex
    char hex[SHA256_DIGEST_LENGTH * 2 + 1];
    for (unsigned i = 0; i < len; ++i)
        snprintf(hex + i * 2, 3, "%02x", digest[i]);
    hex[len * 2] = '\0';

    return std::string(hex) == provided_hmac;
}

std::vector<SlaveInfo> ZombieMaster::list_slaves() const {
    std::vector<SlaveInfo> result;
    for (auto& [id, info] : slaves_) {
        result.push_back(info);
    }
    return result;
}

std::string ZombieMaster::send_command(const std::string& slave_id, const std::string& command) {
    auto it = slaves_.find(slave_id);
    if (it == slaves_.end()) return "Slave not found: " + slave_id;

    // TODO: Send via WebSocket frame to slave
    // For now, store command in queue
    std::cout << "📤 Command to " << slave_id << ": " << command << "\n";
    return "Command queued for " + slave_id;
}

void ZombieMaster::broadcast(const std::string& command) {
    for (auto& [id, _] : slaves_) {
        send_command(id, command);
    }
}

void ZombieMaster::heartbeat_loop() {
    while (running_) {
        std::this_thread::sleep_for(std::chrono::seconds(30));
        auto now = static_cast<double>(std::time(nullptr));

        // Remove stale slaves (no heartbeat in 90s)
        for (auto it = slaves_.begin(); it != slaves_.end();) {
            if (now - it->second.last_seen > 90.0) {
                std::cout << "💀 Slave " << it->first << " timed out\n";
                it = slaves_.erase(it);
            } else {
                ++it;
            }
        }
    }
}

void ZombieMaster::run() {
    running_ = true;

    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) {
        std::cerr << "Failed to create socket\n";
        return;
    }

    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(static_cast<uint16_t>(port_));
    addr.sin_addr.s_addr = INADDR_ANY;

    if (bind(server_fd, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) < 0) {
        std::cerr << "Failed to bind on port " << port_ << "\n";
        close(server_fd);
        return;
    }

    listen(server_fd, 16);
    std::cout << "🧟 Zombie Master listening on " << host_ << ":" << port_ << "\n";

    // Start heartbeat thread
    std::thread hb(&ZombieMaster::heartbeat_loop, this);
    hb.detach();

    while (running_) {
        struct pollfd pfd{server_fd, POLLIN, 0};
        int ret = poll(&pfd, 1, 1000);  // 1s timeout
        if (ret <= 0) continue;

        struct sockaddr_in client_addr{};
        socklen_t client_len = sizeof(client_addr);
        int client_fd = accept(server_fd, reinterpret_cast<struct sockaddr*>(&client_addr), &client_len);
        if (client_fd < 0) continue;

        char ip[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &client_addr.sin_addr, ip, sizeof(ip));

        std::cout << "🔌 Connection from " << ip << "\n";

        // Read auth token (first line)
        char buf[1024];
        ssize_t n = recv(client_fd, buf, sizeof(buf) - 1, 0);
        if (n <= 0) { close(client_fd); continue; }
        buf[n] = '\0';

        std::string token(buf);
        // Trim newline
        while (!token.empty() && (token.back() == '\n' || token.back() == '\r'))
            token.pop_back();

        if (!authenticate(token)) {
            std::cout << "❌ Auth failed from " << ip << "\n";
            send(client_fd, "AUTH_FAIL\n", 10, 0);
            close(client_fd);
            continue;
        }

        // Read slave ID
        n = recv(client_fd, buf, sizeof(buf) - 1, 0);
        if (n <= 0) { close(client_fd); continue; }
        buf[n] = '\0';
        std::string slave_id(buf);
        while (!slave_id.empty() && (slave_id.back() == '\n' || slave_id.back() == '\r'))
            slave_id.pop_back();

        send(client_fd, "AUTH_OK\n", 8, 0);

        SlaveInfo info;
        info.id = slave_id;
        info.ip = ip;
        info.status = "connected";
        info.last_seen = static_cast<double>(std::time(nullptr));
        slaves_[slave_id] = info;

        std::cout << "✅ Slave registered: " << slave_id << " (" << ip << ")\n";

        // TODO: Handle ongoing communication in a separate thread
        // For now, close after registration
        close(client_fd);
    }

    close(server_fd);
}

} // namespace nonail
