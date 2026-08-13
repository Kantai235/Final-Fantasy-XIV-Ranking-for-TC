import childProcess from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const 專案根目錄 = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const 預設Repo = "Kantai235/Final-Fantasy-XIV-Ranking-for-TC-Data";
const 預設分支 = "main";
const Manifest檔名 = "snapshot-manifest.json";
const Repo說明檔名 = "README.md";
const Git屬性檔名 = ".gitattributes";
const Git緩衝上限 = 512 * 1024 * 1024;
const GitHub單檔上限 = 100 * 1024 * 1024;

class DataRepoError extends Error {
  constructor(message, details = []) {
    super(message);
    this.details = details;
  }
}

function 顯示用法() {
  console.log(`Usage: node scripts/data_repository.mjs <hydrate|publish|verify|repair-eol> [options]

Commands:
  hydrate  從 Data repo 還原 data/ 與共用 public/data/ 到專案工作目錄。
  publish  將目前資料發布為 Data repo 的單一 root snapshot。
  verify   驗證 Data repo manifest、檔案雜湊與單一 root commit。
  repair-eol  僅修復 manifest 可驗證的 LF 換行轉換損壞。

Options:
  --repo-dir <path>     Data repo 本機工作目錄，預設為 .data-repo。
  --source-root <path>  專案資料來源根目錄，預設為目前專案根目錄。
  --branch <name>       Data repo 分支，預設為 main。
  --force               hydrate 時允許覆寫不同的本機資料。
  --dry-run             hydrate 時只檢查差異；publish 時只建立本機 snapshot。
  --help                顯示說明。
`);
}

function 解析參數(argv) {
  const command = argv[0];
  if (!command || command === "--help" || command === "-h") {
    顯示用法();
    process.exit(command ? 0 : 1);
  }
  if (!new Set(["hydrate", "publish", "verify", "repair-eol"]).has(command)) {
    throw new DataRepoError(`未知指令：${command}`);
  }

  const options = {
    command,
    repoDir: process.env.DATA_REPO_DIR || path.join(專案根目錄, ".data-repo"),
    sourceRoot: process.env.DATA_SOURCE_ROOT || 專案根目錄,
    branch: process.env.DATA_REPO_BRANCH || 預設分支,
    force: false,
    dryRun: false,
  };

  for (let index = 1; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--repo-dir") {
      options.repoDir = argv[++index];
    } else if (arg === "--source-root") {
      options.sourceRoot = argv[++index];
    } else if (arg === "--branch") {
      options.branch = argv[++index];
    } else if (arg === "--force") {
      options.force = true;
    } else if (arg === "--dry-run") {
      options.dryRun = true;
    } else if (arg === "--help" || arg === "-h") {
      顯示用法();
      process.exit(0);
    } else {
      throw new DataRepoError(`未知參數：${arg}`);
    }
  }

  if (!options.repoDir || !options.sourceRoot || !options.branch) {
    throw new DataRepoError("--repo-dir、--source-root 與 --branch 不可為空。");
  }
  options.repoDir = path.resolve(options.repoDir);
  options.sourceRoot = path.resolve(options.sourceRoot);
  return options;
}

function 正規化路徑(filePath) {
  return filePath.replace(/\\/g, "/");
}

function 是否在目錄內(parentPath, childPath) {
  const relative = path.relative(parentPath, childPath);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function 是否暫存檔(relativePath) {
  return relativePath
    .split("/")
    .some((segment) => segment.endsWith(".tmp") || /^\..+\.tmp$/u.test(segment));
}

function 是否為Data來源(relativePath) {
  if (!relativePath.startsWith("data/")) {
    return false;
  }
  if (
    relativePath.startsWith("data/local-cache/") ||
    relativePath.startsWith("data/shallow_scan_cache/")
  ) {
    return false;
  }
  return !是否暫存檔(relativePath);
}

function 是否為共用公開資料(relativePath) {
  if (!relativePath.startsWith("public/data/")) {
    return false;
  }
  const remainder = relativePath.slice("public/data/".length);
  if (!remainder || 是否暫存檔(relativePath)) {
    return false;
  }

  // 個別玩家成績與報告明細由 Users repo 的單一快照承載；排行榜、hidden delta
  // 與其他 public 子目錄都可由 data/rankings 重新建置。Data repo 只保存主站共用
  // 根層 JSON 與無法由其他來源取代的趣味榜公開摘要，避免重複保存約 1.7 GiB 衍生資料。
  return !remainder.includes("/") || remainder.startsWith("fun/");
}

function 是否受管理資料(relativePath) {
  const normalized = 正規化路徑(relativePath);
  return 是否為Data來源(normalized) || 是否為共用公開資料(normalized);
}

function 遞迴收集檔案(directory) {
  if (!fs.existsSync(directory)) {
    return [];
  }
  const files = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...遞迴收集檔案(fullPath));
    } else if (entry.isFile()) {
      files.push(fullPath);
    }
  }
  return files;
}

