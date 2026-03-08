#include "core/http_client.hpp"
#include <nlohmann/json.hpp>
#include <iostream>
#include <cstring>

namespace nonail {

class WhatsAppBot {
public:
    WhatsAppBot(const std::string& account_sid,
                const std::string& auth_token,
                const std::string& from_number,
                const std::vector<std::string>& allowed_numbers = {})
        : account_sid_(account_sid)
        , auth_token_(auth_token)
        , from_number_(from_number)
        , allowed_numbers_(allowed_numbers)
    {}

    void send_message(const std::string& to, const std::string& body) {
        HttpClient http;
        std::string url = "https://api.twilio.com/2010-04-01/Accounts/" +
            account_sid_ + "/Messages.json";

        std::string form_data =
            "From=whatsapp%3A" + url_encode(from_number_) +
            "&To=whatsapp%3A" + url_encode(to) +
            "&Body=" + url_encode(body);

        http.request("POST", url, form_data, {
            {"Authorization", "Basic " + base64_encode(account_sid_ + ":" + auth_token_)},
            {"Content-Type", "application/x-www-form-urlencoded"}
        });
    }

private:
    std::string account_sid_;
    std::string auth_token_;
    std::string from_number_;
    std::vector<std::string> allowed_numbers_;

    static std::string url_encode(const std::string& s) {
        std::string result;
        for (unsigned char c : s) {
            if (isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') {
                result += static_cast<char>(c);
            } else {
                char buf[4];
                snprintf(buf, sizeof(buf), "%%%02X", c);
                result += buf;
            }
        }
        return result;
    }

    static std::string base64_encode(const std::string& input) {
        static const char t[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        std::string o;
        int i = 0;
        unsigned char a3[3], a4[4];
        for (size_t n = 0; n < input.size(); ++n) {
            a3[i++] = static_cast<unsigned char>(input[n]);
            if (i == 3) {
                a4[0] = (a3[0] & 0xfc) >> 2;
                a4[1] = ((a3[0] & 0x03) << 4) + ((a3[1] & 0xf0) >> 4);
                a4[2] = ((a3[1] & 0x0f) << 2) + ((a3[2] & 0xc0) >> 6);
                a4[3] = a3[2] & 0x3f;
                for (int j = 0; j < 4; j++) o += t[a4[j]];
                i = 0;
            }
        }
        if (i) {
            for (int j = i; j < 3; j++) a3[j] = 0;
            a4[0] = (a3[0] & 0xfc) >> 2;
            a4[1] = ((a3[0] & 0x03) << 4) + ((a3[1] & 0xf0) >> 4);
            a4[2] = ((a3[1] & 0x0f) << 2) + ((a3[2] & 0xc0) >> 6);
            for (int j = 0; j < i + 1; j++) o += t[a4[j]];
            while (i++ < 3) o += '=';
        }
        return o;
    }
};

} // namespace nonail
