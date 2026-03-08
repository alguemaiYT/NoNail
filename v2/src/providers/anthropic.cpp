#include "providers/anthropic.hpp"
#include "core/http_client.hpp"

#include <stdexcept>

namespace nonail {

AnthropicProvider::AnthropicProvider(const std::string& api_key, const std::string& api_base)
    : api_key_(api_key)
    , api_base_(api_base.empty() ? "https://api.anthropic.com/v1" : api_base)
{}

std::string AnthropicProvider::extract_system(const std::vector<Message>& messages) const {
    for (auto& m : messages) {
        if (m.role == "system") return m.content;
    }
    return "";
}

nlohmann::json AnthropicProvider::convert_messages(const std::vector<Message>& messages) const {
    nlohmann::json msgs = nlohmann::json::array();
    for (auto& m : messages) {
        if (m.role == "system") continue;  // handled separately

        nlohmann::json msg;
        if (m.role == "tool") {
            msg = {
                {"role", "user"},
                {"content", nlohmann::json::array({
                    {{"type", "tool_result"},
                     {"tool_use_id", m.tool_call_id},
                     {"content", m.content}}
                })}
            };
        } else if (!m.tool_calls.empty()) {
            nlohmann::json content = nlohmann::json::array();
            if (!m.content.empty()) {
                content.push_back({{"type", "text"}, {"text", m.content}});
            }
            for (auto& tc : m.tool_calls) {
                content.push_back({
                    {"type", "tool_use"},
                    {"id", tc["id"]},
                    {"name", tc["function"]["name"]},
                    {"input", nlohmann::json::parse(tc["function"]["arguments"].get<std::string>())}
                });
            }
            msg = {{"role", "assistant"}, {"content", content}};
        } else {
            msg = {{"role", m.role}, {"content", m.content}};
        }
        msgs.push_back(msg);
    }
    return msgs;
}

nlohmann::json AnthropicProvider::build_request(
    const std::vector<Message>& messages,
    const std::string& model,
    double temperature,
    int max_tokens,
    const nlohmann::json& tools,
    bool stream
) const {
    nlohmann::json req = {
        {"model", model},
        {"max_tokens", max_tokens},
        {"temperature", temperature},
        {"messages", convert_messages(messages)},
        {"stream", stream}
    };

    std::string sys = extract_system(messages);
    if (!sys.empty()) {
        req["system"] = sys;
    }

    if (!tools.empty()) {
        // Convert OpenAI tool format to Anthropic format
        nlohmann::json anthropic_tools = nlohmann::json::array();
        for (auto& t : tools) {
            anthropic_tools.push_back({
                {"name", t["function"]["name"]},
                {"description", t["function"]["description"]},
                {"input_schema", t["function"]["parameters"]}
            });
        }
        req["tools"] = anthropic_tools;
    }
    return req;
}

Message AnthropicProvider::complete(
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
        api_base_ + "/messages",
        req,
        {
            {"x-api-key", api_key_},
            {"anthropic-version", "2023-06-01"}
        }
    );

    if (!resp.ok()) {
        throw std::runtime_error("Anthropic API error (" + std::to_string(resp.status_code) + "): " + resp.body);
    }

    auto j = nlohmann::json::parse(resp.body);
    Message result;
    result.role = "assistant";

    // Parse content blocks
    for (auto& block : j["content"]) {
        if (block["type"] == "text") {
            result.content += block["text"].get<std::string>();
        } else if (block["type"] == "tool_use") {
            nlohmann::json tc = {
                {"id", block["id"]},
                {"type", "function"},
                {"function", {
                    {"name", block["name"]},
                    {"arguments", block["input"].dump()}
                }}
            };
            result.tool_calls.push_back(tc);
        }
    }
    return result;
}

void AnthropicProvider::stream(
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
        api_base_ + "/messages",
        req,
        {
            {"x-api-key", api_key_},
            {"anthropic-version", "2023-06-01"}
        },
        [&cb](const std::string& chunk) {
            try {
                auto j = nlohmann::json::parse(chunk);
                if (j["type"] == "content_block_delta") {
                    auto& delta = j["delta"];
                    if (delta["type"] == "text_delta") {
                        cb(delta["text"].get<std::string>());
                    }
                }
            } catch (...) {}
        }
    );
}

} // namespace nonail
