#pragma once

#include "core/config.hpp"
#include "core/cache.hpp"
#include "providers/provider.hpp"
#include "tools/tool_registry.hpp"

#include <string>
#include <vector>
#include <memory>

namespace nonail {

class Agent {
public:
    explicit Agent(const Config& config);
    ~Agent();

    // Interactive chat loop (stdin/stdout)
    void chat_loop();

    // Single prompt → response
    std::string step(const std::string& prompt);

    // Accessors
    const Config& config() const { return config_; }
    const std::vector<Message>& history() const { return history_; }

    // Slash commands
    bool handle_slash(const std::string& input);

private:
    Config config_;
    std::unique_ptr<Provider> provider_;
    std::unique_ptr<CacheStore> cache_;
    ToolRegistry tools_;
    std::vector<Message> history_;
    std::string system_prompt_;

    void init_provider();
    void print_banner() const;
    Message call_llm(bool stream = true);
    void handle_tool_calls(const Message& response);
    std::string build_system_prompt() const;
};

} // namespace nonail
