#include "core/http_client.hpp"

#include <curl/curl.h>
#include <stdexcept>
#include <sstream>

namespace nonail {

// CURL write callback
static size_t write_callback(char* ptr, size_t size, size_t nmemb, void* userdata) {
    auto* body = static_cast<std::string*>(userdata);
    body->append(ptr, size * nmemb);
    return size * nmemb;
}

// CURL streaming write callback
struct StreamCtx {
    StreamChunkCallback cb;
    std::string buffer;
};

static size_t stream_write_callback(char* ptr, size_t size, size_t nmemb, void* userdata) {
    auto* ctx = static_cast<StreamCtx*>(userdata);
    size_t total = size * nmemb;
    ctx->buffer.append(ptr, total);

    // Process complete SSE lines
    size_t pos;
    while ((pos = ctx->buffer.find('\n')) != std::string::npos) {
        std::string line = ctx->buffer.substr(0, pos);
        ctx->buffer.erase(0, pos + 1);

        // SSE format: "data: {...}"
        if (line.substr(0, 6) == "data: ") {
            std::string data = line.substr(6);
            if (data != "[DONE]") {
                ctx->cb(data);
            }
        }
    }
    return total;
}

// Header callback
static size_t header_callback(char* buffer, size_t size, size_t nitems, void* userdata) {
    auto* headers = static_cast<std::map<std::string, std::string>*>(userdata);
    std::string line(buffer, size * nitems);
    auto colon = line.find(':');
    if (colon != std::string::npos) {
        std::string key = line.substr(0, colon);
        std::string val = line.substr(colon + 2);
        // Trim trailing \r\n
        while (!val.empty() && (val.back() == '\r' || val.back() == '\n'))
            val.pop_back();
        (*headers)[key] = val;
    }
    return size * nitems;
}

HttpClient::HttpClient() {
    curl_ = curl_easy_init();
    if (!curl_) throw std::runtime_error("Failed to init CURL");
}

HttpClient::~HttpClient() {
    if (curl_) curl_easy_cleanup(static_cast<CURL*>(curl_));
}

void HttpClient::set_timeout(long seconds) {
    timeout_ = seconds;
}

HttpResponse HttpClient::request(
    const std::string& method,
    const std::string& url,
    const std::string& body,
    const std::map<std::string, std::string>& headers
) {
    CURL* c = static_cast<CURL*>(curl_);
    HttpResponse resp;

    curl_easy_reset(c);
    curl_easy_setopt(c, CURLOPT_URL, url.c_str());
    curl_easy_setopt(c, CURLOPT_TIMEOUT, timeout_);
    curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, write_callback);
    curl_easy_setopt(c, CURLOPT_WRITEDATA, &resp.body);
    curl_easy_setopt(c, CURLOPT_HEADERFUNCTION, header_callback);
    curl_easy_setopt(c, CURLOPT_HEADERDATA, &resp.headers);

    if (method == "POST") {
        curl_easy_setopt(c, CURLOPT_POST, 1L);
        curl_easy_setopt(c, CURLOPT_POSTFIELDS, body.c_str());
        curl_easy_setopt(c, CURLOPT_POSTFIELDSIZE, static_cast<long>(body.size()));
    } else if (method == "PUT") {
        curl_easy_setopt(c, CURLOPT_CUSTOMREQUEST, "PUT");
        curl_easy_setopt(c, CURLOPT_POSTFIELDS, body.c_str());
    } else if (method == "DELETE") {
        curl_easy_setopt(c, CURLOPT_CUSTOMREQUEST, "DELETE");
    }

    struct curl_slist* header_list = nullptr;
    for (auto& [k, v] : headers) {
        header_list = curl_slist_append(header_list, (k + ": " + v).c_str());
    }
    if (header_list) {
        curl_easy_setopt(c, CURLOPT_HTTPHEADER, header_list);
    }

    CURLcode res = curl_easy_perform(c);
    if (res != CURLE_OK) {
        resp.error = curl_easy_strerror(res);
    }

    long http_code = 0;
    curl_easy_getinfo(c, CURLINFO_RESPONSE_CODE, &http_code);
    resp.status_code = static_cast<int>(http_code);

    if (header_list) curl_slist_free_all(header_list);
    return resp;
}

HttpResponse HttpClient::get(const std::string& url,
                              const std::map<std::string, std::string>& headers) {
    return request("GET", url, "", headers);
}

HttpResponse HttpClient::post_json(
    const std::string& url,
    const nlohmann::json& body,
    const std::map<std::string, std::string>& headers
) {
    auto hdrs = headers;
    hdrs["Content-Type"] = "application/json";
    return request("POST", url, body.dump(), hdrs);
}

HttpResponse HttpClient::post_stream(
    const std::string& url,
    const nlohmann::json& body,
    const std::map<std::string, std::string>& headers,
    StreamChunkCallback cb
) {
    CURL* c = static_cast<CURL*>(curl_);
    HttpResponse resp;
    StreamCtx ctx{cb, ""};

    curl_easy_reset(c);
    curl_easy_setopt(c, CURLOPT_URL, url.c_str());
    curl_easy_setopt(c, CURLOPT_TIMEOUT, 120L);  // longer for streaming
    curl_easy_setopt(c, CURLOPT_POST, 1L);

    std::string body_str = body.dump();
    curl_easy_setopt(c, CURLOPT_POSTFIELDS, body_str.c_str());
    curl_easy_setopt(c, CURLOPT_POSTFIELDSIZE, static_cast<long>(body_str.size()));

    curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, stream_write_callback);
    curl_easy_setopt(c, CURLOPT_WRITEDATA, &ctx);

    struct curl_slist* header_list = nullptr;
    for (auto& [k, v] : headers) {
        header_list = curl_slist_append(header_list, (k + ": " + v).c_str());
    }
    header_list = curl_slist_append(header_list, "Content-Type: application/json");
    curl_easy_setopt(c, CURLOPT_HTTPHEADER, header_list);

    CURLcode res = curl_easy_perform(c);
    if (res != CURLE_OK) resp.error = curl_easy_strerror(res);

    long http_code = 0;
    curl_easy_getinfo(c, CURLINFO_RESPONSE_CODE, &http_code);
    resp.status_code = static_cast<int>(http_code);

    if (header_list) curl_slist_free_all(header_list);
    return resp;
}

} // namespace nonail
