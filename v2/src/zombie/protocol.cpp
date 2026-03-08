#include <nlohmann/json.hpp>
#include <string>
#include <ctime>

namespace nonail {

// Simple zombie protocol message types
enum class MsgType {
    AUTH,
    AUTH_OK,
    AUTH_FAIL,
    PING,
    PONG,
    COMMAND,
    RESULT,
    STATUS,
    ERROR
};

struct ZombieMessage {
    MsgType type;
    std::string payload;
    std::string sender;
    double timestamp = 0.0;

    std::string serialize() const {
        nlohmann::json j = {
            {"type", static_cast<int>(type)},
            {"payload", payload},
            {"sender", sender},
            {"timestamp", timestamp > 0 ? timestamp : static_cast<double>(std::time(nullptr))}
        };
        return j.dump() + "\n";
    }

    static ZombieMessage deserialize(const std::string& data) {
        auto j = nlohmann::json::parse(data);
        ZombieMessage msg;
        msg.type = static_cast<MsgType>(j.at("type").get<int>());
        msg.payload = j.value("payload", "");
        msg.sender = j.value("sender", "");
        msg.timestamp = j.value("timestamp", 0.0);
        return msg;
    }
};

} // namespace nonail
