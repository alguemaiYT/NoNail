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

TEST(ProviderTest, UnknownProvider) {
    EXPECT_THROW(nonail::create_provider("unknown", "key"), std::runtime_error);
}
