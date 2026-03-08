#include "tools/tool_registry.hpp"

#include <stdexcept>
#include <cstdio>
#include <cstdlib>
#include <array>
#include <fstream>
#include <sstream>
#include <filesystem>

namespace nonail {

void ToolRegistry::register_tool(ToolDef tool) {
    tools_[tool.name] = std::move(tool);
}

bool ToolRegistry::has(const std::string& name) const {
    return tools_.count(name) > 0;
}

const ToolDef& ToolRegistry::get(const std::string& name) const {
    auto it = tools_.find(name);
    if (it == tools_.end()) throw std::runtime_error("Unknown tool: " + name);
    return it->second;
}

ToolResult ToolRegistry::execute(const std::string& name, const nlohmann::json& args) const {
    auto& tool = get(name);
    return tool.execute(args);
}

std::vector<std::string> ToolRegistry::list_names() const {
    std::vector<std::string> names;
    names.reserve(tools_.size());
    for (auto& [k, _] : tools_) names.push_back(k);
    return names;
}

nlohmann::json ToolRegistry::to_openai_schema() const {
    nlohmann::json arr = nlohmann::json::array();
    for (auto& [name, tool] : tools_) {
        arr.push_back({
            {"type", "function"},
            {"function", {
                {"name", tool.name},
                {"description", tool.description},
                {"parameters", tool.parameters}
            }}
        });
    }
    return arr;
}

void ToolRegistry::register_defaults() {
    // shell_execute — run shell commands
    register_tool({
        "shell_execute",
        "Execute a shell command and return stdout/stderr",
        {
            {"type", "object"},
            {"properties", {
                {"command", {{"type", "string"}, {"description", "Shell command to execute"}}}
            }},
            {"required", nlohmann::json::array({"command"})}
        },
        [](const nlohmann::json& args) -> ToolResult {
            std::string cmd = args.at("command").get<std::string>();
            std::array<char, 4096> buf;
            std::string output;

            FILE* pipe = popen(cmd.c_str(), "r");
            if (!pipe) return {false, "", "Failed to execute command"};

            while (fgets(buf.data(), buf.size(), pipe)) {
                output += buf.data();
            }
            int status = pclose(pipe);

            return {status == 0, output, status != 0 ? "Exit code: " + std::to_string(status) : ""};
        }
    });

    // file_read — read file contents
    register_tool({
        "file_read",
        "Read the contents of a file",
        {
            {"type", "object"},
            {"properties", {
                {"path", {{"type", "string"}, {"description", "File path to read"}}}
            }},
            {"required", nlohmann::json::array({"path"})}
        },
        [](const nlohmann::json& args) -> ToolResult {
            std::string path = args.at("path").get<std::string>();
            if (!std::filesystem::exists(path)) {
                return {false, "", "File not found: " + path};
            }
            std::ifstream ifs(path);
            std::stringstream ss;
            ss << ifs.rdbuf();
            return {true, ss.str(), ""};
        }
    });

    // file_write — write file contents
    register_tool({
        "file_write",
        "Write content to a file",
        {
            {"type", "object"},
            {"properties", {
                {"path", {{"type", "string"}, {"description", "File path"}}},
                {"content", {{"type", "string"}, {"description", "Content to write"}}}
            }},
            {"required", nlohmann::json::array({"path", "content"})}
        },
        [](const nlohmann::json& args) -> ToolResult {
            std::string path = args.at("path").get<std::string>();
            std::string content = args.at("content").get<std::string>();
            std::ofstream ofs(path);
            if (!ofs.good()) return {false, "", "Cannot write to: " + path};
            ofs << content;
            return {true, "Written " + std::to_string(content.size()) + " bytes to " + path, ""};
        }
    });

    // list_directory
    register_tool({
        "list_directory",
        "List files and directories at the given path",
        {
            {"type", "object"},
            {"properties", {
                {"path", {{"type", "string"}, {"description", "Directory path (default: .)"}}}
            }}
        },
        [](const nlohmann::json& args) -> ToolResult {
            std::string path = args.value("path", ".");
            if (!std::filesystem::exists(path)) {
                return {false, "", "Directory not found: " + path};
            }
            std::string output;
            for (auto& entry : std::filesystem::directory_iterator(path)) {
                output += entry.path().filename().string();
                if (entry.is_directory()) output += "/";
                output += "\n";
            }
            return {true, output, ""};
        }
    });
}

} // namespace nonail
