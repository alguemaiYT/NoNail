#include <gtest/gtest.h>
#include "core/config.hpp"
#include <filesystem>
#include <fstream>

namespace fs = std::filesystem;

TEST(ConfigTest, DefaultValues) {
    nonail::Config cfg;
    EXPECT_EQ(cfg.provider, "openai");
    EXPECT_EQ(cfg.model, "gpt-4o");
    EXPECT_TRUE(cfg.api_key.empty());
    EXPECT_DOUBLE_EQ(cfg.temperature, 0.7);
    EXPECT_EQ(cfg.max_tokens, 4096);
    EXPECT_TRUE(cfg.web.enabled);
    EXPECT_EQ(cfg.web.port, 8080);
    EXPECT_FALSE(cfg.zombie.enabled);
}

TEST(ConfigTest, JsonRoundTrip) {
    nonail::Config cfg;
    cfg.provider = "anthropic";
    cfg.model = "claude-sonnet-4-20250514";
    cfg.api_key = "test-key";
    cfg.temperature = 0.5;
    cfg.web.port = 9090;
    cfg.zombie.enabled = true;
    cfg.zombie.password = "secret";

    nlohmann::json j = cfg;
    auto cfg2 = j.get<nonail::Config>();

    EXPECT_EQ(cfg2.provider, "anthropic");
    EXPECT_EQ(cfg2.model, "claude-sonnet-4-20250514");
    EXPECT_EQ(cfg2.api_key, "test-key");
    EXPECT_DOUBLE_EQ(cfg2.temperature, 0.5);
    EXPECT_EQ(cfg2.web.port, 9090);
    EXPECT_TRUE(cfg2.zombie.enabled);
    EXPECT_EQ(cfg2.zombie.password, "secret");
}

TEST(ConfigTest, SaveAndLoad) {
    std::string tmp_path = "/tmp/nonail-test-config.json";

    nonail::Config cfg;
    cfg.provider = "openai";
    cfg.model = "gpt-4o-mini";
    cfg.api_key = "sk-test123";
    cfg.save(tmp_path);

    EXPECT_TRUE(fs::exists(tmp_path));

    auto loaded = nonail::Config::load(tmp_path);
    EXPECT_EQ(loaded.provider, "openai");
    EXPECT_EQ(loaded.model, "gpt-4o-mini");
    EXPECT_EQ(loaded.api_key, "sk-test123");

    fs::remove(tmp_path);
}

TEST(ConfigTest, MissingFile) {
    auto cfg = nonail::Config::load("/tmp/nonexistent-nonail-config.json");
    EXPECT_EQ(cfg.provider, "openai");  // defaults
}
