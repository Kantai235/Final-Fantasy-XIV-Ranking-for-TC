import { existsSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const minimumVersion = [3, 11];

function candidatePythonCommands() {
  const candidates = [];
  const envPython = process.env.FFXIV_TC_PYTHON?.trim();
  if (envPython) {
    candidates.push(envPython);
  }

  const venvPython = process.platform === "win32"
    ? path.join(rootDir, ".venv", "Scripts", "python.exe")
    : path.join(rootDir, ".venv", "bin", "python");
  candidates.push(venvPython, "python3.11", "python3", "python");

  return Array.from(new Set(candidates.filter(Boolean)));
}

function inspectPython(command) {
  const result = spawnSync(command, [
    "-c",
    "import sys, json; print(json.dumps({'executable': sys.executable, 'version': list(sys.version_info[:3])}))",
  ], {
    cwd: rootDir,
    encoding: "utf8",
    shell: false,
    stdio: ["ignore", "pipe", "pipe"],
  });

  if (result.error) {
    return { ok: false, reason: result.error.message };
  }
  if (result.status !== 0) {
    return { ok: false, reason: (result.stderr || result.stdout || `exit ${result.status}`).trim() };
  }

  try {
    const info = JSON.parse(result.stdout.trim());
    const version = Array.isArray(info.version) ? info.version : [];
    const meetsMinimum = version[0] > minimumVersion[0]
      || (version[0] === minimumVersion[0] && version[1] >= minimumVersion[1]);
    if (!meetsMinimum) {
      return {
        ok: false,
        reason: `Python ${version.join(".")} 低於專案需求 ${minimumVersion.join(".")}+`,
      };
    }
    return { ok: true, executable: info.executable || command, version };
  } catch (error) {
    return { ok: false, reason: `無法解析 Python 版本資訊：${error.message}` };
  }
}

function resolvePython() {
  const attempts = [];
  for (const command of candidatePythonCommands()) {
    if (command.includes(path.sep) && !existsSync(command)) {
      attempts.push(`${command}: 檔案不存在`);
      continue;
    }

    const inspected = inspectPython(command);
    if (inspected.ok) {
      return inspected.executable;
    }
    attempts.push(`${command}: ${inspected.reason}`);
  }

  throw new Error(
    [
      `找不到 Python ${minimumVersion.join(".")}+。`,
      "請先建立 .venv，或設定 FFXIV_TC_PYTHON 指向可用的 Python 3.11+ 直譯器。",
      "已嘗試：",
      ...attempts.map((attempt) => `- ${attempt}`),
    ].join("\n"),
  );
}

let pythonExecutable = "";
try {
  pythonExecutable = resolvePython();
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}

const result = spawnSync(pythonExecutable, process.argv.slice(2), {
  cwd: rootDir,
  env: process.env,
  stdio: "inherit",
});

if (result.error) {
  console.error(`Python 執行失敗：${result.error.message}`);
  process.exit(1);
}

process.exit(result.status ?? 1);
