import { writeFile } from "node:fs/promises";
import { setTimeout as sleep } from "node:timers/promises";

const transientWindowsWriteErrors = new Set(["UNKNOWN", "EBUSY", "EPERM", "EACCES"]);

/**
 * Windows Defender、搜尋索引與同步軟體可能短暫以不允許覆寫的共享模式開啟
 * public/data JSON。資料建置不應因一次瞬間鎖定而整輪失敗，但真正的權限或格式
 * 問題也不能被無限隱藏，因此只對已知暫時性錯誤做有上限的遞增等待。
 */
export async function writeFileWithRetry(filePath, data, options = "utf8") {
  const maxAttempts = process.platform === "win32" ? 10 : 1;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      await writeFile(filePath, data, options);
      return;
    } catch (error) {
      const canRetry = transientWindowsWriteErrors.has(error?.code) && attempt < maxAttempts;
      if (!canRetry) {
        throw error;
      }
      const waitMs = attempt * 500;
      console.warn(`輸出檔案暫時被鎖定，${waitMs} 毫秒後重試（${attempt}/${maxAttempts}）：${filePath}`);
      await sleep(waitMs);
    }
  }
}
