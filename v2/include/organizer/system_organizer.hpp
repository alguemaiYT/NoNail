#pragma once

#include "core/config.hpp"
#include <filesystem>
#include <string>
#include <vector>

namespace nonail {

struct MoveOp {
    std::filesystem::path from;
    std::filesystem::path to;
    std::string reason;
};

struct OrganizerResult {
    int moved = 0;
    int failed = 0;
    int skipped = 0;   // dry-run count
    std::vector<std::string> errors;
};

class SystemOrganizer {
public:
    explicit SystemOrganizer(const Config& cfg);

    // Collect candidate files from target_dir (non-hidden, depth=1, files only)
    std::vector<std::filesystem::path> list_candidates(
        const std::filesystem::path& target_dir = ""
    ) const;

    // Ask the LLM for a JSON move plan, then apply (or preview) the moves.
    // Returns a result summary.
    OrganizerResult organize(
        const std::filesystem::path& target_dir = "",
        bool dry_run = false
    );

private:
    Config cfg_;

    std::string build_dir_summary(const std::filesystem::path& dir) const;
    std::vector<MoveOp> plan(const std::string& dir_summary,
                              const std::filesystem::path& base) const;
    std::string apply_move(const MoveOp& op, bool dry_run) const;
};

} // namespace nonail
