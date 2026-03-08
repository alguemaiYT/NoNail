#pragma once

#include "providers/openai.hpp"

namespace nonail {

// Gemini via Google's OpenAI-compatible endpoint.
class GeminiProvider : public OpenAIProvider {
public:
    explicit GeminiProvider(const std::string& api_key, const std::string& api_base = "")
        : OpenAIProvider(api_key, api_base.empty()
            ? "https://generativelanguage.googleapis.com/v1beta/openai"
            : api_base)
    {}

    std::string name() const override { return "gemini"; }
};

} // namespace nonail
