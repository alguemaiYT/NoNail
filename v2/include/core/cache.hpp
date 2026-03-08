#pragma once

#include <string>
#include <optional>

namespace nonail {

class CacheStore {
public:
    explicit CacheStore(const std::string& db_path = "~/.nonail/cache.db",
                        int max_entries = 5000,
                        int ttl_seconds = 86400);
    ~CacheStore();

    CacheStore(const CacheStore&) = delete;
    CacheStore& operator=(const CacheStore&) = delete;

    // Lookup a cached response for the given prompt hash
    std::optional<std::string> get(const std::string& key) const;

    // Store a response
    void put(const std::string& key, const std::string& value);

    // Clear all entries
    void clear();

    // Return number of entries
    int count() const;

    // Prune expired entries
    void prune();

private:
    void init_db();
    void enforce_limits();
    std::string expand_path(const std::string& path) const;

    void* db_ = nullptr;  // sqlite3*
    std::string db_path_;
    int max_entries_;
    int ttl_seconds_;
};

} // namespace nonail
