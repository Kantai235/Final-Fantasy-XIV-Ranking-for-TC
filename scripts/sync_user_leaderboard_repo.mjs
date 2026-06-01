import childProcess from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const 專用Repo擁有者與名稱 = "Kantai235/Final-Fantasy-XIV-Ranking-for-TC-Users";
const 目標分支 = process.env.USER_REPO_BRANCH || "main";
const 執行參數 = new Set(process.argv.slice(2));
const 乾跑 = 執行參數.has("--dry-run") || ["1", "true", "yes"].includes(String(process.env.USER_SYNC_DRY_RUN || "").toLowerCase());
const 來源根目錄 = path.resolve(process.env.USER_DATA_SOURCE_ROOT || process.cwd());
const 工作根目錄 = path.resolve(
  process.env.USER_REPO_DIR ||
    path.join(process.env.RUNNER_TEMP || os.tmpdir(), "Final-Fantasy-XIV-Ranking-for-TC-Users"),
);
const Git輸出緩衝上限 = 128 * 1024 * 1024;
const 需替換的資料路徑 = [
  "data/users",
  "data/user-entry-details",
  "data/all/users",
  "data/all/user-entry-details",
];
const 需同步資料夾 = [
  { key: "users", source: "public/data/users", target: "data/users", required: true },
  {
    key: "user_entry_details",
    source: "public/data/user-entry-details",
    target: "data/user-entry-details",
    required: true,
  },
  { key: "all_users", source: "public/data/all/users", target: "data/all/users", required: false },
  {
    key: "all_user_entry_details",
    source: "public/data/all/user-entry-details",
    target: "data/all/user-entry-details",
    required: false,
  },
];

function 取得RepoUrl() {
  const 覆寫Url = String(process.env.USER_REPO_URL || "").trim();
  if (覆寫Url) {
    return 覆寫Url;
  }

  const token = String(process.env.GIT_PAT || "").trim();
  if (!token) {
    throw new Error("缺少 GIT_PAT，請在 repository secrets 定義。");
  }

  return `https://x-access-token:${token}@github.com/${專用Repo擁有者與名稱}.git`;
}

const 專用RepoUrl = 取得RepoUrl();

function 隱藏敏感內容(文字) {
  let 結果 = String(文字 || "");
  const token = String(process.env.GIT_PAT || "").trim();
  if (token) {
    結果 = 結果.replaceAll(token, "***");
  }
  if (專用RepoUrl) {
    結果 = 結果.replaceAll(專用RepoUrl, "USER_REPO_URL");
  }
  return 結果;
}

function 執行指令(指令, 參數, 選項 = {}) {
  const 結果 = childProcess.spawnSync(指令, 參數, {
    cwd: 選項.cwd || 來源根目錄,
    encoding: 選項.encoding || "utf8",
    input: 選項.input,
    maxBuffer: 選項.maxBuffer || Git輸出緩衝上限,
    stdio: 選項.stdio,
  });

  if (結果.error) {
    throw 結果.error;
  }

  if (結果.status !== 0) {
    const 顯示參數 = 參數.map((參數值) => 隱藏敏感內容(參數值)).join(" ");
    const 錯誤輸出 = 隱藏敏感內容(結果.stderr || 結果.stdout || "");
    throw new Error(`${指令} ${顯示參數} 執行失敗，exit code ${結果.status}\n${錯誤輸出}`);
  }

  return 結果.stdout || "";
}

function 執行Git(參數, 選項 = {}) {
  return 執行指令("git", 參數, { ...選項, cwd: 選項.cwd || 工作根目錄 });
}

function 檢查Git是否有差異(參數) {
  const 結果 = childProcess.spawnSync("git", 參數, {
    cwd: 工作根目錄,
    encoding: "utf8",
    maxBuffer: Git輸出緩衝上限,
  });
  if (結果.error) {
    throw 結果.error;
  }
  if (結果.status === 0) {
    return false;
  }
  if (結果.status === 1) {
    return true;
  }
  throw new Error(`git ${參數.join(" ")} 執行失敗，exit code ${結果.status}\n${隱藏敏感內容(結果.stderr || 結果.stdout || "")}`);
}

function 讀取Json(filePath, fallback = null) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return fallback;
  }
}

function 讀取上一版Manifest() {
  const 結果 = childProcess.spawnSync("git", ["show", "HEAD:data/sync-manifest.json"], {
    cwd: 工作根目錄,
    encoding: "utf8",
    maxBuffer: Git輸出緩衝上限,
  });
  if (結果.status !== 0) {
    return null;
  }
  try {
    return JSON.parse(結果.stdout);
  } catch {
    return null;
  }
}

