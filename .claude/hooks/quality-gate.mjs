// Claude Code PostToolUse hook: lint every file Claude edits, the moment it is written.
// Exit code 2 sends the violations back to Claude, which then fixes them before moving on.
// The rules are the same as in pre-commit and CI (backend/pyproject.toml, frontend/eslint.config.js).
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

const input = JSON.parse(readFileSync(0, "utf8"));
const file = input.tool_input?.file_path;
if (!file) process.exit(0);

const root = process.env.CLAUDE_PROJECT_DIR ?? process.cwd();
const relative = path.relative(root, path.resolve(file)).split(path.sep).join("/");

function check(cwd, command, args) {
  const result = spawnSync(command, args, { cwd: path.join(root, cwd), encoding: "utf8" }); // no shell: args are never interpolated
  if (result.status !== 0) {
    process.stderr.write(`Quality gate failed for ${relative}:\n${result.stdout}${result.stderr}`);
    process.exit(2);
  }
}

if (/^backend\/.*\.py$/.test(relative)) {
  const target = relative.slice("backend/".length);
  check("backend", "uv", ["run", "ruff", "check", "--output-format", "concise", target]);
  check("backend", "uv", ["run", "ruff", "format", "--check", target]);
} else if (/^frontend\/(src|e2e)\/.*\.tsx?$/.test(relative)) {
  const eslint = path.join("node_modules", "eslint", "bin", "eslint.js");
  check("frontend", process.execPath, [eslint, "--max-warnings", "0", relative.slice("frontend/".length)]);
}