function 建立Sha256(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function 收集受管理檔案(sourceRoot) {
  const files = [];
  for (const topLevel of ["data", "public/data"]) {
    const absoluteRoot = path.join(sourceRoot, topLevel);
    for (const absolutePath of 遞迴收集檔案(absoluteRoot)) {
      const relativePath = 正規化路徑(path.relative(sourceRoot, absolutePath));
      if (!是否受管理資料(relativePath)) {
        continue;
      }
      const stats = fs.statSync(absolutePath);
      files.push({
        path: relativePath,
        absolutePath,
        sizeBytes: stats.size,
        sha256: 建立Sha256(absolutePath),
      });
    }
  }
  files.sort((left, right) => left.path.localeCompare(right.path, "en"));
  return files;
}

function 建立內容簽章(files) {
  const input = files.map((file) => `${file.path}:${file.sizeBytes}:${file.sha256}`).join("\n");
  return crypto.createHash("sha256").update(input).digest("hex");
}

function 確認必要來源(files) {
  const paths = new Set(files.map((file) => file.path));
  const required = [
    "data/state.json",
    "data/update_status.json",
    "data/pages_payload_history.jsonl",
    "public/data/announcements.json",
    "public/data/encounters.json",
    "public/data/global_stats.json",
    "public/data/update_status.json",
  ];
  const issues = required.filter((requiredPath) => !paths.has(requiredPath));
  if (!files.some((file) => /^data\/rankings\/[^/]+\.json$/u.test(file.path))) {
    issues.push("data/rankings/*.json");
  }
  if (!files.some((file) => /^data\/rankings\/[^/]+\.reports\/\d+\.json$/u.test(file.path))) {
    issues.push("data/rankings/*.reports/*.json");
  }
  if (issues.length > 0) {
    throw new DataRepoError("Data snapshot 缺少必要來源，拒絕發布。", issues);
  }

  const oversized = files.filter((file) => file.sizeBytes >= GitHub單檔上限);
  if (oversized.length > 0) {
    throw new DataRepoError(
      "Data snapshot 含有達到 GitHub 100 MiB 上限的檔案，請先分片。",
      oversized.map((file) => `${file.path}: ${(file.sizeBytes / 1024 / 1024).toFixed(2)} MiB`),
    );
  }
}

function 遮蔽敏感內容(value) {
  let output = String(value || "");
  const token = String(process.env.GIT_PAT || "").trim();
  if (token) {
    output = output.replaceAll(token, "***");
  }
  return output;
}

function 執行(command, args, { cwd, input, allowFailure = false, maxBuffer = Git緩衝上限 } = {}) {
  const result = childProcess.spawnSync(command, args, {
    cwd,
    encoding: "utf8",
    input,
    maxBuffer,
  });
  if (result.error) {
    throw result.error;
  }
  if (!allowFailure && result.status !== 0) {
    throw new DataRepoError(
      `${command} ${args.map(遮蔽敏感內容).join(" ")} 執行失敗（exit code ${result.status}）。`,
      [遮蔽敏感內容(result.stderr || result.stdout || "")],
    );
  }
  return result;
}

function Git(repoDir, args, options = {}) {
  return 執行("git", args, { ...options, cwd: repoDir });
}

function Git輸出(repoDir, args, options = {}) {
  return String(Git(repoDir, args, options).stdout || "").trim();
}

function 取得RepoUrl() {
  const override = String(process.env.DATA_REPO_URL || "").trim();
  if (override) {
    return override;
  }
  const repository = String(process.env.DATA_REPO || 預設Repo).trim();
  const token = String(process.env.GIT_PAT || "").trim();
  return token
    ? `https://x-access-token:${token}@github.com/${repository}.git`
    : `https://github.com/${repository}.git`;
}

function 清除RepoUrl憑證(options) {
  if (!options || !fs.existsSync(path.join(options.repoDir, ".git"))) {
    return;
  }
  const override = String(process.env.DATA_REPO_URL || "").trim();
  const repository = String(process.env.DATA_REPO || 預設Repo).trim();
  const safeUrl = override || `https://github.com/${repository}.git`;
  Git(options.repoDir, ["remote", "set-url", "origin", safeUrl], { allowFailure: true });
}

function 初始化Repo(repoDir, branch) {
  if (!fs.existsSync(path.join(repoDir, ".git"))) {
    if (fs.existsSync(repoDir) && fs.readdirSync(repoDir).length > 0) {
      throw new DataRepoError(`Data repo 工作目錄不是空目錄，也不是 Git repo：${repoDir}`);
    }
    fs.mkdirSync(repoDir, { recursive: true });
    Git(repoDir, ["init", "-q"]);
  }
  const remoteExists = Git(repoDir, ["remote", "get-url", "origin"], { allowFailure: true });
  if (remoteExists.status === 0) {
    Git(repoDir, ["remote", "set-url", "origin", 取得RepoUrl()]);
  } else {
    Git(repoDir, ["remote", "add", "origin", 取得RepoUrl()]);
  }
  Git(repoDir, ["config", "core.autocrlf", "false"]);
  Git(repoDir, ["config", "user.name", "github-actions[bot]"]);
  Git(repoDir, ["config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"]);
  Git(repoDir, ["symbolic-ref", "HEAD", `refs/heads/${branch}`]);
}

function 取得遠端快照(repoDir, branch) {
  const fetched = Git(repoDir, ["fetch", "--depth=1", "--filter=blob:none", "origin", branch], {
    allowFailure: true,
  });
  if (fetched.status === 0) {
    const remoteHead = Git輸出(repoDir, ["rev-parse", "FETCH_HEAD"]);
    Git(repoDir, ["update-ref", `refs/remotes/origin/${branch}`, remoteHead]);
    return remoteHead;
  }

  const message = 遮蔽敏感內容(fetched.stderr || fetched.stdout || "");
  if (/couldn(?:'|’)t find remote ref|remote branch .* not found|repository is empty/iu.test(message)) {
    return null;
  }
  throw new DataRepoError("無法取得 Data repo 快照。", [message]);
}

function 從Commit讀取Json(repoDir, commit, filePath) {
  if (!commit) {
    return null;
  }
  const result = Git(repoDir, ["show", `${commit}:${filePath}`], { allowFailure: true });
  if (result.status !== 0) {
    return null;
  }
  try {
    return JSON.parse(result.stdout);
  } catch {
    return null;
  }
}

function 建立Manifest(files, options) {
  const totalSizeBytes = files.reduce((sum, file) => sum + file.sizeBytes, 0);
  return {
    schema_version: 1,
    format: "ffxiv_tc_data_snapshot_v1",
    repository: process.env.DATA_REPO || 預設Repo,
    branch: options.branch,
    content_signature: 建立內容簽章(files),
    file_count: files.length,
    total_size_bytes: totalSizeBytes,
    source: {
      repository: process.env.GITHUB_REPOSITORY || "Kantai235/Final-Fantasy-XIV-Ranking-for-TC",
      branch: process.env.GITHUB_REF_NAME || null,
      commit: process.env.GITHUB_SHA || null,
      event: process.env.GITHUB_EVENT_NAME || null,
      run_id: process.env.GITHUB_RUN_ID || null,
      run_attempt: Number(process.env.GITHUB_RUN_ATTEMPT || 0) || null,
    },
    files: files.map((file) => ({
      path: file.path,
      size_bytes: file.sizeBytes,
      sha256: file.sha256,
    })),
  };
}

function Repo說明內容() {
  return `# FFXIV 繁中服排行榜資料快照

此 repo 只保存 [Final-Fantasy-XIV-Ranking-for-TC](https://github.com/Kantai235/Final-Fantasy-XIV-Ranking-for-TC) 資料管線產生的最新可追溯快照。

- \`data/\`：FFLogs report、fight、player、掃描狀態與歷史游標等權威來源。
- \`public/data/\`：主站共用的靜態 JSON；個別玩家成績與明細由 Users repo 承載。
- \`${Manifest檔名}\`：本快照的檔案清單、大小與 SHA-256。

每次更新都建立沒有 parent 的 root commit，並以 \`force-with-lease\` 更新 \`main\`。舊快照不屬於可追溯歷史；歷史來源由目前快照內的 append-only report 與 state 保存。

請勿直接人工修改資料。所有寫入都必須先通過主專案的資料契約與守恆驗證。
`;
}

function 寫入暫存文字(repoDir, name, content) {
  const tempDir = fs.mkdtempSync(path.join(repoDir, ".snapshot-"));
  const filePath = path.join(tempDir, name);
  fs.writeFileSync(filePath, content, "utf8");
  return { tempDir, filePath };
}

function 將檔案寫入Index(repoDir, files) {
  for (const file of files) {
    // Manifest 的 SHA-256 是來源檔案原始位元組的摘要。Git 若依上層
    // .gitattributes 將 CRLF 正規化為 LF，commit 就會與剛建立的 manifest 不同。
    // 因此使用 --no-filters 明確以原始位元組寫入 blob，不將資料格式
    // 偶然綁定在 runner 的作業系統與 Git 換行設定。
    const oid = Git輸出(repoDir, ["hash-object", "-w", "--no-filters", "--", file.absolutePath]);
    Git(repoDir, ["update-index", "--add", "--cacheinfo", `100644,${oid},${file.path}`]);
  }
}

function 建立RootCommit(repoDir, branch, files, manifest) {
  Git(repoDir, ["read-tree", "--empty"]);
  將檔案寫入Index(repoDir, files);

  const tempPaths = [];
  try {
    const attributes = 寫入暫存文字(
      repoDir,
      Git屬性檔名,
      "# Manifest 以來源檔案的原始位元組計算 SHA-256；禁止 Git 轉換換行。\n* -text\n",
    );
    const readme = 寫入暫存文字(repoDir, Repo說明檔名, Repo說明內容());
    const manifestFile = 寫入暫存文字(
      repoDir,
      Manifest檔名,
      `${JSON.stringify(manifest, null, 2)}\n`,
    );
    tempPaths.push(attributes.tempDir, readme.tempDir, manifestFile.tempDir);
    將檔案寫入Index(repoDir, [
      { absolutePath: attributes.filePath, path: Git屬性檔名 },
      { absolutePath: readme.filePath, path: Repo說明檔名 },
      { absolutePath: manifestFile.filePath, path: Manifest檔名 },
    ]);

    const tree = Git輸出(repoDir, ["write-tree"]);
    const message = [
      "chore(data): 更新排行榜資料單一快照",
      "",
      "Why:",
      "- 排行榜來源與公開 JSON 會高頻更新，Data repo 只保存目前可部署快照，避免 Git 歷史無上限成長。",
      "",
      "主要變更：",
      `- 保存 ${manifest.file_count.toLocaleString("en-US")} 個資料檔，合計 ${(manifest.total_size_bytes / 1024 / 1024).toFixed(1)} MiB。`,
      "- 快照 manifest 記錄所有檔案大小與 SHA-256，供載入及部署前驗證。",
      "",
      "測試與驗證：",
      "- 主專案 workflow 已執行資料建置、公開資料契約與資料守恆檢查。",
      "- 本提交為無 parent 的 root commit；推送由 force-with-lease 防止競爭覆寫。",
      "",
    ].join("\n");
    const commit = Git輸出(repoDir, ["commit-tree", tree, "-F", "-"], { input: message });
    Git(repoDir, ["update-ref", `refs/heads/${branch}`, commit]);
    return commit;
  } finally {
    for (const tempDir of tempPaths) {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  }
}

function 驗證Manifest結構(manifest) {
  if (
    manifest?.schema_version !== 1 ||
    manifest?.format !== "ffxiv_tc_data_snapshot_v1" ||
    !Array.isArray(manifest.files) ||
    !manifest.content_signature
  ) {
    throw new DataRepoError(`Data repo 缺少有效的 ${Manifest檔名}。`);
  }
  const invalid = manifest.files.filter(
    (file) =>
      !file?.path ||
      !是否受管理資料(file.path) ||
      !Number.isSafeInteger(file.size_bytes) ||
      file.size_bytes < 0 ||
      !/^[0-9a-f]{64}$/u.test(file.sha256 || ""),
  );
  if (invalid.length > 0) {
    throw new DataRepoError("Data repo manifest 含有無效或不受管理的路徑。", invalid.slice(0, 20));
  }
  const uniquePaths = new Set(manifest.files.map((file) => file.path));
  if (uniquePaths.size !== manifest.files.length) {
    throw new DataRepoError("Data repo manifest 含有重複路徑。");
  }
}

function 驗證快照追蹤路徑(repoDir, commit, manifest) {
  const tracked = Git輸出(repoDir, ["ls-tree", "-r", "--name-only", commit])
    .split(/\r?\n/u)
    .filter(Boolean);
  // .gitattributes 是 2026-08 後新快照用來鎖定原始位元組的保護檔。
  // 舊快照尚未含有這個檔案，驗證時必須維持向後相容。
  const requiredTracked = new Set([
    Repo說明檔名,
    Manifest檔名,
    ...manifest.files.map((file) => file.path),
  ]);
  const allowedTracked = new Set([...requiredTracked, Git屬性檔名]);
  const unexpected = tracked.filter((file) => !allowedTracked.has(file));
  const missing = [...requiredTracked].filter((file) => !tracked.includes(file));
  if (unexpected.length > 0 || missing.length > 0) {
    throw new DataRepoError("Data repo 快照的追蹤檔案與 manifest 不一致。", [
      ...unexpected.slice(0, 20).map((file) => `未列於 manifest：${file}`),
      ...missing.slice(0, 20).map((file) => `缺少追蹤檔案：${file}`),
    ]);
  }
}

function 驗證Repo快照(repoDir, branch, commit) {
  const manifest = 從Commit讀取Json(repoDir, commit, Manifest檔名);
  驗證Manifest結構(manifest);
  const parents = Git輸出(repoDir, ["show", "-s", "--format=%P", commit]);
  if (parents) {
    throw new DataRepoError("Data repo main 必須是沒有 parent 的單一 root snapshot。", [parents]);
  }

  Git(repoDir, ["reset", "--hard", commit]);
  const verifiedFiles = [];
  for (const expected of manifest.files) {
    const absolutePath = path.resolve(repoDir, expected.path);
    if (!是否在目錄內(repoDir, absolutePath) || !fs.existsSync(absolutePath)) {
      throw new DataRepoError(`Data repo 快照缺少檔案：${expected.path}`);
    }
    const stats = fs.statSync(absolutePath);
    const actualSha = 建立Sha256(absolutePath);
    if (stats.size !== expected.size_bytes || actualSha !== expected.sha256) {
      throw new DataRepoError(`Data repo 快照檔案驗證失敗：${expected.path}`);
    }
    verifiedFiles.push({
      path: expected.path,
      sizeBytes: stats.size,
      sha256: actualSha,
    });
  }
  const signature = 建立內容簽章(verifiedFiles);
  if (signature !== manifest.content_signature) {
    throw new DataRepoError("Data repo manifest 的整體內容簽章不一致。");
  }
  驗證快照追蹤路徑(repoDir, commit, manifest);

  console.log(
    `Data repo 驗證通過：${branch}@${commit.slice(0, 12)}，${manifest.file_count.toLocaleString("en-US")} 個檔案，${(manifest.total_size_bytes / 1024 / 1024).toFixed(1)} MiB。`,
  );
  return manifest;
}

function 讀取Json檔(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (error) {
    throw new DataRepoError(`無法解析資料 JSON：${filePath}`, [error.message]);
  }
}

function 取得Report分片(rootDir, encounterKey) {
  const shardDir = path.join(rootDir, "data", "rankings", `${encounterKey}.reports`);
  return 遞迴收集檔案(shardDir)
    .filter((filePath) => filePath.endsWith(".json"))
    .sort((left, right) => left.localeCompare(right, "en"));
}

function 取得既有副本鍵(rootDir) {
  const rankingsDir = path.join(rootDir, "data", "rankings");
  if (!fs.existsSync(rankingsDir)) {
    return [];
  }
  return fs
    .readdirSync(rankingsDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name.endsWith(".reports"))
    .map((entry) => entry.name.slice(0, -".reports".length))
    .sort((left, right) => left.localeCompare(right, "en"));
}

function 建立Report位置索引(rootDir, encounterKey) {
  const locations = new Map();
  for (const shardPath of 取得Report分片(rootDir, encounterKey)) {
    const shard = 讀取Json檔(shardPath);
    for (const reportCode of Object.keys(shard)) {
      if (locations.has(reportCode)) {
        throw new DataRepoError(
          `副本 ${encounterKey} 的 report ${reportCode} 在目前快照重複出現。`,
        );
      }
      locations.set(reportCode, shardPath);
    }
  }
  return locations;
}

function 玩家身分鍵(player) {
  if (player?.fflogs_id !== null && player?.fflogs_id !== undefined) {
    return `id:${player.fflogs_id}`;
  }
  if (player?.fflogs_guid !== null && player?.fflogs_guid !== undefined) {
    return `guid:${player.fflogs_guid}`;
  }
  return `fallback:${player?.name || ""}\u0000${player?.server || ""}\u0000${player?.job || ""}`;
}

function 確認單一Report歷史未遺失(encounterKey, reportCode, previousReport, currentReport, issues) {
  if (!currentReport) {
    issues.push(`${encounterKey}: report ${reportCode} 已遺失`);
    return;
  }

  const currentFights = new Map(
    (currentReport.fights || []).map((fight) => [String(fight?.fight_id), fight]),
  );
  for (const previousFight of previousReport.fights || []) {
    const fightId = String(previousFight?.fight_id);
    const currentFight = currentFights.get(fightId);
    if (!currentFight) {
      issues.push(`${encounterKey}: report ${reportCode} 的 fight ${fightId} 已遺失`);
      continue;
    }

    const currentPlayers = new Set((currentFight.players || []).map(玩家身分鍵));
    for (const previousPlayer of previousFight.players || []) {
      const playerKey = 玩家身分鍵(previousPlayer);
      if (!currentPlayers.has(playerKey)) {
        issues.push(
          `${encounterKey}: report ${reportCode} fight ${fightId} 的玩家 ${previousPlayer?.name || playerKey} 已遺失`,
        );
      }
      if (issues.length >= 100) {
        return;
      }
    }
  }
}

function 確認Report歷史未遺失(previousRoot, currentRoot, encounterKey, issues) {
  const currentLocations = 建立Report位置索引(currentRoot, encounterKey);
  let cachedCurrentPath = null;
  let cachedCurrentShard = null;

  // 分片可因體積調整而重新排列，所以先以 report code 建立小型位置索引，再逐一載入
  // 舊分片比對。此做法不會同時把整個約 1 GiB report 集合留在記憶體。
  for (const previousShardPath of 取得Report分片(previousRoot, encounterKey)) {
    const previousShard = 讀取Json檔(previousShardPath);
    for (const [reportCode, previousReport] of Object.entries(previousShard)) {
      const currentPath = currentLocations.get(reportCode);
      if (!currentPath) {
        issues.push(`${encounterKey}: report ${reportCode} 已遺失`);
        if (issues.length >= 100) return;
        continue;
      }
      if (currentPath !== cachedCurrentPath) {
        cachedCurrentPath = currentPath;
        cachedCurrentShard = 讀取Json檔(currentPath);
      }
      確認單一Report歷史未遺失(
        encounterKey,
        reportCode,
        previousReport,
        cachedCurrentShard[reportCode],
        issues,
      );
      if (issues.length >= 100) return;
    }
  }
}

function 確認CheckedReports未遺失(previousRoot, currentRoot, issues) {
  const previousDir = path.join(previousRoot, "data", "state", "checked_reports");
  for (const previousPath of 遞迴收集檔案(previousDir).filter((file) => file.endsWith(".json"))) {
    const relativePath = path.relative(previousRoot, previousPath);
    const currentPath = path.join(currentRoot, relativePath);
    if (!fs.existsSync(currentPath)) {
      issues.push(`${正規化路徑(relativePath)} 已遺失`);
      continue;
    }
    const previous = 讀取Json檔(previousPath);
    const current = 讀取Json檔(currentPath);
    for (const reportCode of Object.keys(previous)) {
      if (!Object.hasOwn(current, reportCode)) {
        issues.push(`${正規化路徑(relativePath)} 的 checkpoint ${reportCode} 已遺失`);
      }
      if (issues.length >= 100) return;
    }
  }
}

function 確認State副本未遺失(previousRoot, currentRoot, issues) {
  const previous = 讀取Json檔(path.join(previousRoot, "data", "state.json"));
  const current = 讀取Json檔(path.join(currentRoot, "data", "state.json"));
  for (const encounterKey of Object.keys(previous.encounters || {})) {
    if (!Object.hasOwn(current.encounters || {}, encounterKey)) {
      issues.push(`data/state.json 的副本狀態 ${encounterKey} 已遺失`);
    }
  }
}

function 確認趣味榜歷史未遺失(previousRoot, currentRoot, issues) {
  const relativePath = path.join("data", "fun", "honey_b_fans.json");
  const previous = 讀取Json檔(path.join(previousRoot, relativePath));
  const current = 讀取Json檔(path.join(currentRoot, relativePath));
  const currentRecordIds = new Set((current.records || []).map((record) => String(record?.id)));
  for (const record of previous.records || []) {
    if (!currentRecordIds.has(String(record?.id))) {
      issues.push(`data/fun/honey_b_fans.json 的歷史紀錄 ${record?.id || "未知"} 已遺失`);
      if (issues.length >= 100) return;
    }
  }
  for (const stateKey of ["checked_fights", "checked_reports"]) {
    const currentState = current.state?.[stateKey] || {};
    for (const historyKey of Object.keys(previous.state?.[stateKey] || {})) {
      if (!Object.hasOwn(currentState, historyKey)) {
        issues.push(`data/fun/honey_b_fans.json 的 ${stateKey}.${historyKey} 已遺失`);
      }
      if (issues.length >= 100) return;
    }
  }
}

function 確認AppendOnly歷史(previousRoot, currentRoot) {
  const issues = [];
  for (const encounterKey of 取得既有副本鍵(previousRoot)) {
    確認Report歷史未遺失(previousRoot, currentRoot, encounterKey, issues);
    if (issues.length >= 100) break;
  }
  if (issues.length < 100) {
    確認CheckedReports未遺失(previousRoot, currentRoot, issues);
  }
  if (issues.length < 100) {
    確認State副本未遺失(previousRoot, currentRoot, issues);
  }
  if (issues.length < 100) {
    確認趣味榜歷史未遺失(previousRoot, currentRoot, issues);
  }
  if (issues.length > 0) {
    throw new DataRepoError(
      "Data snapshot 會遺失既有 report、fight、player 或 checkpoint，拒絕發布。",
      issues,
    );
  }
  console.log("Data repo append-only 歷史檢查通過。");
}

function 清除本機受管理資料(sourceRoot) {
  const files = 收集受管理檔案(sourceRoot);
  for (const file of files) {
    fs.rmSync(file.absolutePath, { force: true });
  }
}

function 複製快照到來源(repoDir, sourceRoot, manifest) {
  for (const file of manifest.files) {
    const sourcePath = path.resolve(repoDir, file.path);
    const targetPath = path.resolve(sourceRoot, file.path);
    if (!是否在目錄內(repoDir, sourcePath) || !是否在目錄內(sourceRoot, targetPath)) {
      throw new DataRepoError(`拒絕複製工作目錄外的路徑：${file.path}`);
    }
    fs.mkdirSync(path.dirname(targetPath), { recursive: true });
    fs.copyFileSync(sourcePath, targetPath);
  }
}

function 執行Hydrate(options) {
  初始化Repo(options.repoDir, options.branch);
  const remoteHead = 取得遠端快照(options.repoDir, options.branch);
  if (!remoteHead) {
    throw new DataRepoError("Data repo 尚無可載入的 main snapshot。");
  }
  const manifest = 驗證Repo快照(options.repoDir, options.branch, remoteHead);

  const currentFiles = 收集受管理檔案(options.sourceRoot);
  let currentSignature = null;
  if (currentFiles.length > 0) {
    currentSignature = 建立內容簽章(currentFiles);
    if (currentSignature !== manifest.content_signature && !options.force) {
      throw new DataRepoError(
        "本機已有不同的受管理資料；為避免覆寫本機回補成果，hydrate 已停止。",
        ["先發布／備份本機資料，或確認可捨棄後加上 --force。"],
      );
    }
  }

  if (options.dryRun) {
    const result = currentSignature === manifest.content_signature ? "內容相同" : "將以遠端快照取代";
    console.log(`Data repo hydrate dry run 通過：${result}，未寫入本機資料。`);
    return;
  }

  清除本機受管理資料(options.sourceRoot);
  複製快照到來源(options.repoDir, options.sourceRoot, manifest);
  console.log(`已從 Data repo ${remoteHead.slice(0, 12)} 還原資料到 ${options.sourceRoot}。`);
}

function 推送RootCommit(repoDir, branch, remoteHead, newCommit) {
  const ref = `refs/heads/${branch}`;
  const pushArgs = ["push"];
  if (remoteHead) {
    pushArgs.push(`--force-with-lease=${ref}:${remoteHead}`);
  }
  pushArgs.push("origin", `${newCommit}:${ref}`);

  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const pushed = Git(repoDir, pushArgs, { allowFailure: true });
    if (pushed.status === 0) {
      Git(repoDir, ["update-ref", `refs/remotes/origin/${branch}`, newCommit]);
      console.log(`Data repo 已更新為單一 root snapshot ${newCommit}。`);
      return;
    }
    const currentRemote = Git(repoDir, ["ls-remote", "--heads", "origin", ref], {
      allowFailure: true,
    });
    const currentSha = String(currentRemote.stdout || "").trim().split(/\s+/u)[0] || null;
    if (currentSha === newCommit) {
      console.log(`Data repo 遠端已是 ${newCommit}，視為推送成功。`);
      return;
    }
    if (currentSha !== remoteHead) {
      throw new DataRepoError(
        `Data repo 在本輪建置期間已從 ${remoteHead || "空白"} 更新為 ${currentSha || "未知"}；force-with-lease 已阻止覆寫。`,
      );
    }
    if (attempt === 3) {
      throw new DataRepoError("Data repo snapshot 推送重試後仍失敗。", [
        遮蔽敏感內容(pushed.stderr || pushed.stdout || ""),
      ]);
    }
  }
}

function 將Lf還原為CrLf(content) {
  let bareLfCount = 0;
  for (let index = 0; index < content.length; index += 1) {
    if (content[index] === 0x0a && (index === 0 || content[index - 1] !== 0x0d)) {
      bareLfCount += 1;
    }
  }
  if (bareLfCount === 0) {
    return null;
  }

  const restored = Buffer.allocUnsafe(content.length + bareLfCount);
  let outputIndex = 0;
  for (let index = 0; index < content.length; index += 1) {
    if (content[index] === 0x0a && (index === 0 || content[index - 1] !== 0x0d)) {
      restored[outputIndex++] = 0x0d;
    }
    restored[outputIndex++] = content[index];
  }
  return restored;
}

function 是否符合Manifest檔案(content, expected) {
  return (
    Buffer.isBuffer(content) &&
    content.length === expected.size_bytes &&
    crypto.createHash("sha256").update(content).digest("hex") === expected.sha256
  );
}

function 執行RepairEol(options) {
  初始化Repo(options.repoDir, options.branch);
  const remoteHead = 取得遠端快照(options.repoDir, options.branch);
  if (!remoteHead) {
    throw new DataRepoError("Data repo 尚無可修復的 main snapshot。");
  }

  const manifest = 從Commit讀取Json(options.repoDir, remoteHead, Manifest檔名);
  驗證Manifest結構(manifest);
  const parents = Git輸出(options.repoDir, ["show", "-s", "--format=%P", remoteHead]);
  if (parents) {
    throw new DataRepoError("Data repo main 必須是沒有 parent 的單一 root snapshot。", [parents]);
  }
  驗證快照追蹤路徑(options.repoDir, remoteHead, manifest);
  Git(options.repoDir, ["reset", "--hard", remoteHead]);

  const files = [];
  const repairedPaths = [];
  for (const expected of manifest.files) {
    const absolutePath = path.resolve(options.repoDir, expected.path);
    if (!是否在目錄內(options.repoDir, absolutePath) || !fs.existsSync(absolutePath)) {
      throw new DataRepoError(`Data repo 快照缺少檔案：${expected.path}`);
    }

    const content = fs.readFileSync(absolutePath);
    if (!是否符合Manifest檔案(content, expected)) {
      // 混合 LF / CRLF 的文字檔無法只從正規化後的 blob 推回哪些行原本帶 CR。
      // 因此先嘗試專案工作目錄中的同路徑原始檔；它只有大小與 SHA-256
      // 完全命中舊 manifest 時才可採用。若本機沒有原始檔，才嘗試單純
      // LF -> CRLF 還原。兩者都無法驗證時立即停止，不把其他損壞誤當換行問題。
      const sourceCandidatePath = path.resolve(options.sourceRoot, expected.path);
      const sourceCandidate =
        是否在目錄內(options.sourceRoot, sourceCandidatePath) &&
        fs.existsSync(sourceCandidatePath)
          ? fs.readFileSync(sourceCandidatePath)
          : null;
      const eolCandidate = 將Lf還原為CrLf(content);
      const restored = 是否符合Manifest檔案(sourceCandidate, expected)
        ? sourceCandidate
        : eolCandidate;
      if (!restored || !是否符合Manifest檔案(restored, expected)) {
        throw new DataRepoError(
          `Data repo 快照不是可安全修復的換行轉換：${expected.path}`,
        );
      }
      fs.writeFileSync(absolutePath, restored);
      repairedPaths.push(expected.path);
    }

    files.push({
      path: expected.path,
      absolutePath,
      sizeBytes: expected.size_bytes,
      sha256: expected.sha256,
    });
  }

  if (repairedPaths.length === 0) {
    驗證Repo快照(options.repoDir, options.branch, remoteHead);
    console.log("Data repo 快照沒有需要修復的換行轉換。");
    return;
  }

  確認必要來源(files);
  const commit = 建立RootCommit(options.repoDir, options.branch, files, manifest);
  驗證Repo快照(options.repoDir, options.branch, commit);
  console.log(`Data repo 已安全還原 ${repairedPaths.length} 個檔案的 CRLF 原始位元組。`);
  if (options.dryRun) {
    console.log(`Data repo repair-eol dry run 已建立本機 root snapshot ${commit}，未推送。`);
    return;
  }
  推送RootCommit(options.repoDir, options.branch, remoteHead, commit);
}

function 執行Publish(options) {
  const files = 收集受管理檔案(options.sourceRoot);
  確認必要來源(files);
  const manifest = 建立Manifest(files, options);

  初始化Repo(options.repoDir, options.branch);
  const remoteHead = 取得遠端快照(options.repoDir, options.branch);
  const previousManifest = remoteHead
    ? 驗證Repo快照(options.repoDir, options.branch, remoteHead)
    : null;
  const remoteParents = remoteHead
    ? Git輸出(options.repoDir, ["show", "-s", "--format=%P", remoteHead])
    : "";
  if (
    previousManifest?.content_signature === manifest.content_signature &&
    previousManifest?.file_count === manifest.file_count &&
    !remoteParents
  ) {
    console.log("Data repo 內容與單一 root snapshot 均未變更，略過發布。");
    return;
  }

  if (remoteHead) {
    確認AppendOnly歷史(options.repoDir, options.sourceRoot);
  }

  const commit = 建立RootCommit(options.repoDir, options.branch, files, manifest);
  if (options.dryRun) {
    console.log(`Data repo dry run 已建立本機 root snapshot ${commit}，未推送。`);
    return;
  }
  推送RootCommit(options.repoDir, options.branch, remoteHead, commit);
}

function 執行Verify(options) {
  初始化Repo(options.repoDir, options.branch);
  const remoteHead = 取得遠端快照(options.repoDir, options.branch);
  if (!remoteHead) {
    throw new DataRepoError("Data repo 尚無可驗證的 main snapshot。");
  }
  驗證Repo快照(options.repoDir, options.branch, remoteHead);
}

function main(options) {
  if (options.command === "hydrate") {
    執行Hydrate(options);
  } else if (options.command === "publish") {
    執行Publish(options);
  } else if (options.command === "repair-eol") {
    執行RepairEol(options);
  } else {
    執行Verify(options);
  }
}

let options = null;
try {
  options = 解析參數(process.argv.slice(2));
  main(options);
} catch (error) {
  console.error(error.message);
  for (const detail of error.details || []) {
    console.error(`- ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
  }
  process.exitCode = 1;
} finally {
  // workflow runner 雖然是暫時環境，本機維護者也會重用 .data-repo。遠端 URL 只在
  // Git 命令執行期間帶入 PAT，結束前一律還原為不含憑證的網址，避免權杖留在 .git/config。
  清除RepoUrl憑證(options);
}
