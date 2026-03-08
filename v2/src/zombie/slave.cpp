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
#include <netdb.h>
#include <unistd.h>

namespace nonail {

ZombieSlave::ZombieSlave(const std::string& master_host, int master_port,
                         const std::string& password, const std::string& slave_id)
    : master_host_(master_host)
    , master_port_(master_port)
    , password_(password)
    , slave_id_(slave_id)
{
    if (slave_id_.empty()) {
        char hostname[256];
        gethostname(hostname, sizeof(hostname));
        slave_id_ = hostname;
    }
}

ZombieSlave::~ZombieSlave() {
    stop();
}

void ZombieSlave::stop() {
    running_ = false;
}

std::string ZombieSlave::generate_auth_token() const {
    auto now = std::to_string(std::time(nullptr));

    unsigned char digest[SHA256_DIGEST_LENGTH];
    unsigned int len = 0;
    HMAC(EVP_sha256(),
         password_.data(), static_cast<int>(password_.size()),
         reinterpret_cast<const unsigned char*>(now.data()),
         now.size(), digest, &len);

    char hex[SHA256_DIGEST_LENGTH * 2 + 1];
    for (unsigned i = 0; i < len; ++i)
        snprintf(hex + i * 2, 3, "%02x", digest[i]);
    hex[len * 2] = '\0';

    return now + ":" + std::string(hex);
}

std::string ZombieSlave::execute_command(const std::string& command) {
    // Execute locally and return output
    FILE* pipe = popen(command.c_str(), "r");
    if (!pipe) return "Failed to execute: " + command;

    char buf[4096];
    std::string output;
    while (fgets(buf, sizeof(buf), pipe)) {
        output += buf;
    }
    int status = pclose(pipe);
    if (status != 0) {
        output += "\n(exit code: " + std::to_string(status) + ")";
    }
    return output;
}

void ZombieSlave::connect_and_serve() {
    struct addrinfo hints{}, *res = nullptr;
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;

    if (getaddrinfo(master_host_.c_str(), std::to_string(master_port_).c_str(), &hints, &res) != 0) {
        std::cerr << "Cannot resolve " << master_host_ << "\n";
        return;
    }

    int fd = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (fd < 0) {
        freeaddrinfo(res);
        std::cerr << "Socket creation failed\n";
        return;
    }

    if (connect(fd, res->ai_addr, res->ai_addrlen) < 0) {
        close(fd);
        freeaddrinfo(res);
        std::cerr << "Connection failed to " << master_host_ << ":" << master_port_ << "\n";
        return;
    }
    freeaddrinfo(res);

    // Send auth token
    std::string token = generate_auth_token() + "\n";
    send(fd, token.c_str(), token.size(), 0);

    // Read auth response
    char buf[1024];
    ssize_t n = recv(fd, buf, sizeof(buf) - 1, 0);
    if (n <= 0) { close(fd); return; }
    buf[n] = '\0';

    std::string response(buf);
    if (response.find("AUTH_OK") == std::string::npos) {
        std::cerr << "❌ Authentication failed\n";
        close(fd);
        return;
    }

    // Send slave ID
    std::string id_msg = slave_id_ + "\n";
    send(fd, id_msg.c_str(), id_msg.size(), 0);

    std::cout << "✅ Connected to master as '" << slave_id_ << "'\n";

    // Command loop
    while (running_) {
        n = recv(fd, buf, sizeof(buf) - 1, 0);
        if (n <= 0) break;
        buf[n] = '\0';

        std::string cmd(buf);
        while (!cmd.empty() && (cmd.back() == '\n' || cmd.back() == '\r'))
            cmd.pop_back();

        if (cmd == "PING") {
            send(fd, "PONG\n", 5, 0);
            continue;
        }

        std::cout << "📥 Command: " << cmd << "\n";
        std::string result = execute_command(cmd);
        result += "\n---END---\n";
        send(fd, result.c_str(), result.size(), 0);
    }

    close(fd);
}

void ZombieSlave::run() {
    running_ = true;

    while (running_) {
        std::cout << "🔌 Connecting to " << master_host_ << ":" << master_port_ << "...\n";
        connect_and_serve();

        if (running_) {
            std::cout << "🔄 Reconnecting in 5s...\n";
            std::this_thread::sleep_for(std::chrono::seconds(5));
        }
    }
}

} // namespace nonail
