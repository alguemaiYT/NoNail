#include "core/config.hpp"

#include <fstream>
#include <cstdlib>
#include <filesystem>

namespace fs = std::filesystem;

namespace nonail {

// ---------------------------------------------------------------------------
// JSON serialization
// ---------------------------------------------------------------------------

void to_json(nlohmann::json& j, const Config& c) {
    j = nlohmann::json{
        {"provider", c.provider},
        {"model", c.model},
        {"api_key", c.api_key},
        {"api_base", c.api_base},
        {"temperature", c.temperature},
        {"max_tokens", c.max_tokens},
        {"web", {
            {"enabled", c.web.enabled},
            {"port", c.web.port},
            {"bind_address", c.web.bind_address}
        }},
        {"zombie", {
            {"enabled", c.zombie.enabled},
            {"port", c.zombie.port},
            {"password", c.zombie.password},
            {"bind_address", c.zombie.bind_address}
        }},
        {"cache", {
            {"enabled", c.cache.enabled},
            {"path", c.cache.path},
            {"max_entries", c.cache.max_entries},
            {"ttl_seconds", c.cache.ttl_seconds}
        }}
    };
}

void from_json(const nlohmann::json& j, Config& c) {
    if (j.contains("provider"))    j.at("provider").get_to(c.provider);
    if (j.contains("model"))       j.at("model").get_to(c.model);
    if (j.contains("api_key"))     j.at("api_key").get_to(c.api_key);
    if (j.contains("api_base"))    j.at("api_base").get_to(c.api_base);
    if (j.contains("temperature")) j.at("temperature").get_to(c.temperature);
    if (j.contains("max_tokens"))  j.at("max_tokens").get_to(c.max_tokens);

    if (j.contains("web")) {
        auto& w = j.at("web");
        if (w.contains("enabled"))      w.at("enabled").get_to(c.web.enabled);
        if (w.contains("port"))         w.at("port").get_to(c.web.port);
        if (w.contains("bind_address")) w.at("bind_address").get_to(c.web.bind_address);
    }
    if (j.contains("zombie")) {
        auto& z = j.at("zombie");
        if (z.contains("enabled"))      z.at("enabled").get_to(c.zombie.enabled);
        if (z.contains("port"))         z.at("port").get_to(c.zombie.port);
        if (z.contains("password"))     z.at("password").get_to(c.zombie.password);
        if (z.contains("bind_address")) z.at("bind_address").get_to(c.zombie.bind_address);
    }
    if (j.contains("cache")) {
        auto& ca = j.at("cache");
        if (ca.contains("enabled"))      ca.at("enabled").get_to(c.cache.enabled);
        if (ca.contains("path"))         ca.at("path").get_to(c.cache.path);
        if (ca.contains("max_entries"))  ca.at("max_entries").get_to(c.cache.max_entries);
        if (ca.contains("ttl_seconds")) ca.at("ttl_seconds").get_to(c.cache.ttl_seconds);
    }

    // Try loading api_key from environment if empty
    if (c.api_key.empty()) {
        const char* env_key = nullptr;
        if (c.provider == "openai")    env_key = std::getenv("OPENAI_API_KEY");
        if (c.provider == "anthropic") env_key = std::getenv("ANTHROPIC_API_KEY");
        if (c.provider == "groq")      env_key = std::getenv("GROQ_API_KEY");
        if (c.provider == "gemini")    env_key = std::getenv("GEMINI_API_KEY");
        if (!env_key) env_key = std::getenv("NONAIL_API_KEY");
        if (env_key) c.api_key = env_key;
    }
}

// ---------------------------------------------------------------------------
// File I/O
// ---------------------------------------------------------------------------

std::string Config::default_path() {
    const char* home = std::getenv("HOME");
    if (!home) home = "/tmp";
    return std::string(home) + "/.nonail/config.json";
}

Config Config::load(const std::string& path) {
    std::string cfg_path = path.empty() ? default_path() : path;
    Config cfg;

    if (fs::exists(cfg_path)) {
        std::ifstream ifs(cfg_path);
        if (ifs.good()) {
            nlohmann::json j;
            ifs >> j;
            cfg = j.get<Config>();
        }
    }
    return cfg;
}

void Config::save(const std::string& path) const {
    std::string cfg_path = path.empty() ? default_path() : path;

    fs::create_directories(fs::path(cfg_path).parent_path());

    nlohmann::json j = *this;
    std::ofstream ofs(cfg_path);
    ofs << j.dump(2) << std::endl;

    // Set restrictive permissions (owner only)
    fs::permissions(cfg_path,
        fs::perms::owner_read | fs::perms::owner_write,
        fs::perm_options::replace);
}

nlohmann::json Config::to_json() const {
    nlohmann::json j;
    nonail::to_json(j, *this);
    return j;
}

Config Config::from_json(const nlohmann::json& j) {
    Config c;
    nonail::from_json(j, c);
    return c;
}

} // namespace nonail
