#pragma once

#include <string>
#include <vector>
#include <map>
#include <functional>
#include <nlohmann/json.hpp>

namespace nonail {

struct HttpResponse {
    int status_code = 0;
    std::string body;
    std::map<std::string, std::string> headers;
    std::string error;

    bool ok() const { return status_code >= 200 && status_code < 300; }
};

using StreamChunkCallback = std::function<void(const std::string& chunk)>;

class HttpClient {
public:
    HttpClient();
    ~HttpClient();

    HttpClient(const HttpClient&) = delete;
    HttpClient& operator=(const HttpClient&) = delete;

    // Standard request
    HttpResponse request(
        const std::string& method,
        const std::string& url,
        const std::string& body = "",
        const std::map<std::string, std::string>& headers = {}
    );

    // GET shorthand
    HttpResponse get(const std::string& url,
                     const std::map<std::string, std::string>& headers = {});

    // POST JSON shorthand
    HttpResponse post_json(
        const std::string& url,
        const nlohmann::json& body,
        const std::map<std::string, std::string>& headers = {}
    );

    // Streaming POST (SSE) — calls cb for each data: line
    HttpResponse post_stream(
        const std::string& url,
        const nlohmann::json& body,
        const std::map<std::string, std::string>& headers,
        StreamChunkCallback cb
    );

    void set_timeout(long seconds);

private:
    void* curl_ = nullptr;   // CURL handle
    long timeout_ = 30;
};

} // namespace nonail
