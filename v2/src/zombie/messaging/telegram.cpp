#include "core/http_client.hpp"
#include <nlohmann/json.hpp>
#include <iostream>
#include <thread>
#include <chrono>

namespace nonail {

class TelegramBot {
public:
    TelegramBot(const std::string& token, const std::vector<int64_t>& allowed_users = {})
        : token_(token), allowed_users_(allowed_users)
    {}

    using MessageHandler = std::function<std::string(const std::string& text, int64_t user_id)>;

    void set_handler(MessageHandler handler) { handler_ = handler; }

    void poll() {
        HttpClient http;
        int64_t offset = 0;

        while (running_) {
            auto resp = http.get(
                "https://api.telegram.org/bot" + token_ + "/getUpdates?offset=" +
                std::to_string(offset) + "&timeout=30"
            );

            if (!resp.ok()) {
                std::cerr << "Telegram poll error: " << resp.body << "\n";
                std::this_thread::sleep_for(std::chrono::seconds(5));
                continue;
            }

            auto j = nlohmann::json::parse(resp.body);
            for (auto& update : j["result"]) {
                offset = update["update_id"].get<int64_t>() + 1;

                if (!update.contains("message") || !update["message"].contains("text"))
                    continue;

                int64_t user_id = update["message"]["from"]["id"].get<int64_t>();
                std::string text = update["message"]["text"].get<std::string>();
                int64_t chat_id = update["message"]["chat"]["id"].get<int64_t>();

                if (!allowed_users_.empty()) {
                    bool allowed = false;
                    for (auto id : allowed_users_) {
                        if (id == user_id) { allowed = true; break; }
                    }
                    if (!allowed) {
                        send_message(chat_id, "⛔ Not authorized.");
                        continue;
                    }
                }

                std::string reply = handler_ ? handler_(text, user_id) : "No handler.";
                send_message(chat_id, reply);
            }
        }
    }

    void send_message(int64_t chat_id, const std::string& text) {
        HttpClient http;
        nlohmann::json body = {
            {"chat_id", chat_id},
            {"text", text},
            {"parse_mode", "Markdown"}
        };
        http.post_json("https://api.telegram.org/bot" + token_ + "/sendMessage", body);
    }

    void stop() { running_ = false; }

private:
    std::string token_;
    std::vector<int64_t> allowed_users_;
    MessageHandler handler_;
    bool running_ = true;
};

} // namespace nonail
