#include "core/http_client.hpp"
#include <nlohmann/json.hpp>
#include <iostream>
#include <thread>
#include <chrono>

namespace nonail {

class DiscordBot {
public:
    DiscordBot(const std::string& token, int64_t channel_id = 0)
        : token_(token), channel_id_(channel_id)
    {}

    using MessageHandler = std::function<std::string(const std::string& text, const std::string& user_id)>;

    void set_handler(MessageHandler handler) { handler_ = handler; }

    void send_message(const std::string& content) {
        HttpClient http;
        nlohmann::json body = {{"content", content}};
        http.post_json(
            "https://discord.com/api/v10/channels/" + std::to_string(channel_id_) + "/messages",
            body,
            {{"Authorization", "Bot " + token_}}
        );
    }

    void poll() {
        HttpClient http;
        std::string last_message_id;

        while (running_) {
            std::string url = "https://discord.com/api/v10/channels/" +
                std::to_string(channel_id_) + "/messages?limit=1";
            if (!last_message_id.empty()) url += "&after=" + last_message_id;

            auto resp = http.get(url, {{"Authorization", "Bot " + token_}});
            if (!resp.ok()) {
                std::this_thread::sleep_for(std::chrono::seconds(5));
                continue;
            }

            auto msgs = nlohmann::json::parse(resp.body);
            for (auto& msg : msgs) {
                if (msg["author"].contains("bot") && msg["author"]["bot"].get<bool>())
                    continue;

                last_message_id = msg["id"].get<std::string>();
                std::string content = msg["content"].get<std::string>();
                std::string user_id = msg["author"]["id"].get<std::string>();

                if (handler_) {
                    std::string reply = handler_(content, user_id);
                    send_message(reply);
                }
            }
            std::this_thread::sleep_for(std::chrono::seconds(2));
        }
    }

    void stop() { running_ = false; }

private:
    std::string token_;
    int64_t channel_id_;
    MessageHandler handler_;
    bool running_ = true;
};

} // namespace nonail
