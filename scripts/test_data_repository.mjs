import assert from "node:assert/strict";
import childProcess from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const 專案根目錄 = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const 工具 = path.join(專案根目錄, "scripts/data_repository.mjs");
const 測試根目錄 = fs.mkdtempSync(path.join(os.tmpdir(), "ffxiv-data-repo-"));
const 來源目錄 = path.join(測試根目錄, "source");
const 還原目錄 = path.join(測試根目錄, "hydrate-target");
const Data工作目錄 = path.join(測試根目錄, "data-worktree");
const 還原Data工作目錄 = path.join(測試根目錄, "hydrate-data-worktree");
const 遠端Repo = path.join(測試根目錄, "remote.git");

function 執行(command, args, { cwd = 專案根目錄, env = process.env, allowFailure = false } = {}) {
  const result = childProcess.spawnSync(command, args, {
    cwd,
    env,
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  });
  if (result.error) {
    throw result.error;
  }
  if (!allowFailure && result.status !== 0) {
    throw new Error(
      `${command} ${args.join(" ")} 執行失敗（exit code ${result.status}）\n${result.stderr || result.stdout || ""}`,
    );
  }
  return result;
}

function 寫入(root, relativePath, content) {
  const filePath = path.join(root, relativePath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content, "utf8");
}

function 寫入必要Fixture(root, score = 100) {
  寫入(root, "data/state.json", JSON.stringify({ schema_version: 1, score }));
  寫入(root, "data/update_status.json", JSON.stringify({ schema_version: 1 }));
  寫入(root, "data/pages_payload_history.jsonl", `${JSON.stringify({ bytes: score })}\n`);
  寫入(root, "data/rankings/test.json", JSON.stringify({ ranking_entries: [{ score }] }));
  寫入(
    root,
    "data/rankings/test.reports/000.json",
    JSON.stringify({
      REPORT: {
        fights: [
          {
            fight_id: 1,
            players: [{ name: "測試玩家", server: "陸行鳥", job: "Paladin", fflogs_id: 1 }],
          },
        ],
      },
    }),
  );
  寫入(root, "data/state/checked_reports/test.json", JSON.stringify({ REPORT: { status: "processed" } }));
  寫入(
    root,
    "data/fun/honey_b_fans.json",
    JSON.stringify({
      score,
      records: [{ id: "HONEY:1", score }],
      state: {
        checked_fights: { "HONEY:1": { status: "checked" } },
        checked_reports: { HONEY: { status: "checked" } },
      },
    }),
  );
  寫入(root, "public/data/announcements.json", "[]");
  寫入(root, "public/data/encounters.json", "[]");
  寫入(root, "public/data/global_stats.json", JSON.stringify({ total_character_count: score }));
  寫入(root, "public/data/update_status.json", JSON.stringify({ schema_version: 1 }));
  寫入(root, "public/data/fun/honey_b_fans.json", JSON.stringify({ score }));
}

function 工具Env(sourceRoot, repoDir) {
  return {
    ...process.env,
    DATA_REPO_URL: 遠端Repo,
    DATA_REPO_DIR: repoDir,
    DATA_SOURCE_ROOT: sourceRoot,
    DATA_REPO_BRANCH: "main",
    DATA_REPO: "fixture/data",
    GITHUB_REPOSITORY: "fixture/main",
    GITHUB_REF_NAME: "main",
    GITHUB_SHA: "0123456789abcdef0123456789abcdef01234567",
    GITHUB_EVENT_NAME: "test",
  };
}

function 執行工具(
  command,
  sourceRoot = 來源目錄,
  repoDir = Data工作目錄,
  extraArgs = [],
  allowFailure = false,
) {
  return 執行(process.execPath, [工具, command, ...extraArgs], {
    env: 工具Env(sourceRoot, repoDir),
    allowFailure,
  });
}

function 遠端Git(args) {
  return String(執行("git", ["--git-dir", 遠端Repo, ...args]).stdout || "").trim();
}

