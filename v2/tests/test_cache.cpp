#include <gtest/gtest.h>
#include "core/cache.hpp"
#include <filesystem>

TEST(CacheTest, PutAndGet) {
    std::string path = "/tmp/nonail-test-cache.db";
    std::filesystem::remove(path);

    nonail::CacheStore cache(path);
    cache.put("key1", "value1");

    auto result = cache.get("key1");
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(*result, "value1");

    std::filesystem::remove(path);
}

TEST(CacheTest, MissingKey) {
    std::string path = "/tmp/nonail-test-cache2.db";
    std::filesystem::remove(path);

    nonail::CacheStore cache(path);
    auto result = cache.get("nonexistent");
    EXPECT_FALSE(result.has_value());

    std::filesystem::remove(path);
}

TEST(CacheTest, Clear) {
    std::string path = "/tmp/nonail-test-cache3.db";
    std::filesystem::remove(path);

    nonail::CacheStore cache(path);
    cache.put("k1", "v1");
    cache.put("k2", "v2");
    EXPECT_EQ(cache.count(), 2);

    cache.clear();
    EXPECT_EQ(cache.count(), 0);

    std::filesystem::remove(path);
}

TEST(CacheTest, Overwrite) {
    std::string path = "/tmp/nonail-test-cache4.db";
    std::filesystem::remove(path);

    nonail::CacheStore cache(path);
    cache.put("key", "old");
    cache.put("key", "new");

    auto result = cache.get("key");
    ASSERT_TRUE(result.has_value());
    EXPECT_EQ(*result, "new");
    EXPECT_EQ(cache.count(), 1);

    std::filesystem::remove(path);
}
