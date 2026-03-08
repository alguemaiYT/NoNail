#pragma once

#include "providers/provider.hpp"

namespace nonail {

class OpenAIProvider : public Provider {
public:
    OpenAIProvider(const std::string& api_key, const std::string& api_base = "");

    std::string name() const override { return "openai"; }

    Message complete(
        const std::vector<Message>& messages,
        const std::string& model,
        double temperature,
        int max_tokens,
        const nlohmann::json& tools = nlohmann::json::array()
    ) override;

    void stream(
        const std::vector<Message>& messages,
        const std::string& model,
        double temperature,
        int max_tokens,
        StreamCallback cb,
        const nlohmann::json& tools = nlohmann::json::array()
    ) override;

private:
    std::string api_key_;
    std::string api_base_;

    nlohmann::json build_request(
        const std::vector<Message>& messages,
        const std::string& model,
        double temperature,
        int max_tokens,
        const nlohmann::json& tools,
        bool stream
    ) const;
};

} // namespace nonail