try {
  執行("git", ["init", "--bare", 遠端Repo]);
  寫入必要Fixture(來源目錄, 100);
  寫入(來源目錄, "data/local-cache/measurements.json", "不應發布");
  寫入(來源目錄, "data/shallow_scan_cache/cache.json", "不應發布");
  寫入(來源目錄, "data/.state.json.123.tmp", "不應發布");
  寫入(來源目錄, "public/data/users/玩家.json", "不應發布");
  寫入(來源目錄, "public/data/user-entry-details/detail.json", "不應發布");
  寫入(來源目錄, "public/data/rankings/test.json", "不應發布");

  執行工具("publish");
  assert.equal(遠端Git(["rev-list", "--count", "main"]), "1", "Data repo 只能保留一筆可達提交");
  assert.equal(遠端Git(["show", "-s", "--format=%P", "main"]), "", "Data snapshot 不可有 parent");
  assert.equal(JSON.parse(遠端Git(["show", "main:data/state.json"])).score, 100);
  assert.equal(JSON.parse(遠端Git(["show", "main:public/data/global_stats.json"])).total_character_count, 100);
  assert.equal(
    執行("git", ["--git-dir", 遠端Repo, "cat-file", "-e", "main:data/local-cache/measurements.json"], {
      allowFailure: true,
    }).status,
    128,
    "本機快取不可進入 Data repo",
  );
  assert.equal(
    執行("git", ["--git-dir", 遠端Repo, "cat-file", "-e", "main:public/data/users/玩家.json"], {
      allowFailure: true,
    }).status,
    128,
    "個別玩家資料不可重複進入 Data repo",
  );

  const stableHead = 遠端Git(["rev-parse", "main"]);
  執行工具("publish");
  assert.equal(遠端Git(["rev-parse", "main"]), stableHead, "內容未變時不可製造新 snapshot");

  寫入必要Fixture(來源目錄, 200);
  執行工具("publish");
  const updatedHead = 遠端Git(["rev-parse", "main"]);
  assert.notEqual(updatedHead, stableHead, "資料變更後應建立新 root snapshot");
  assert.equal(遠端Git(["rev-list", "--count", "main"]), "1", "更新後仍只能有一筆可達提交");
  assert.equal(JSON.parse(遠端Git(["show", "main:data/state.json"])).score, 200);

  寫入(
    來源目錄,
    "data/fun/honey_b_fans.json",
    JSON.stringify({ score: 200, records: [], state: { checked_fights: {}, checked_reports: {} } }),
  );
  const honeyRemovalResult = 執行工具("publish", 來源目錄, Data工作目錄, [], true);
  assert.notEqual(honeyRemovalResult.status, 0, "遺失既有趣味榜歷史時必須拒絕發布");
  assert.match(honeyRemovalResult.stderr, /趣味榜|honey_b_fans/u);
  assert.equal(遠端Git(["rev-parse", "main"]), updatedHead, "趣味榜守恆失敗不可更新遠端");
  寫入必要Fixture(來源目錄, 200);

  寫入(
    來源目錄,
    "data/rankings/test.reports/000.json",
    JSON.stringify({ REPORT: { fights: [{ fight_id: 1, players: [] }] } }),
  );
  const removalResult = 執行工具("publish", 來源目錄, Data工作目錄, [], true);
  assert.notEqual(removalResult.status, 0, "遺失既有玩家時必須拒絕發布");
  assert.match(removalResult.stderr, /玩家.+已遺失/u);
  assert.equal(遠端Git(["rev-parse", "main"]), updatedHead, "守恆失敗不可更新遠端");
  寫入必要Fixture(來源目錄, 200);

  寫入(還原目錄, "data/local-cache/keep.json", "保留快取");
  寫入(還原目錄, "data/rankings/stale.json", "刪除舊資料");
  寫入(還原目錄, "public/data/users/local.json", "保留 Users 衍生資料");
  執行工具("hydrate", 還原目錄, 還原Data工作目錄, ["--force"]);
  assert.equal(JSON.parse(fs.readFileSync(path.join(還原目錄, "data/state.json"), "utf8")).score, 200);
  assert(!fs.existsSync(path.join(還原目錄, "data/rankings/stale.json")), "hydrate 必須清除舊受管理資料");
  assert(fs.existsSync(path.join(還原目錄, "data/local-cache/keep.json")), "hydrate 不可刪除本機快取");
  assert(fs.existsSync(path.join(還原目錄, "public/data/users/local.json")), "hydrate 不可刪除 Users 衍生資料");

  執行工具("verify", 還原目錄, 還原Data工作目錄);
  console.log("Data repo 單一 root snapshot、排除規則、hydrate 與 manifest 驗證測試通過。");
} finally {
  fs.rmSync(測試根目錄, { recursive: true, force: true });
}
