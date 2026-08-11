import childProcess from "node:child_process";
import path from "node:path";

const 專案根目錄 = path.resolve(process.env.WORKFLOW_DATA_SNAPSHOT_REPO_DIR || process.cwd());
const 原始參數 = process.argv.slice(2);
const 路徑分隔位置 = 原始參數.indexOf("--");
const 選項參數 = 路徑分隔位置 >= 0 ? 原始參數.slice(0, 路徑分隔位置) : 原始參數;
const 資料路徑 = 路徑分隔位置 >= 0 ? 原始參數.slice(路徑分隔位置 + 1) : [];
const Git輸出緩衝上限 = 128 * 1024 * 1024;
const 快照版本標記 = "Workflow-Data-Snapshot: v1";
const 快照標題 = "chore(data): 更新自動化資料快照";

function 讀取選項(name, fallback = "") {
  const inlinePrefix = `${name}=`;
  for (let index = 0; index < 選項參數.length; index += 1) {
    const value = 選項參數[index];
    if (value === name) {
      return 選項參數[index + 1] || fallback;
    }
    if (value.startsWith(inlinePrefix)) {
      return value.slice(inlinePrefix.length) || fallback;
    }
  }
  return fallback;
}

const 遠端名稱 = 讀取選項("--remote", process.env.WORKFLOW_DATA_SNAPSHOT_REMOTE || "origin");
const 目標分支 = 讀取選項("--branch", process.env.GITHUB_REF_NAME || "main");

function 執行Git(參數, { allowFailure = false } = {}) {
  const result = childProcess.spawnSync("git", 參數, {
    cwd: 專案根目錄,
    encoding: "utf8",
    maxBuffer: Git輸出緩衝上限,
  });

  if (result.error) {
    throw result.error;
  }
  if (!allowFailure && result.status !== 0) {
    throw new Error(
      `git ${參數.join(" ")} 執行失敗（exit code ${result.status}）\n${result.stderr || result.stdout || ""}`,
    );
  }
  return result;
}

function 讀取Git輸出(參數) {
  return String(執行Git(參數).stdout || "").trim();
}

function 讀取遠端Sha() {
  const result = 執行Git(["ls-remote", "--exit-code", 遠端名稱, `refs/heads/${目標分支}`], {
    allowFailure: true,
  });
  if (result.status !== 0) {
    throw new Error(
      `無法讀取 ${遠端名稱}/${目標分支} 的遠端 SHA。\n${result.stderr || result.stdout || ""}`,
    );
  }
  return String(result.stdout || "")
    .trim()
    .split(/\s+/)[0];
}

function 快照CommitMessage() {
  return [
    快照標題,
    "",
    "Why：GitHub Actions 會頻繁更新大量排行榜與部署稽核資料，若每輪追加 commit，會讓 Git 歷史與儲存庫容量無上限成長。",
    "主要變更：更新 data 與 public/data 的可追溯資料產物，並將同一程式碼歷史區段中的自動化更新收斂為一筆滾動快照。",
    "測試/驗證：本 workflow 已完成 FFLogs 抓取、資料建置、公開資料契約驗證與 Pages 建置；快照推送使用明確舊 SHA 的 force-with-lease。",
    "",
    快照版本標記,
  ].join("\n");
}

function 是受管理快照(commitSha) {
  const message = 讀取Git輸出(["show", "-s", "--format=%B", commitSha]);
  return message.split(/\r?\n/).some((line) => line.trim() === 快照版本標記);
}

