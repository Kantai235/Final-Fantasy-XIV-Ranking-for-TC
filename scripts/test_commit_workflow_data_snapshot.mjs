import assert from "node:assert/strict";
import childProcess from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const 專案根目錄 = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const 快照腳本 = path.join(專案根目錄, "scripts/commit_workflow_data_snapshot.mjs");
const 測試根目錄 = fs.mkdtempSync(path.join(os.tmpdir(), "ffxiv-workflow-data-snapshot-"));
const 遠端Repo = path.join(測試根目錄, "remote.git");
const 工作目錄 = path.join(測試根目錄, "worktree");

function 執行(指令, 參數, { cwd = 專案根目錄, allowFailure = false } = {}) {
  const result = childProcess.spawnSync(指令, 參數, {
    cwd,
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
  });
  if (result.error) {
    throw result.error;
  }
  if (!allowFailure && result.status !== 0) {
    throw new Error(
      `${指令} ${參數.join(" ")} 執行失敗（exit code ${result.status}）\n${result.stderr || result.stdout || ""}`,
    );
  }
  return result;
}

function Git(參數, 選項 = {}) {
  return 執行("git", 參數, { cwd: 選項.cwd || 工作目錄, allowFailure: 選項.allowFailure });
}

function Git輸出(參數, 選項 = {}) {
  return String(Git(參數, 選項).stdout || "").trim();
}

function 遠端Git(參數) {
  return String(執行("git", ["--git-dir", 遠端Repo, ...參數]).stdout || "").trim();
}

function 寫入(relativePath, content, cwd = 工作目錄) {
  const filePath = path.join(cwd, relativePath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content, "utf8");
}

function 執行快照({ cwd = 工作目錄, allowFailure = false, paths = ["data", "public/data"] } = {}) {
  return 執行(
    process.execPath,
    [快照腳本, "--remote", "origin", "--branch", "main", "--", ...paths],
    { cwd, allowFailure },
  );
}

function 設定人工提交身分(cwd = 工作目錄) {
  執行("git", ["config", "user.name", "fixture"], { cwd });
  執行("git", ["config", "user.email", "fixture@example.com"], { cwd });
}

function 確認尾端快照({ expectedCount, expectedParent }) {
  assert.equal(遠端Git(["rev-list", "--count", "main"]), String(expectedCount));
  assert.equal(遠端Git(["show", "-s", "--format=%P", "main"]), expectedParent);
  assert.match(遠端Git(["show", "-s", "--format=%B", "main"]), /Workflow-Data-Snapshot: v1/);
}

