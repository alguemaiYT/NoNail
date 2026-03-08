#include <gtest/gtest.h>
#include "core/agent.hpp"

TEST(AgentTest, Construction) {
    nonail::Config cfg;
    cfg.api_key = "test-key";
    cfg.cache.enabled = false;

    nonail::Agent agent(cfg);
    EXPECT_EQ(agent.config().provider, "openai");
    EXPECT_EQ(agent.history().size(), 1);  // system prompt
}

TEST(AgentTest, SlashHelp) {
    nonail::Config cfg;
    cfg.api_key = "test-key";
    cfg.cache.enabled = false;

    nonail::Agent agent(cfg);
    // /help should not signal exit
    EXPECT_FALSE(agent.handle_slash("/help"));
    // /quit should signal exit
    EXPECT_TRUE(agent.handle_slash("/quit"));
}

TEST(AgentTest, SlashClear) {
    nonail::Config cfg;
    cfg.api_key = "test-key";
    cfg.cache.enabled = false;

    nonail::Agent agent(cfg);
    EXPECT_FALSE(agent.handle_slash("/clear"));
    EXPECT_EQ(agent.history().size(), 1);  // only system prompt remains
}
