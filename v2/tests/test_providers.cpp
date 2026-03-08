#include <gtest/gtest.h>
#include "providers/provider.hpp"

TEST(ProviderTest, CreateOpenAI) {
    auto provider = nonail::create_provider("openai", "test-key");
    ASSERT_NE(provider, nullptr);
    EXPECT_EQ(provider->name(), "openai");
}

TEST(ProviderTest, CreateAnthropic) {
    auto provider = nonail::create_provider("anthropic", "test-key");
    ASSERT_NE(provider, nullptr);
    EXPECT_EQ(provider->name(), "anthropic");
}

TEST(ProviderTest, CreateGroq) {
    auto provider = nonail::create_provider("groq", "test-key");
    ASSERT_NE(provider, nullptr);
    EXPECT_EQ(provider->name(), "groq");
}

TEST(ProviderTest, CreateGemini) {
    auto provider = nonail::create_provider("gemini", "test-key");
    ASSERT_NE(provider, nullptr);
    EXPECT_EQ(provider->name(), "gemini");
}

TEST(ProviderTest, UnknownProvider) {
    EXPECT_THROW(nonail::create_provider("unknown", "key"), std::runtime_error);
}
