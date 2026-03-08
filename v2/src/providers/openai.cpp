#include "providers/openai.hpp"
#include "core/http_client.hpp"

#include <stdexcept>

namespace nonail {

OpenAIProvider::OpenAIProvider(const std::string& api_key, const std::string& api_base)
    : api_key_(api_key)
    , api_base_(api_base.empty() ? "https://api.openai.com/v1" : api_base)
{}

nlohmann::json OpenAIProvider::build_request(
    const std::vector<Message>& messages,
    const std::string& model,
    double temperature,
    int max_tokens,
    const nlohmann::json& tools,
    bool stream
) const {
    nlohmann::json msgs = nlohmann::json::array();
    for (auto& m : messages) {
        nlohmann::json msg = {{"role", m.role}, {"content", m.content}};
        if (!m.tool_call_id.empty()) msg["tool_call_id"] = m.tool_call_id;
        if (!m.tool_calls.empty())   msg["tool_calls"] = m.tool_calls;
        msgs.push_back(msg);
    }

    nlohmann::json req = {
        {"model", model},
        {"messages", msgs},
        {"temperature", temperature},
        {"max_tokens", max_tokens},
        {"stream", stream}
    };

    if (!tools.empty()) {
        req["tools"] = tools;
    }
    return req;
}

Message OpenAIProvider::complete(
    const std::vector<Message>& messages,
    const std::string& model,
    double temperature,
    int max_tokens,
    const nlohmann::json& tools
) {
    HttpClient http;
    http.set_timeout(120);

    auto req = build_request(messages, model, temperature, max_tokens, tools, false);
    auto resp = http.post_json(
        api_base_ + "/chat/completions",
        req,
        {{"Authorization", "Bearer " + api_key_}}
    );

    if (!resp.ok()) {
        throw std::runtime_error("OpenAI API error (" + std::to_string(resp.status_code) + "): " + resp.body);
    }

    auto j = nlohmann::json::parse(resp.body);
    auto& choice = j["choices"][0]["message"];

    Message result;
    result.role = choice.value("role", "assistant");
    result.content = choice.value("content", "");
    if (choice.contains("tool_calls")) {
        result.tool_calls = choice["tool_calls"];
    }
    return result;
}

void OpenAIProvider::stream(
    const std::vector<Message>& messages,
    const std::string& model,
    double temperature,
    int max_tokens,
    StreamCallback cb,
    const nlohmann::json& tools
) {
    HttpClient http;
    http.set_timeout(120);

    auto req = build_request(messages, model, temperature, max_tokens, tools, true);
    http.post_stream(
        api_base_ + "/chat/completions",
        req,
        {{"Authorization", "Bearer " + api_key_}},
        [&cb](const std::string& chunk) {
            try {
                auto j = nlohmann::json::parse(chunk);
                auto& delta = j["choices"][0]["delta"];
                if (delta.contains("content") && !delta["content"].is_null()) {
                    cb(delta["content"].get<std::string>());
                }
            } catch (...) {
                // Ignore malformed chunks
            }
        }
    );
}

} // namespace nonail
