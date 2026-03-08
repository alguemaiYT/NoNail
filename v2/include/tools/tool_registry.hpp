#pragma once

#include <string>
#include <vector>
#include <map>
#include <functional>
#include <nlohmann/json.hpp>

namespace nonail {

struct ToolResult {
    bool success = true;
    std::string output;
    std::string error;
};

struct ToolDef {
    std::string name;
    std::string description;
    nlohmann::json parameters;  // JSON Schema
    std::function<ToolResult(const nlohmann::json& args)> execute;
};

class ToolRegistry {
public:
    void register_tool(ToolDef tool);
    void register_defaults();

    ToolResult execute(const std::string& name, const nlohmann::json& args) const;

    std::vector<std::string> list_names() const;
    nlohmann::json to_openai_schema() const;

    bool has(const std::string& name) const;
    const ToolDef& get(const std::string& name) const;

private:
    std::map<std::string, ToolDef> tools_;
};

} // namespace nonail
