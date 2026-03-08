#pragma once

#include <nlohmann/json.hpp>
#include <string>
#include <optional>

namespace nonail {

struct WebConfig {
    bool enabled = true;
    int port = 8080;
    std::string bind_address = "0.0.0.0";
};

struct ZombieConfig {
    bool enabled = false;
    int port = 8765;
    std::string password;
    std::string bind_address = "0.0.0.0";
};

struct CacheConfig {
    bool enabled = true;
    std::string path = "~/.nonail/cache.db";
    int max_entries = 5000;
    int ttl_seconds = 86400;
};

struct Config {
    std::string provider = "openai";
    std::string model = "gpt-4o";
    std::string api_key;
    std::string api_base;
    double temperature = 0.7;
    int max_tokens = 4096;

    WebConfig web;
    ZombieConfig zombie;
    CacheConfig cache;

    static Config load(const std::string& path = "");
    void save(const std::string& path = "") const;
    static std::string default_path();

    nlohmann::json to_json() const;
    static Config from_json(const nlohmann::json& j);
};

void to_json(nlohmann::json& j, const Config& c);
void from_json(const nlohmann::json& j, Config& c);

} // namespace nonail