function 建立或收斂快照() {
  if (資料路徑.length === 0) {
    throw new Error("缺少要納入快照的路徑；請在 -- 之後列出資料路徑。");
  }

  執行Git(["config", "user.name", "github-actions[bot]"]);
  執行Git(["config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"]);
  執行Git(["add", "--all", "--", ...資料路徑]);

  const staged = 執行Git(["diff", "--cached", "--quiet"], { allowFailure: true });
  if (staged.status === 0) {
    console.log("指定資料路徑沒有變更，略過快照提交。");
    return;
  }
  if (staged.status !== 1) {
    throw new Error(`無法檢查已暫存變更。\n${staged.stderr || staged.stdout || ""}`);
  }

  const unstaged = 執行Git(["diff", "--quiet"], { allowFailure: true });
  if (unstaged.status === 1) {
    const status = 讀取Git輸出(["status", "--short", "--untracked-files=no"]);
    throw new Error(`建立資料快照前仍有未暫存的已追蹤檔案；請確認資料路徑是否遺漏。\n${status}`);
  }
  if (unstaged.status !== 0) {
    throw new Error(`無法檢查工作樹狀態。\n${unstaged.stderr || unstaged.stdout || ""}`);
  }

  const oldHead = 讀取Git輸出(["rev-parse", "HEAD"]);
  const remoteHead = 讀取遠端Sha();
  if (remoteHead !== oldHead) {
    throw new Error(
      `遠端 ${目標分支} 已從本輪起點 ${oldHead} 更新為 ${remoteHead}；拒絕改寫新程式碼 commit。`,
    );
  }

  const message = 快照CommitMessage();
  const managedSnapshot = 是受管理快照(oldHead);
  let originalParents = [];
  if (managedSnapshot) {
    originalParents = 讀取Git輸出(["show", "-s", "--format=%P", oldHead])
      .split(/\s+/)
      .filter(Boolean);
    if (originalParents.length !== 1) {
      throw new Error("受管理資料快照必須剛好有一個 parent，拒絕改寫非預期的 Git 歷史。");
    }

    // fetch-depth=1 會把 HEAD 當成 shallow root；amend 時可能意外切斷程式碼歷史。
    // workflow 因此至少取得兩層，這裡再以 cat-file 強制驗證 parent object 真的存在。
    const parentExists = 執行Git(["cat-file", "-e", `${originalParents[0]}^{commit}`], { allowFailure: true });
    if (parentExists.status !== 0) {
      throw new Error("資料快照的 parent commit 未取得；請將 checkout/fetch depth 設為 2 以上再重試。");
    }

    執行Git(["commit", "--amend", "--reset-author", "--no-gpg-sign", "-m", message]);
  } else {
    執行Git(["commit", "--no-gpg-sign", "-m", message]);
  }

  const newHead = 讀取Git輸出(["rev-parse", "HEAD"]);
  if (managedSnapshot) {
    const nextParents = 讀取Git輸出(["show", "-s", "--format=%P", newHead])
      .split(/\s+/)
      .filter(Boolean);
    if (nextParents.length !== 1 || nextParents[0] !== originalParents[0]) {
      throw new Error("收斂快照後的 parent 已改變，為避免切斷程式碼歷史而停止推送。");
    }
  }

  const pushArgs = [
    "push",
    `--force-with-lease=refs/heads/${目標分支}:${oldHead}`,
    遠端名稱,
    `HEAD:refs/heads/${目標分支}`,
  ];
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const pushed = 執行Git(pushArgs, { allowFailure: true });
    if (pushed.status === 0) {
      console.log(
        managedSnapshot
          ? `已將 ${目標分支} 的自動化資料收斂為新快照 ${newHead}。`
          : `已在 ${目標分支} 建立自動化資料快照 ${newHead}。`,
      );
      return;
    }

    const currentRemoteHead = 讀取遠端Sha();
    if (currentRemoteHead === newHead) {
      console.log(`遠端 ${目標分支} 已是新快照 ${newHead}，視為推送成功。`);
      return;
    }
    if (currentRemoteHead !== oldHead) {
      throw new Error(
        `推送期間遠端 ${目標分支} 已更新為 ${currentRemoteHead}；force-with-lease 已阻止覆寫他人的 commit。`,
      );
    }
    if (attempt === 3) {
      throw new Error(
        `第 ${attempt} 次推送資料快照仍失敗。\n${pushed.stderr || pushed.stdout || ""}`,
      );
    }
  }
}

建立或收斂快照();
