#include "core/agent.hpp"

#include <iostream>
#include <sstream>
#include <functional>

namespace nonail {

static const char* SYSTEM_PROMPT = R"(You are NoNail, a helpful AI assistant with full computer access.
You can execute shell commands, read/write files, and manage the system.
Always explain what you're about to do before executing commands.
Be concise and direct.)";

Agent::Agent(const Config& config)
    : config_(config)
{
    init_provider();
    tools_.register_defaults();

    if (config_.cache.enabled) {
        cache_ = std::make_unique<CacheStore>(
            config_.cache.path,
            config_.cache.max_entries,
            config_.cache.ttl_seconds
        );
    }

    system_prompt_ = build_system_prompt();
    history_.push_back({"system", system_prompt_, "", {}});
}

Agent::~Agent() = default;

void Agent::init_provider() {
    provider_ = create_provider(config_.provider, config_.api_key, config_.api_base);
}

std::string Agent::build_system_prompt() const {
    std::string prompt = SYSTEM_PROMPT;

    // Add tool descriptions
    auto names = tools_.list_names();
    if (!names.empty()) {
        prompt += "\n\nAvailable tools:\n";
        for (auto& name : names) {
            auto& t = tools_.get(name);
            prompt += "- " + t.name + ": " + t.description + "\n";
        }
    }
    return prompt;
}

void Agent::print_banner() const {
    std::cout << "\n"
              << "╔══════════════════════════════════════╗\n"
              << "║  🔨 NoNail v2 — C++ Edition         ║\n"
              << "║  Provider: " << config_.provider
              << " | Model: " << config_.model << "\n"
              << "╚══════════════════════════════════════╝\n"
              << "\n"
              << "Type your message. Use /help for commands, /quit to exit.\n\n";
}

bool Agent::handle_slash(const std::string& input) {
    if (input == "/quit" || input == "/exit") {
        std::cout << "Goodbye!\n";
        return true;  // signal exit
    }
    if (input == "/help") {
        std::cout << "Commands:\n"
                  << "  /quit     Exit chat\n"
                  << "  /clear    Clear history\n"
                  << "  /model    Show current model\n"
                  << "  /tools    List available tools\n"
                  << "  /status   Show status\n"
                  << "  /cache    Show cache status\n";
        return false;
    }
    if (input == "/clear") {
        history_.clear();
        history_.push_back({"system", system_prompt_, "", {}});
        std::cout << "History cleared.\n";
        return false;
    }
    if (input == "/model") {
        std::cout << config_.provider << "/" << config_.model << "\n";
        return false;
    }
    if (input == "/tools") {
        auto names = tools_.list_names();
        std::cout << "Tools (" << names.size() << "):\n";
        for (auto& n : names) {
            auto& t = tools_.get(n);
            std::cout << "  " << t.name << " — " << t.description << "\n";
        }
        return false;
    }
    if (input == "/status") {
        std::cout << "Provider: " << config_.provider << "\n"
                  << "Model: " << config_.model << "\n"
                  << "History: " << history_.size() << " messages\n"
                  << "Cache: " << (cache_ ? std::to_string(cache_->count()) + " entries" : "disabled") << "\n";
        return false;
    }
    if (input == "/cache") {
        if (!cache_) {
            std::cout << "Cache: disabled\n";
        } else {
            std::cout << "Cache: " << cache_->count() << " entries\n"
                      << "Path: " << config_.cache.path << "\n";
        }
        return false;
    }

    std::cout << "Unknown command: " << input << ". Type /help for help.\n";
    return false;
}

Message Agent::call_llm(bool stream) {
    auto tool_schema = tools_.to_openai_schema();

    if (stream) {
        std::string accumulated;
        provider_->stream(
            history_, config_.model, config_.temperature, config_.max_tokens,
            [&accumulated](const std::string& chunk) {
                std::cout << chunk << std::flush;
                accumulated += chunk;
            },
            tool_schema
        );
        std::cout << "\n";
        return {"assistant", accumulated, "", {}};
    } else {
        return provider_->complete(
            history_, config_.model, config_.temperature, config_.max_tokens, tool_schema
        );
    }
}

void Agent::handle_tool_calls(const Message& response) {
    for (auto& tc : response.tool_calls) {
        std::string name = tc["function"]["name"];
        std::string args_str = tc["function"]["arguments"];
        std::string tool_id = tc["id"];

        std::cout << "🔧 " << name << "(" << args_str << ")\n";

        nlohmann::json args;
        try {
            args = nlohmann::json::parse(args_str);
        } catch (...) {
            args = nlohmann::json::object();
        }

        ToolResult result;
        if (tools_.has(name)) {
            result = tools_.execute(name, args);
        } else {
            result = {false, "", "Unknown tool: " + name};
        }

        std::string output = result.success ? result.output : ("ERROR: " + result.error);
        if (output.size() > 4000) output = output.substr(0, 4000) + "\n... (truncated)";

        history_.push_back({"tool", output, tool_id, {}});
    }
}

std::string Agent::step(const std::string& prompt) {
    history_.push_back({"user", prompt, "", {}});

    // Tool loop: keep calling LLM until no more tool calls
    int max_iterations = 10;
    for (int i = 0; i < max_iterations; ++i) {
        auto response = call_llm(false);
        history_.push_back(response);

        if (response.tool_calls.empty()) {
            return response.content;
        }
        handle_tool_calls(response);
    }
    return "(max tool iterations reached)";
}

void Agent::chat_loop() {
    print_banner();

    std::string input;
    while (true) {
        std::cout << "You> " << std::flush;
        if (!std::getline(std::cin, input)) break;

        // Trim
        while (!input.empty() && (input.front() == ' ' || input.front() == '\t'))
            input.erase(input.begin());
        while (!input.empty() && (input.back() == ' ' || input.back() == '\t'))
            input.pop_back();

        if (input.empty()) continue;

        // Slash commands
        if (input[0] == '/') {
            if (handle_slash(input)) break;
            continue;
        }

        // Add user message
        history_.push_back({"user", input, "", {}});

        // Call LLM with streaming
        std::cout << "\nNoNail> ";
        try {
            auto response = call_llm(true);
            history_.push_back(response);

            // Handle tool calls (non-streaming loop)
            while (!response.tool_calls.empty()) {
                handle_tool_calls(response);
                std::cout << "\nNoNail> ";
                response = call_llm(true);
                history_.push_back(response);
            }
        } catch (const std::exception& e) {
            std::cout << "\n❌ Error: " << e.what() << "\n";
        }
        std::cout << "\n";
    }
}

} // namespace nonail
