import assert from "node:assert/strict";
import childProcess from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const 專案根目錄 = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const 工具 = path.join(專案根目錄, "scripts/data_repository.mjs");
const 測試根目錄 = fs.mkdtempSync(path.join(os.tmpdir(), "ffxiv-data-repo-"));
const 來源目錄 = path.join(測試根目錄, "source");
const 還原目錄 = path.join(測試根目錄, "hydrate-target");
const Data工作目錄 = path.join(測試根目錄, "data-worktree");
const 還原Data工作目錄 = path.join(測試根目錄, "hydrate-data-worktree");
const Partial還原目錄 = path.join(測試根目錄, "partial-hydrate-target");
const PartialData工作目錄 = path.join(測試根目錄, "partial-data-worktree");
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
  // 實際 payload history 曾從 Windows 工作目錄以 CRLF 進入 Ubuntu workflow。
  // fixture 固定保留 CRLF，避免測試只覆蓋單一作業系統的換行語意。
  寫入(
    root,
    "data/pages_payload_history.jsonl",
    `${JSON.stringify({ bytes: score, sample: 1 })}\r\n${JSON.stringify({ bytes: score, sample: 2 })}\r\n`,
  );
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
  // 混合換行無法只從被正規化的 LF blob 反推，修復時必須改用
  // 大小與 SHA-256 同時命中 manifest 的原始來源檔。
  寫入(root, "public/data/announcements.json", '[\r\n  {"id":"one"},\n  {"id":"two"}\r\n]\n');
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
  assert.match(遠端Git(["show", "main:.gitattributes"]), /\* -text/u);
  assert.match(遠端Git(["show", "main:data/pages_payload_history.jsonl"]), /\r\n/u);
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

  // 模擬 Git clean filter 曾造成的快照：manifest 仍記錄 CRLF 原始位元組，
  // commit blob 卻被正規化為 LF。repair-eol 只有在還原後大小與 SHA-256
  // 完全命中 manifest 時才能重建 root snapshot。
  const originalHistory = 遠端Git(["show", "main:data/pages_payload_history.jsonl"]);
  const originalAnnouncements = 遠端Git(["show", "main:public/data/announcements.json"]);
  const corruptHistoryPath = path.join(測試根目錄, "normalized-pages-payload-history.jsonl");
  const corruptAnnouncementsPath = path.join(測試根目錄, "normalized-announcements.json");
  fs.writeFileSync(corruptHistoryPath, `${originalHistory.replaceAll("\r\n", "\n")}\n`, "utf8");
  fs.writeFileSync(corruptAnnouncementsPath, `${originalAnnouncements.replaceAll("\r\n", "\n")}\n`, "utf8");
  const corruptIndexPath = path.join(測試根目錄, "corrupt-data-repo.index");
  const corruptGitEnv = {
    ...process.env,
    GIT_INDEX_FILE: corruptIndexPath,
    GIT_AUTHOR_NAME: "fixture",
    GIT_AUTHOR_EMAIL: "fixture@example.invalid",
    GIT_COMMITTER_NAME: "fixture",
    GIT_COMMITTER_EMAIL: "fixture@example.invalid",
  };
  執行("git", ["--git-dir", 遠端Repo, "read-tree", "main"], { env: corruptGitEnv });
  const corruptBlob = String(
    執行(
      "git",
      [
        "--git-dir",
        遠端Repo,
        "hash-object",
        "-w",
        "--no-filters",
        "--",
        corruptHistoryPath,
      ],
      { env: corruptGitEnv },
    ).stdout || "",
  ).trim();
  const corruptAnnouncementsBlob = String(
    執行(
      "git",
      [
        "--git-dir",
        遠端Repo,
        "hash-object",
        "-w",
        "--no-filters",
        "--",
        corruptAnnouncementsPath,
      ],
      { env: corruptGitEnv },
    ).stdout || "",
  ).trim();
  執行(
    "git",
    [
      "--git-dir",
      遠端Repo,
      "update-index",
      "--add",
      "--cacheinfo",
      `100644,${corruptBlob},data/pages_payload_history.jsonl`,
    ],
    { env: corruptGitEnv },
  );
  執行(
    "git",
    [
      "--git-dir",
      遠端Repo,
      "update-index",
      "--add",
      "--cacheinfo",
      `100644,${corruptAnnouncementsBlob},public/data/announcements.json`,
    ],
    { env: corruptGitEnv },
  );
  const corruptTree = String(
    執行("git", ["--git-dir", 遠端Repo, "write-tree"], { env: corruptGitEnv }).stdout || "",
  ).trim();
  const corruptCommit = String(
    執行(
      "git",
      ["--git-dir", 遠端Repo, "commit-tree", corruptTree, "-m", "fixture: normalize eol"],
      { env: corruptGitEnv },
    ).stdout || "",
  ).trim();
  執行("git", ["--git-dir", 遠端Repo, "update-ref", "refs/heads/main", corruptCommit, updatedHead]);
  const invalidVerifyResult = 執行工具("verify", 來源目錄, Data工作目錄, [], true);
  assert.notEqual(invalidVerifyResult.status, 0, "manifest 與 blob 換行不一致時必須拒絕驗證");
  assert.match(invalidVerifyResult.stderr, /pages_payload_history\.jsonl/u);
  執行工具("repair-eol");
  const repairedHead = 遠端Git(["rev-parse", "main"]);
  assert.notEqual(repairedHead, corruptCommit, "換行修復必須建立新的 root snapshot");
  assert.equal(遠端Git(["rev-list", "--count", "main"]), "1", "修復後仍只保留單一 root commit");
  assert.equal(遠端Git(["show", "main:data/pages_payload_history.jsonl"]), originalHistory);
  assert.equal(遠端Git(["show", "main:public/data/announcements.json"]), originalAnnouncements);
  執行工具("verify");

  // 2026-08 前的同步工具曾把 .data-repo 建成 blob:none promisor repo。即使後續
  // fetch 加上 --no-filter，Git 仍可能因為 commit 已存在而不補傳缺少的 blob，
  // 最後在 reset --hard 才隱性連網。這裡用真正的 partial clone 重現舊快取，
  // 確保 hydrate 會在下載階段用 --refetch 補齊並移除 promisor 設定。
  執行("git", ["--git-dir", 遠端Repo, "config", "uploadpack.allowFilter", "true"]);
  fs.mkdirSync(PartialData工作目錄, { recursive: true });
  執行("git", ["init", "-q"], { cwd: PartialData工作目錄 });
  const 遠端FileUrl = pathToFileURL(遠端Repo).href;
  執行("git", ["remote", "add", "origin", 遠端FileUrl], { cwd: PartialData工作目錄 });
  執行("git", ["config", "remote.origin.promisor", "true"], { cwd: PartialData工作目錄 });
  執行("git", ["config", "remote.origin.partialclonefilter", "blob:none"], {
    cwd: PartialData工作目錄,
  });
  執行("git", ["fetch", "--depth=1", "--filter=blob:none", "origin", "main"], {
    cwd: PartialData工作目錄,
  });
  const partialMissingBefore = 執行(
    "git",
    ["rev-list", "--objects", "--missing=print", "FETCH_HEAD"],
    {
      cwd: PartialData工作目錄,
      env: { ...process.env, GIT_NO_LAZY_FETCH: "1" },
    },
  );
  assert.match(partialMissingBefore.stdout, /^\?/mu, "fixture 必須先缺少 blob 才能驗證修復");

  const partialHydrate = 執行(process.execPath, [工具, "hydrate", "--dry-run"], {
    env: {
      ...工具Env(Partial還原目錄, PartialData工作目錄),
      DATA_REPO_URL: 遠端FileUrl,
    },
  });
  assert.match(partialHydrate.stdout, /舊版 blob:none 快取/u, "必須明確說明正在修復舊快取");
  assert.match(partialHydrate.stdout, /partial-clone 設定已移除/u, "補齊後必須退出 promisor 模式");
  const partialMissingAfter = 執行(
    "git",
    ["rev-list", "--objects", "--missing=print", "FETCH_HEAD"],
    {
      cwd: PartialData工作目錄,
      env: { ...process.env, GIT_NO_LAZY_FETCH: "1" },
    },
  );
  assert.doesNotMatch(partialMissingAfter.stdout, /^\?/mu, "完整重抓後不可再缺少 snapshot blob");
  assert.notEqual(
    執行("git", ["config", "--get", "remote.origin.promisor"], {
      cwd: PartialData工作目錄,
      allowFailure: true,
    }).status,
    0,
    "補齊後不可保留 promisor 設定",
  );

  寫入(
    來源目錄,
    "data/fun/honey_b_fans.json",
    JSON.stringify({ score: 200, records: [], state: { checked_fights: {}, checked_reports: {} } }),
  );
  const honeyRemovalResult = 執行工具("publish", 來源目錄, Data工作目錄, [], true);
  assert.notEqual(honeyRemovalResult.status, 0, "遺失既有趣味榜歷史時必須拒絕發布");
  assert.match(honeyRemovalResult.stderr, /趣味榜|honey_b_fans/u);
  assert.equal(遠端Git(["rev-parse", "main"]), repairedHead, "趣味榜守恆失敗不可更新遠端");
  寫入必要Fixture(來源目錄, 200);

  寫入(
    來源目錄,
    "data/rankings/test.reports/000.json",
    JSON.stringify({ REPORT: { fights: [{ fight_id: 1, players: [] }] } }),
  );
  const removalResult = 執行工具("publish", 來源目錄, Data工作目錄, [], true);
  assert.notEqual(removalResult.status, 0, "遺失既有玩家時必須拒絕發布");
  assert.match(removalResult.stderr, /玩家.+已遺失/u);
  assert.equal(遠端Git(["rev-parse", "main"]), repairedHead, "守恆失敗不可更新遠端");
  寫入必要Fixture(來源目錄, 200);

  寫入(還原目錄, "data/local-cache/keep.json", "保留快取");
  寫入(還原目錄, "data/rankings/stale.json", "刪除舊資料");
  寫入(還原目錄, "public/data/users/local.json", "保留 Users 衍生資料");
  const hydrateResult = 執行工具("hydrate", 還原目錄, 還原Data工作目錄, ["--force"]);
  assert.match(hydrateResult.stdout, /正在下載遠端 main snapshot/u, "hydrate 必須先顯示下載階段");
  assert.match(hydrateResult.stdout, /正在驗證 snapshot 檔案雜湊/u, "hydrate 必須顯示驗證進度");
  assert.match(hydrateResult.stdout, /正在比對本機受管理資料/u, "hydrate 必須顯示本機比對階段");
  assert.match(hydrateResult.stdout, /正在還原 snapshot/u, "正式 hydrate 必須顯示還原進度");
  assert.equal(JSON.parse(fs.readFileSync(path.join(還原目錄, "data/state.json"), "utf8")).score, 200);
  assert(!fs.existsSync(path.join(還原目錄, "data/rankings/stale.json")), "hydrate 必須清除舊受管理資料");
  assert(fs.existsSync(path.join(還原目錄, "data/local-cache/keep.json")), "hydrate 不可刪除本機快取");
  assert(fs.existsSync(path.join(還原目錄, "public/data/users/local.json")), "hydrate 不可刪除 Users 衍生資料");

  const dryRunResult = 執行工具(
    "hydrate",
    還原目錄,
    還原Data工作目錄,
    ["--dry-run"],
  );
  assert.match(dryRunResult.stdout, /dry-run=是/u, "dry-run 必須在開始時清楚標示模式");
  assert.match(dryRunResult.stdout, /未寫入本機資料/u, "dry-run 完成時必須確認沒有寫入資料");

  執行工具("verify", 還原目錄, 還原Data工作目錄);
  console.log("Data repo 單一 root snapshot、排除規則、hydrate 與 manifest 驗證測試通過。");
} finally {
  fs.rmSync(測試根目錄, { recursive: true, force: true });
}
