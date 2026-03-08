#include "core/agent.hpp"
#include "core/config.hpp"
#include "organizer/system_organizer.hpp"

#include <iostream>
#include <string>
#include <cstring>
#include <thread>

#ifdef NONAIL_WEB
#include "web/server.hpp"
#endif

#ifdef NONAIL_ZOMBIE
#include "zombie/master.hpp"
#endif

#ifdef NONAIL_DEVICES
#include "devices/device_manager.hpp"
#endif

static void print_usage() {
    std::cout << "Usage: nonail <command> [options]\n\n"
              << "Commands:\n"
              << "  chat                  Start interactive chat\n"
              << "  run <message>         Send a single message\n"
#ifdef NONAIL_WEB
              << "  web [--port PORT]     Start web UI server\n"
#endif
#ifdef NONAIL_ZOMBIE
              << "  zombie master         Start zombie master\n"
              << "  zombie slave           Connect as zombie slave\n"
#endif
#ifdef NONAIL_DEVICES
              << "  devices scan          Scan network for devices\n"
              << "  devices exec <ip> <cmd>  Execute command on device\n"
#endif
              << "  config                Show configuration\n"
              << "  organize home [--dry-run]  AI-powered home dir organizer\n"
              << "  help                  Show this help\n"
              << "  version               Show version\n\n"
              << "Config: ~/.nonail/config.json\n";
}

static void cmd_chat(nonail::Config& cfg) {
    if (cfg.api_key.empty()) {
        std::cerr << "❌ No API key. Set OPENAI_API_KEY or configure ~/.nonail/config.json\n";
        return;
    }
    nonail::Agent agent(cfg);

#ifdef NONAIL_WEB
    // Start web server in background if enabled
    std::unique_ptr<nonail::WebServer> web;
    std::thread web_thread;
    if (cfg.web.enabled) {
        web = std::make_unique<nonail::WebServer>(agent);
        web_thread = std::thread([&web, &cfg]() {
            web->start(cfg.web.bind_address, cfg.web.port);
        });
        web_thread.detach();
    }
#endif

    agent.chat_loop();
}

static void cmd_run(nonail::Config& cfg, const std::string& message) {
    if (cfg.api_key.empty()) {
        std::cerr << "❌ No API key.\n";
        return;
    }
    nonail::Agent agent(cfg);
    std::string reply = agent.step(message);
    std::cout << reply << "\n";
}

#ifdef NONAIL_WEB
static void cmd_web(nonail::Config& cfg, int port) {
    if (cfg.api_key.empty()) {
        std::cerr << "❌ No API key.\n";
        return;
    }
    nonail::Agent agent(cfg);
    nonail::WebServer server(agent);
    server.start(cfg.web.bind_address, port > 0 ? port : cfg.web.port);
}
#endif

#ifdef NONAIL_ZOMBIE
static void cmd_zombie_master(nonail::Config& cfg) {
    nonail::ZombieMaster master(cfg.zombie.password, cfg.zombie.bind_address, cfg.zombie.port);
    master.run();
}

static void cmd_zombie_slave(nonail::Config& cfg, const std::string& host, int port, const std::string& password) {
    nonail::ZombieSlave slave(host, port, password);
    slave.run();
}
#endif

#ifdef NONAIL_DEVICES
static void cmd_devices_scan() {
    nonail::DeviceManager dm;
    auto devices = dm.scan();
    std::cout << "Found " << devices.size() << " device(s):\n\n";
    std::cout << "IP              MAC                Hostname         Reachable\n";
    std::cout << "──────────────  ─────────────────  ───────────────  ─────────\n";
    for (auto& d : devices) {
        printf("%-15s %-18s %-16s %s\n",
            d.ip.c_str(), d.mac.c_str(),
            d.hostname.empty() ? "-" : d.hostname.c_str(),
            d.reachable ? "✅" : "❌");
    }
}

static void cmd_devices_exec(const std::string& ip, const std::string& cmd) {
    nonail::DeviceManager dm;
    std::string output = dm.ssh_exec(ip, cmd);
    std::cout << output;
}
#endif