function 雜湊檔案(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function 收集檔案(dir, basePath = "") {
  if (!fs.existsSync(dir)) {
    return [];
  }

  let files = [];
  const entries = fs
    .readdirSync(dir, { withFileTypes: true })
    .sort((left, right) => left.name.localeCompare(right.name, "en"));

  for (const entry of entries) {
    const next = path.join(dir, entry.name);
    const relativePath = basePath ? `${basePath}/${entry.name}` : entry.name;

    if (entry.isDirectory()) {
      files = files.concat(收集檔案(next, relativePath));
    } else if (entry.isFile()) {
      const stats = fs.statSync(next);
      files.push({
        path: relativePath,
        absolute_path: next,
        size_bytes: stats.size,
        sha256: 雜湊檔案(next),
      });
    }
  }

  return files;
}

function 建立區段簽章(relativeDir) {
  const files = 收集檔案(path.join(來源根目錄, relativeDir));
  const signatureInput = files.map((file) => `${file.path}:${file.size_bytes}:${file.sha256}`);
  const totalSize = files.reduce((sum, file) => sum + file.size_bytes, 0);

  return {
    file_count: files.length,
    total_size_bytes: totalSize,
    signature: crypto.createHash("sha256").update(signatureInput.join("|")).digest("hex"),
  };
}

function 建立使用者資料簽章() {
  const sections = Object.fromEntries(需同步資料夾.map((設定) => [設定.key, 建立區段簽章(設定.source)]));
  const signatureInput = Object.entries(sections)
    .map(([name, section]) => `${name}:${section.file_count}:${section.total_size_bytes}:${section.signature}`)
    .sort();

  return {
    sections,
    data_signature: crypto.createHash("sha256").update(signatureInput.join("|")).digest("hex"),
  };
}

function 確認必要資料存在() {
  for (const 設定 of 需同步資料夾) {
    const sourcePath = path.join(來源根目錄, 設定.source);
    if (設定.required && !fs.existsSync(sourcePath)) {
      throw new Error(`缺少必要的個人成績單資料夾：${設定.source}`);
    }
  }
}

function 建立Manifest(previousManifest) {
  const usersData = 建立使用者資料簽章();
  const globalStats = 讀取Json(path.join(來源根目錄, "public/data/global_stats.json"), null);
  const manifest = {
    schema_version: 1,
    source: {
      repository: process.env.GITHUB_REPOSITORY || null,
      branch: process.env.GITHUB_REF_NAME || null,
      head_sha: process.env.GITHUB_SHA || null,
      event: process.env.GITHUB_EVENT_NAME || null,
    },
    source_snapshot: {
      generated_at_iso: globalStats?.generated_at_iso || null,
      rankings_updated_at_iso: globalStats?.rankings_updated_at_iso || null,
      total_character_count: globalStats?.total_character_count ?? null,
      total_entry_count: globalStats?.total_entry_count ?? null,
      source_commit: process.env.GITHUB_SHA || null,
    },
    users_data_signature: usersData.data_signature,
    users_data_counts: {
      users: usersData.sections.users.file_count,
      user_entry_details: usersData.sections.user_entry_details.file_count,
      all_users: usersData.sections.all_users.file_count,
      all_user_entry_details: usersData.sections.all_user_entry_details.file_count,
    },
    users_data_sections: usersData.sections,
    sync_status: {
      generated_at_iso: new Date().toISOString(),
      has_content_change: false,
    },
  };

  manifest.source_snapshot.checksum = crypto
    .createHash("sha256")
    .update(JSON.stringify(manifest.source_snapshot))
    .update(JSON.stringify(manifest.users_data_counts))
    .update(JSON.stringify(manifest.users_data_sections))
    .digest("hex");

  const hasContentChange = !previousManifest || previousManifest.users_data_signature !== manifest.users_data_signature;
  manifest.sync_status.has_content_change = hasContentChange;

  return { manifest, hasContentChange };
}

function 建立同步檔案清單() {
  const files = [];
  for (const 設定 of 需同步資料夾) {
    const sourceRoot = path.join(來源根目錄, 設定.source);
    if (!fs.existsSync(sourceRoot)) {
      continue;
    }
    for (const file of 收集檔案(sourceRoot)) {
      files.push({
        source: file.absolute_path,
        target: `${設定.target}/${file.path}`,
      });
    }
  }
  return files;
}

function 寫入Manifest(manifest) {
  const manifestPath = path.join(工作根目錄, "data/sync-manifest.json");
  fs.mkdirSync(path.dirname(manifestPath), { recursive: true });
  fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
}

function 寫入外部檔案到Index(files) {
  if (files.length === 0) {
    return;
  }

  // 使用 git object/index plumbing 直接把 public/data 的檔案寫成下一個 commit。
  // 這是為了避免 checkout 專用 users repo 既有的龐大資料與歷史，降低 GitHub runner 磁碟用量。
  const hashInput = `${files.map((file) => file.source).join("\n")}\n`;
  const hashOutput = 執行Git(["hash-object", "-w", "--stdin-paths"], {
    input: hashInput,
    maxBuffer: Git輸出緩衝上限,
  })
    .trim()
    .split(/\r?\n/)
    .filter(Boolean);

  if (hashOutput.length !== files.length) {
    throw new Error(`git hash-object 回傳 ${hashOutput.length} 個 object id，但待同步檔案有 ${files.length} 個。`);
  }

  const indexInfo = files
    .map((file, index) => `100644 ${hashOutput[index]}\t${file.target}\n`)
    .join("");
  執行Git(["update-index", "--add", "--index-info"], {
    input: indexInfo,
    maxBuffer: Git輸出緩衝上限,
  });
}

function 初始化Repo() {
  fs.rmSync(工作根目錄, { recursive: true, force: true });
  fs.mkdirSync(工作根目錄, { recursive: true });

  執行Git(["init", "-q"]);
  執行Git(["remote", "add", "origin", 專用RepoUrl]);
  執行Git(["config", "core.autocrlf", "false"]);
  執行Git(["config", "user.name", "github-actions[bot]"]);
  執行Git(["config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"]);
  執行Git(["fetch", "--depth=1", "--filter=blob:none", "origin", 目標分支]);
  const head = 執行Git(["rev-parse", "FETCH_HEAD"]).trim();
  執行Git(["update-ref", `refs/heads/${目標分支}`, head]);
  執行Git(["symbolic-ref", "HEAD", `refs/heads/${目標分支}`]);
  執行Git(["read-tree", "HEAD"]);
}

function 建立Commit() {
  const previousManifest = 讀取上一版Manifest();
  const { manifest, hasContentChange } = 建立Manifest(previousManifest);
  const files = 建立同步檔案清單();

  寫入Manifest(manifest);
  執行Git(["rm", "-r", "--cached", "--ignore-unmatch", ...需替換的資料路徑, "data/sync-manifest.json"]);
  寫入外部檔案到Index(files);
  執行Git(["add", "data/sync-manifest.json"]);

  const dataChanged = 檢查Git是否有差異(["diff", "--cached", "--quiet", "HEAD", "--", ...需替換的資料路徑]);
  const repoChanged = 檢查Git是否有差異([
    "diff",
    "--cached",
    "--quiet",
    "HEAD",
    "--",
    ...需替換的資料路徑,
    "data/sync-manifest.json",
  ]);

  if (!repoChanged) {
    console.log("沒有需要同步的個人成績單資料變更。");
    return false;
  }

  if (!hasContentChange && !dataChanged) {
    console.log("只有個人成績單同步 metadata 變更，略過 commit 以避免產生雜訊紀錄。");
    return false;
  }

  執行Git([
    "commit",
    "-m",
    "chore(data): 同步個人成績單資料到專用資料庫",
    "-m",
    "將最新生成的使用者排行榜資料同步到外部 users Repo，主站僅保留公開資料。",
    "-m",
    "資料同步來源：public/data/users、public/data/user-entry-details、public/data/all/users、public/data/all/user-entry-details。",
  ]);
  return true;
}

async function 等待(ms) {
  await new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function main() {
  確認必要資料存在();

  for (let attempt = 1; attempt <= 3; attempt += 1) {
    初始化Repo();
    const hasCommit = 建立Commit();
    if (!hasCommit) {
      return;
    }

    if (乾跑) {
      console.log("已啟用 dry run：個人成績單 commit 已在本機建立，但不會推送。");
      return;
    }

    const push = childProcess.spawnSync("git", ["push", "origin", `HEAD:${目標分支}`], {
      cwd: 工作根目錄,
      encoding: "utf8",
      maxBuffer: Git輸出緩衝上限,
    });
    if (push.status === 0) {
      console.log("個人成績單資料已同步到專用 users repo。");
      return;
    }

    console.warn(`第 ${attempt} 次推送個人成績單資料失敗：`);
    console.warn(隱藏敏感內容(push.stderr || push.stdout || ""));
    if (attempt < 3) {
      await 等待(attempt * 5000);
    }
  }

  throw new Error("多次重試後仍無法推送個人成績單資料。");
}

await main();
