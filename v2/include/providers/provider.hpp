#pragma once

#include <string>
#include <vector>
#include <functional>
#include <nlohmann/json.hpp>

namespace nonail {

struct Message {
    std::string role;    // "system", "user", "assistant", "tool"
    std::string content;
    std::string tool_call_id;
    nlohmann::json tool_calls = nlohmann::json::array();
};

using StreamCallback = std::function<void(const std::string& chunk)>;

class Provider {
public:
    virtual ~Provider() = default;

    virtual std::string name() const = 0;

    // Synchronous completion
    virtual Message complete(
        const std::vector<Message>& messages,
        const std::string& model,
        double temperature,
        int max_tokens,
        const nlohmann::json& tools = nlohmann::json::array()
    ) = 0;

    // Streaming completion (calls cb for each chunk)
    virtual void stream(
        const std::vector<Message>& messages,
        const std::string& model,
        double temperature,
        int max_tokens,
        StreamCallback cb,
        const nlohmann::json& tools = nlohmann::json::array()
    ) = 0;
};

// Factory: create provider by name
std::unique_ptr<Provider> create_provider(
    const std::string& name,
    const std::string& api_key,
    const std::string& api_base = ""
);

} // namespace nonail
