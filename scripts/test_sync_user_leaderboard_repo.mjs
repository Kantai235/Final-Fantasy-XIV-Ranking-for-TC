import assert from "node:assert/strict";
import childProcess from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const 專案根目錄 = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const 同步腳本 = path.join(專案根目錄, "scripts/sync_user_leaderboard_repo.mjs");
const 測試根目錄 = fs.mkdtempSync(path.join(os.tmpdir(), "ffxiv-user-repo-sync-"));
const 來源根目錄 = path.join(測試根目錄, "source");
const 遠端Repo = path.join(測試根目錄, "remote.git");
const 同步工作目錄 = path.join(測試根目錄, "sync-worktree");

function 執行(指令, 參數, { cwd = 專案根目錄, env = process.env } = {}) {
  const 結果 = childProcess.spawnSync(指令, 參數, {
    cwd,
    env,
    encoding: "utf8",
    maxBuffer: 16 * 1024 * 1024,
  });
  if (結果.error) {
    throw 結果.error;
  }
  if (結果.status !== 0) {
    throw new Error(
      `${指令} ${參數.join(" ")} 執行失敗（exit code ${結果.status}）\n${結果.stderr || 結果.stdout || ""}`,
    );
  }
  return `${結果.stdout || ""}${結果.stderr || ""}`;
}

function 寫入Json(relativePath, value) {
  const filePath = path.join(來源根目錄, relativePath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function 執行同步() {
  return 執行(process.execPath, [同步腳本], {
    env: {
      ...process.env,
      USER_REPO_URL: 遠端Repo,
      USER_REPO_DIR: 同步工作目錄,
      USER_DATA_SOURCE_ROOT: 來源根目錄,
      USER_REPO_BRANCH: "main",
      GITHUB_REPOSITORY: "fixture/source",
      GITHUB_REF_NAME: "main",
      GITHUB_SHA: "0123456789abcdef0123456789abcdef01234567",
      GITHUB_EVENT_NAME: "test",
    },
  });
}

function 遠端Git(參數) {
  return 執行("git", ["--git-dir", 遠端Repo, ...參數]).trim();
}

function 確認遠端只有一筆RootCommit() {
  assert.equal(遠端Git(["rev-list", "--count", "main"]), "1", "快照分支只能保留一筆可達提交");
  const commit = 遠端Git(["cat-file", "-p", "main"]);
  assert(!/^parent\s+/m.test(commit), "快照提交不可串接上一版 parent");
}

try {
  寫入Json("public/data/global_stats.json", {
    generated_at_iso: "2026-08-11T00:00:00.000Z",
    rankings_updated_at_iso: "2026-08-11T00:00:00.000Z",
    total_character_count: 1,
    total_entry_count: 1,
  });
  寫入Json("public/data/users/index.json", { schema_version: 1, total_users: 1 });
  寫入Json("public/data/users/測試玩家.json", { name: "測試玩家", score: 100 });
  寫入Json("public/data/user-entry-details/測試細節.json", { format: "user_entry_details_v1" });

  執行("git", ["init", "--bare", 遠端Repo]);

  執行同步();
  確認遠端只有一筆RootCommit();
  assert.equal(
    JSON.parse(遠端Git(["show", "main:data/users/測試玩家.json"])).score,
    100,
    "空白遠端應能收到第一版使用者資料",
  );

  // 模擬舊流程在快照上追加 commit。下一輪即使資料內容沒變，也應主動把歷史收斂回一筆。
  const legacyWorktree = path.join(測試根目錄, "legacy-worktree");
  執行("git", ["clone", "--branch", "main", 遠端Repo, legacyWorktree]);
  執行("git", ["config", "user.name", "fixture"], { cwd: legacyWorktree });
  執行("git", ["config", "user.email", "fixture@example.com"], { cwd: legacyWorktree });
  fs.writeFileSync(path.join(legacyWorktree, "README.md"), "fixture metadata\n", "utf8");
  執行("git", ["add", "README.md"], { cwd: legacyWorktree });
  執行("git", ["commit", "-m", "chore(data): 模擬舊版累積提交"], { cwd: legacyWorktree });
  執行("git", ["push", "origin", "main"], { cwd: legacyWorktree });
  assert.equal(遠端Git(["rev-list", "--count", "main"]), "2", "fixture 應先建立兩筆累積歷史");

  const 收斂輸出 = 執行同步();
  assert.match(收斂輸出, /收斂為單一快照提交/, "內容沒變時仍應執行一次歷史收斂");
  確認遠端只有一筆RootCommit();
  assert.equal(遠端Git(["show", "main:README.md"]), "fixture metadata", "非同步目標檔案應保留在最新快照");

  const 穩定Head = 遠端Git(["rev-parse", "main"]);
  執行同步();
  assert.equal(遠端Git(["rev-parse", "main"]), 穩定Head, "內容與歷史皆穩定時不應製造 metadata-only commit");

  寫入Json("public/data/users/測試玩家.json", { name: "測試玩家", score: 200 });
  執行同步();
  確認遠端只有一筆RootCommit();
  assert.notEqual(遠端Git(["rev-parse", "main"]), 穩定Head, "資料變更後應產生新的快照 commit");
  assert.equal(
    JSON.parse(遠端Git(["show", "main:data/users/測試玩家.json"])).score,
    200,
    "新快照應包含最新使用者資料",
  );

  console.log("sync_user_leaderboard_repo 單一快照、空白遠端與歷史收斂測試通過。");
} finally {
  fs.rmSync(測試根目錄, { recursive: true, force: true });
}