try {
  執行("git", ["init", "--bare", 遠端Repo]);
  執行("git", ["clone", 遠端Repo, 工作目錄]);
  設定人工提交身分();
  寫入("src/app.js", "export const version = 1;\n");
  Git(["add", "src/app.js"]);
  Git(["commit", "-m", "feat(app): 建立程式碼基準"]);
  Git(["branch", "-M", "main"]);
  Git(["push", "-u", "origin", "main"]);
  const 程式碼基準 = Git輸出(["rev-parse", "HEAD"]);

  寫入("data/rankings.json", "{\"score\":1}\n");
  寫入("public/data/status.json", "{\"ready\":true}\n");
  執行快照();
  確認尾端快照({ expectedCount: 2, expectedParent: 程式碼基準 });
  const 第一版快照 = 遠端Git(["rev-parse", "main"]);

  // 同一輪 workflow 在 payload 稽核後再次推送時，應 amend 同一筆快照而不追加 commit。
  寫入("data/pages_payload_history.jsonl", "{\"bytes\":100}\n");
  執行快照({ paths: ["data/pages_payload_history.jsonl"] });
  確認尾端快照({ expectedCount: 2, expectedParent: 程式碼基準 });
  const 第二版快照 = 遠端Git(["rev-parse", "main"]);
  assert.notEqual(第二版快照, 第一版快照);
  assert.equal(遠端Git(["show", "main:data/rankings.json"]), '{"score":1}');
  assert.equal(遠端Git(["show", "main:data/pages_payload_history.jsonl"]), '{"bytes":100}');

  // depth=1 會把目前快照視為 shallow root；腳本必須安全失敗，不能切斷程式碼 parent。
  const depthOneWorktree = path.join(測試根目錄, "depth-one-worktree");
  執行("git", ["clone", "--depth=1", "--branch", "main", pathToFileURL(遠端Repo).href, depthOneWorktree]);
  寫入("data/rankings.json", "{\"score\":999}\n", depthOneWorktree);
  const depthOneRejected = 執行快照({ cwd: depthOneWorktree, allowFailure: true });
  assert.notEqual(depthOneRejected.status, 0, "depth=1 不得執行 amend");
  assert.equal(遠端Git(["rev-parse", "main"]), 第二版快照, "depth=1 失敗不得改寫遠端");

  // 正式 workflow 使用 depth=2；下一輪排程可安全改寫尾端快照，程式碼基準 SHA 不得改變。
  const depthTwoWorktree = path.join(測試根目錄, "depth-two-worktree");
  執行("git", ["clone", "--depth=2", "--branch", "main", pathToFileURL(遠端Repo).href, depthTwoWorktree]);
  寫入("data/rankings.json", "{\"score\":2}\n", depthTwoWorktree);
  執行快照({ cwd: depthTwoWorktree });
  確認尾端快照({ expectedCount: 2, expectedParent: 程式碼基準 });
  assert.equal(遠端Git(["show", "main:data/rankings.json"]), '{"score":2}');
  assert.equal(遠端Git(["rev-parse", "main^"]), 程式碼基準);

  // 原始 fixture worktree 要先快轉到 depth=2 測試產生的新快照，才能繼續模擬人工程式碼 commit。
  Git(["fetch", "origin", "main"]);
  Git(["reset", "--hard", "origin/main"]);

  // 人工程式碼 commit 是新的安全分界：之後建立新快照，不改寫程式碼 commit。
  設定人工提交身分();
  寫入("src/app.js", "export const version = 2;\n");
  Git(["add", "src/app.js"]);
  Git(["commit", "-m", "feat(app): 更新程式碼"]);
  Git(["push", "origin", "main"]);
  const 新程式碼基準 = Git輸出(["rev-parse", "HEAD"]);
  寫入("data/rankings.json", "{\"score\":3}\n");
  執行快照();
  確認尾端快照({ expectedCount: 4, expectedParent: 新程式碼基準 });
  const 新區段快照 = 遠端Git(["rev-parse", "main"]);

  寫入("data/rankings.json", "{\"score\":4}\n");
  執行快照();
  確認尾端快照({ expectedCount: 4, expectedParent: 新程式碼基準 });
  assert.notEqual(遠端Git(["rev-parse", "main"]), 新區段快照);

  // 遠端在本輪開始後出現新程式碼 commit 時，必須拒絕 force push。
  const raceWorktree = path.join(測試根目錄, "race-worktree");
  執行("git", ["clone", "--branch", "main", 遠端Repo, raceWorktree]);
  設定人工提交身分(raceWorktree);
  寫入("src/race.js", "export const race = true;\n", raceWorktree);
  執行("git", ["add", "src/race.js"], { cwd: raceWorktree });
  執行("git", ["commit", "-m", "fix(app): 模擬並行程式碼更新"], { cwd: raceWorktree });
  執行("git", ["push", "origin", "main"], { cwd: raceWorktree });
  const raceRemoteHead = 遠端Git(["rev-parse", "main"]);

  寫入("data/rankings.json", "{\"score\":5}\n");
  const rejected = 執行快照({ allowFailure: true });
  assert.notEqual(rejected.status, 0, "遠端有新 commit 時應拒絕快照改寫");
  assert.match(`${rejected.stdout || ""}${rejected.stderr || ""}`, /拒絕改寫新程式碼 commit/);
  assert.equal(遠端Git(["rev-parse", "main"]), raceRemoteHead, "競爭保護不得覆寫遠端程式碼 commit");

  console.log("workflow 資料快照收斂、程式碼分界與 force-with-lease 競爭保護測試通過。");
} finally {
  fs.rmSync(測試根目錄, { recursive: true, force: true });
}
