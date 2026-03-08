#pragma once

#include "providers/openai.hpp"

namespace nonail {

// Groq is OpenAI API-compatible — just swaps the base URL.
class GroqProvider : public OpenAIProvider {
public:
    explicit GroqProvider(const std::string& api_key, const std::string& api_base = "")
        : OpenAIProvider(api_key, api_base.empty() ? "https://api.groq.com/openai/v1" : api_base)
    {}

    std::string name() const override { return "groq"; }
};

} // namespace nonail
