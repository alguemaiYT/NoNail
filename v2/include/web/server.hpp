#pragma once

#include "core/agent.hpp"
#include <string>
#include <memory>
#include <atomic>

namespace nonail {

class WebServer {
public:
    WebServer(Agent& agent, const std::string& assets_dir = "");
    ~WebServer();

    void start(const std::string& host = "0.0.0.0", int port = 8080);
    void stop();
    bool is_running() const { return running_.load(); }

private:
    Agent& agent_;
    std::string assets_dir_;
    std::atomic<bool> running_{false};
    void* server_ = nullptr;  // httplib::Server*

    void register_routes();
    void register_api_routes();
    void register_ws_routes();
    std::string get_index_html() const;
};

} // namespace nonail
