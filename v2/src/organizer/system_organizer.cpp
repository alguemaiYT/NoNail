#include "organizer/system_organizer.hpp"
#include "providers/provider.hpp"

#include <iostream>
#include <sstream>
#include <algorithm>
#include <cstdlib>
#include <nlohmann/json.hpp>

namespace fs = std::filesystem;

namespace nonail {

// Directories to always skip (large, noisy, or system-managed)
static const std::vector<std::string> SKIP_DIRS = {
    "NoNail", "node_modules", "__pycache__", "snap",
    "Qt", "qtcreator-18.0.2", ".cache", ".local", ".config"
};

static bool should_skip(const std::string& name) {
    if (name.empty() || name[0] == '.') return true;
    for (auto& s : SKIP_DIRS) {
        if (name == s) return true;
    }
    return false;
}

// ---------------------------------------------------------------------------

SystemOrganizer::SystemOrganizer(const Config& cfg) : cfg_(cfg) {}

std::vector<fs::path> SystemOrganizer::list_candidates(const fs::path& target_dir) const {
    fs::path dir = target_dir.empty()
        ? fs::path(std::getenv("HOME") ? std::getenv("HOME") : "/home")
        : target_dir;

    std::vector<fs::path> result;
    std::error_code ec;
    for (auto& entry : fs::directory_iterator(dir, ec)) {
        auto name = entry.path().filename().string();
        if (should_skip(name)) continue;
        if (entry.is_regular_file(ec)) {
            result.push_back(entry.path());
        }
    }
    std::sort(result.begin(), result.end());
    return result;
}

std::string SystemOrganizer::build_dir_summary(const fs::path& dir) const {
    std::ostringstream ss;
    ss << "=== Loose files in " << dir.string() << " ===\n";

    auto candidates = list_candidates(dir);
    for (auto& p : candidates) {
        ss << "  FILE: " << p.filename().string() << "\n";
    }

    ss << "\n=== Directories in " << dir.string() << " ===\n";
    std::error_code ec;
    std::vector<std::string> dirs;
    for (auto& entry : fs::directory_iterator(dir, ec)) {
        auto name = entry.path().filename().string();
        if (should_skip(name)) continue;
        if (entry.is_directory(ec)) dirs.push_back(name);
    }
    std::sort(dirs.begin(), dirs.end());
    for (auto& d : dirs) {
        // List a few child entries as context
        std::vector<std::string> children;
        std::error_code ec2;
        for (auto& c : fs::directory_iterator(dir / d, ec2)) {
            children.push_back(c.path().filename().string());
            if (children.size() >= 5) { children.push_back("..."); break; }
        }
        ss << "  DIR: " << d;
        if (!children.empty()) {
            ss << "  [";
            for (size_t i = 0; i < children.size(); ++i) {
                if (i) ss << ", ";
                ss << children[i];
            }
            ss << "]";
        }
        ss << "\n";
    }

    return ss.str();
}

// ---------------------------------------------------------------------------
// Ask the provider for a move plan
// ---------------------------------------------------------------------------

std::vector<MoveOp> SystemOrganizer::plan(const std::string& dir_summary,
                                           const fs::path& base) const {
    auto provider = create_provider(cfg_.provider, cfg_.api_key, cfg_.api_base);

    std::string prompt =
        "You are organizing the directory: " + base.string() + "\n\n"
        "Here is the current state:\n" + dir_summary + "\n\n"
        "Rules:\n"
        "- Only move loose files at the root level (FILE: entries)\n"
        "- Group into EXISTING subdirectories when the file clearly belongs\n"
        "- Create new subdirs only when a clear category has 2+ files: "
        "Screenshots/, Audio/, Archives/, Misc/, Pictures/\n"
        "- Do NOT suggest moving directories, only files\n"
        "- Do NOT touch dotfiles or anything inside NoNail/\n"
        "- If the file clearly belongs where it is, omit it\n\n"
        "Respond ONLY with a valid JSON array. No text before or after.\n"
        "Format:\n"
        "[\n"
        "  {\"from\": \"filename.ext\", \"to\": \"SubDir/filename.ext\", \"reason\": \"short reason\"},\n"
        "  ...\n"
        "]\n"
        "Use relative paths (no leading /).";

    std::vector<Message> msgs = {
        {"user", prompt, "", {}}
    };

    Message resp = provider->complete(msgs, cfg_.model, 0.2, 2048);
    std::string content = resp.content;

    // Extract JSON array from response
    auto start = content.find('[');
    auto end   = content.rfind(']');
    if (start == std::string::npos || end == std::string::npos || end <= start) {
        std::cerr << "⚠️  AI response did not contain a JSON array.\n";
        return {};
    }

    try {
        auto j = nlohmann::json::parse(content.substr(start, end - start + 1));
        std::vector<MoveOp> ops;
        for (auto& item : j) {
            MoveOp op;
            op.from   = base / item.at("from").get<std::string>();
            op.to     = base / item.at("to").get<std::string>();
            op.reason = item.value("reason", "");
            ops.push_back(op);
        }
        return ops;
    } catch (std::exception& e) {
        std::cerr << "⚠️  JSON parse error: " << e.what() << "\n";
        return {};
    }
}

// ---------------------------------------------------------------------------
// Apply a single move
// ---------------------------------------------------------------------------

std::string SystemOrganizer::apply_move(const MoveOp& op, bool dry_run) const {
    std::error_code ec;

    // Guard: source must exist
    if (!fs::exists(op.from, ec)) {
        return "Source not found: " + op.from.string();
    }
    // Guard: never overwrite an existing file
    if (fs::exists(op.to, ec)) {
        return "Destination already exists: " + op.to.string();
    }

    if (dry_run) return {};  // success in dry-run

    // Ensure destination directory exists
    fs::create_directories(op.to.parent_path(), ec);
    if (ec) return "mkdir failed: " + ec.message();

    fs::rename(op.from, op.to, ec);
    if (ec) return "rename failed: " + ec.message();

    return {};  // success
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

OrganizerResult SystemOrganizer::organize(const fs::path& target_dir, bool dry_run) {
    fs::path base = target_dir.empty()
        ? fs::path(std::getenv("HOME") ? std::getenv("HOME") : "/home")
        : target_dir;

    std::string summary = build_dir_summary(base);

    std::cout << "\n[organizer] Consulting " << cfg_.provider << " (" << cfg_.model
              << ") for organization plan...\n";

    auto ops = plan(summary, base);

    if (ops.empty()) {
        std::cout << "[organizer] No moves suggested -- directory may already be tidy.\n";
        return {};
    }

    std::cout << "\n>> Plan (" << ops.size() << " move"
              << (ops.size() != 1 ? "s" : "") << "):\n";
    std::cout << std::string(60, '-') << "\n";
    for (auto& op : ops) {
        std::cout << "  " << op.from.filename().string()
                  << "  ->  " << op.to.parent_path().filename().string() << "/\n";
        if (!op.reason.empty())
            std::cout << "      " << op.reason << "\n";
    }
    std::cout << std::string(60, '-') << "\n";

    if (dry_run) {
        std::cout << "\n[dry-run] No files were moved.\n";
        OrganizerResult r;
        r.skipped = static_cast<int>(ops.size());
        return r;
    }

    std::cout << "\n[executing]\n";
    OrganizerResult result;
    for (auto& op : ops) {
        std::string err = apply_move(op, false);
        if (err.empty()) {
            std::cout << "  OK  " << op.from.filename().string()
                      << "  ->  " << op.to.parent_path().filename().string() << "/\n";
            ++result.moved;
        } else {
            std::cout << "  FAIL  " << op.from.filename().string()
                      << "  --  " << err << "\n";
            ++result.failed;
            result.errors.push_back(err);
        }
    }

    std::cout << "\n" << std::string(60, '=') << "\n";
    std::cout << "  Done: " << result.moved << " moved";
    if (result.failed) std::cout << ", " << result.failed << " failed";
    std::cout << "\n" << std::string(60, '=') << "\n";

    return result;
}

} // namespace nonail
