#include "providers/provider.hpp"
#include "providers/openai.hpp"
#include "providers/anthropic.hpp"

#include <stdexcept>

namespace nonail {

std::unique_ptr<Provider> create_provider(
    const std::string& name,
    const std::string& api_key,
    const std::string& api_base
) {
    if (name == "openai") {
        return std::make_unique<OpenAIProvider>(api_key, api_base);
    }
    if (name == "anthropic") {
        return std::make_unique<AnthropicProvider>(api_key, api_base);
    }
    throw std::runtime_error("Unknown provider: " + name);
}

} // namespace nonail