static void cmd_organize(nonail::Config& cfg, bool dry_run) {
    if (cfg.api_key.empty()) {
        std::cerr << "❌ No API key configured.\n";
        return;
    }

    const char* home = std::getenv("HOME");
    std::string target = home ? home : "/home";

    std::cout << "\n📂 Target directory: " << target << "\n";
    std::cout << "🔌 Provider: " << cfg.provider << " / " << cfg.model << "\n";
    if (dry_run) {
        std::cout << "[dry-run mode — no files will be moved]\n";
    }

    std::cout << "\nProceed? [y/N] ";
    std::string answer;
    std::getline(std::cin, answer);
    if (answer != "y" && answer != "Y") {
        std::cout << "Aborted.\n";
        return;
    }

    nonail::SystemOrganizer organizer(cfg);
    organizer.organize(target, dry_run);
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        print_usage();
        return 0;
    }

    std::string cmd = argv[1];

    if (cmd == "help" || cmd == "--help" || cmd == "-h") {
        print_usage();
        return 0;
    }
    if (cmd == "version" || cmd == "--version") {
        std::cout << "nonail v0.2.0 (C++ edition)\n";
        return 0;
    }

    auto cfg = nonail::Config::load();

    if (cmd == "chat") {
        cmd_chat(cfg);
    } else if (cmd == "run") {
        if (argc < 3) {
            std::cerr << "Usage: nonail run <message>\n";
            return 1;
        }
        std::string message;
        for (int i = 2; i < argc; ++i) {
            if (i > 2) message += " ";
            message += argv[i];
        }
        cmd_run(cfg, message);
    } else if (cmd == "config") {
        std::cout << cfg.to_json().dump(2) << "\n";
    } else if (cmd == "organize") {
        bool dry_run = false;
        for (int i = 2; i < argc; ++i) {
            if (std::string(argv[i]) == "--dry-run") dry_run = true;
        }
        cmd_organize(cfg, dry_run);
#ifdef NONAIL_WEB
    } else if (cmd == "web") {
        int port = 0;
        for (int i = 2; i < argc - 1; ++i) {
            if (std::string(argv[i]) == "--port") port = std::stoi(argv[i + 1]);
        }
        cmd_web(cfg, port);
#endif
#ifdef NONAIL_ZOMBIE
    } else if (cmd == "zombie") {
        if (argc < 3) {
            std::cerr << "Usage: nonail zombie <master|slave> [options]\n";
            return 1;
        }
        std::string sub = argv[2];
        if (sub == "master") {
            cmd_zombie_master(cfg);
        } else if (sub == "slave") {
            std::string host = "127.0.0.1";
            int port = cfg.zombie.port;
            std::string password = cfg.zombie.password;
            for (int i = 3; i < argc - 1; ++i) {
                if (std::string(argv[i]) == "--host") host = argv[i + 1];
                if (std::string(argv[i]) == "--port") port = std::stoi(argv[i + 1]);
                if (std::string(argv[i]) == "--password") password = argv[i + 1];
            }
            cmd_zombie_slave(cfg, host, port, password);
        }
#endif
#ifdef NONAIL_DEVICES
    } else if (cmd == "devices") {
        if (argc < 3) {
            std::cerr << "Usage: nonail devices <scan|exec> [options]\n";
            return 1;
        }
        std::string sub = argv[2];
        if (sub == "scan") {
            cmd_devices_scan();
        } else if (sub == "exec") {
            if (argc < 5) {
                std::cerr << "Usage: nonail devices exec <ip> <command>\n";
                return 1;
            }
            std::string ip = argv[3];
            std::string command;
            for (int i = 4; i < argc; ++i) {
                if (i > 4) command += " ";
                command += argv[i];
            }
            cmd_devices_exec(ip, command);
        }
#endif
    } else {
        std::cerr << "Unknown command: " << cmd << "\n";
        print_usage();
        return 1;
    }

    return 0;
}
