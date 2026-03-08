#include "core/cache.hpp"

#include <sqlite3.h>
#include <cstdlib>
#include <ctime>
#include <filesystem>
#include <stdexcept>

namespace fs = std::filesystem;

namespace nonail {

std::string CacheStore::expand_path(const std::string& path) const {
    if (path.size() >= 2 && path[0] == '~' && path[1] == '/') {
        const char* home = std::getenv("HOME");
        if (home) return std::string(home) + path.substr(1);
    }
    return path;
}

CacheStore::CacheStore(const std::string& db_path, int max_entries, int ttl_seconds)
    : db_path_(expand_path(db_path))
    , max_entries_(max_entries)
    , ttl_seconds_(ttl_seconds)
{
    init_db();
}

CacheStore::~CacheStore() {
    if (db_) sqlite3_close(static_cast<sqlite3*>(db_));
}

void CacheStore::init_db() {
    fs::create_directories(fs::path(db_path_).parent_path());

    sqlite3* db = nullptr;
    int rc = sqlite3_open(db_path_.c_str(), &db);
    if (rc != SQLITE_OK) {
        throw std::runtime_error("Failed to open cache DB: " + db_path_);
    }
    db_ = db;

    const char* sql =
        "CREATE TABLE IF NOT EXISTS cache ("
        "  key TEXT PRIMARY KEY,"
        "  value TEXT NOT NULL,"
        "  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))"
        ")";
    char* errmsg = nullptr;
    sqlite3_exec(db, sql, nullptr, nullptr, &errmsg);
    if (errmsg) {
        std::string err(errmsg);
        sqlite3_free(errmsg);
        throw std::runtime_error("Cache DB init failed: " + err);
    }
}

std::optional<std::string> CacheStore::get(const std::string& key) const {
    auto* db = static_cast<sqlite3*>(db_);
    const char* sql = "SELECT value FROM cache WHERE key = ? AND created_at > ?";
    sqlite3_stmt* stmt = nullptr;
    sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr);

    sqlite3_bind_text(stmt, 1, key.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt, 2, static_cast<int64_t>(std::time(nullptr)) - ttl_seconds_);

    std::optional<std::string> result;
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        result = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 0));
    }
    sqlite3_finalize(stmt);
    return result;
}

void CacheStore::put(const std::string& key, const std::string& value) {
    auto* db = static_cast<sqlite3*>(db_);
    const char* sql =
        "INSERT OR REPLACE INTO cache (key, value, created_at) VALUES (?, ?, strftime('%s','now'))";
    sqlite3_stmt* stmt = nullptr;
    sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr);
    sqlite3_bind_text(stmt, 1, key.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, value.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    enforce_limits();
}

void CacheStore::clear() {
    auto* db = static_cast<sqlite3*>(db_);
    sqlite3_exec(db, "DELETE FROM cache", nullptr, nullptr, nullptr);
}

int CacheStore::count() const {
    auto* db = static_cast<sqlite3*>(db_);
    sqlite3_stmt* stmt = nullptr;
    sqlite3_prepare_v2(db, "SELECT COUNT(*) FROM cache", -1, &stmt, nullptr);
    int n = 0;
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        n = sqlite3_column_int(stmt, 0);
    }
    sqlite3_finalize(stmt);
    return n;
}

void CacheStore::prune() {
    auto* db = static_cast<sqlite3*>(db_);
    const char* sql = "DELETE FROM cache WHERE created_at < ?";
    sqlite3_stmt* stmt = nullptr;
    sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr);
    sqlite3_bind_int64(stmt, 1, static_cast<int64_t>(std::time(nullptr)) - ttl_seconds_);
    sqlite3_step(stmt);
    sqlite3_finalize(stmt);
}

void CacheStore::enforce_limits() {
    if (count() > max_entries_) {
        auto* db = static_cast<sqlite3*>(db_);
        // Delete oldest entries exceeding limit
        std::string sql =
            "DELETE FROM cache WHERE key IN ("
            "  SELECT key FROM cache ORDER BY created_at ASC LIMIT " +
            std::to_string(count() - max_entries_) + ")";
        sqlite3_exec(db, sql.c_str(), nullptr, nullptr, nullptr);
    }
}

} // namespace nonail
