const FFLOGS_REPORT_BASE_URL = "https://www.fflogs.com/reports";
const XIVANALYSIS_REPORT_BASE_URL = "https://xivanalysis.com/fflogs";
const FFREPLAY_URL = "https://ffreplay.vjoi.cn/ffreplay.html";

function firstPresent(...values) {
  return values.find((value) => value !== null && value !== undefined && String(value).trim() !== "");
}

function toPositiveInteger(value) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) && numberValue > 0 ? Math.trunc(numberValue) : null;
}

function extractReportCodeFromUrl(reportUrl) {
  const match = String(reportUrl || "").match(/fflogs\.com\/reports\/([^/?#]+)/i);
  return match ? decodeURIComponent(match[1]) : null;
}

export function getReportCode(record = {}) {
  return firstPresent(record.reportCode, record.report_code, extractReportCodeFromUrl(record.reportUrl || record.report_url)) || null;
}

export function getFightId(record = {}) {
  return toPositiveInteger(firstPresent(record.fightId, record.fight_id));
}

export function getFflogsSourceId(record = {}) {
  return toPositiveInteger(firstPresent(record.fflogsSourceId, record.fflogs_source_id, record.fflogs_id, record.source_id));
}

export function buildFflogsReportUrl(record = {}) {
  const reportCode = getReportCode(record);
  const reportUrl = firstPresent(record.reportUrl, record.report_url);
  const fightId = getFightId(record);

  if (reportCode) {
    const url = new URL(`${FFLOGS_REPORT_BASE_URL}/${encodeURIComponent(reportCode)}`);
    if (fightId !== null) {
      url.searchParams.set("fight", String(fightId));
    }
    return url.toString();
  }

  if (!reportUrl) {
    return null;
  }

  try {
    const url = new URL(reportUrl);
    if (fightId !== null) {
      url.searchParams.set("fight", String(fightId));
    }
    return url.toString();
  } catch {
    return String(reportUrl);
  }
}

export function buildXivanalysisReportUrl(record = {}) {
  const reportCode = getReportCode(record);
  if (!reportCode) {
    return null;
  }

  const fightId = getFightId(record);
  const sourceId = getFflogsSourceId(record);
  const pathParts = [XIVANALYSIS_REPORT_BASE_URL, encodeURIComponent(reportCode)];
  if (fightId !== null) {
    pathParts.push(String(fightId));
    if (sourceId !== null) {
      pathParts.push(String(sourceId));
    }
  }
  return pathParts.join("/");
}

export function buildFfreplayReportUrl(record = {}) {
  const reportCode = getReportCode(record);
  const fightId = getFightId(record);
  if (!reportCode || fightId === null) {
    return null;
  }

  const fflogsUrl = buildFflogsReportUrl({ report_code: reportCode, fight_id: fightId });
  return `${FFREPLAY_URL}?url=${encodeURIComponent(fflogsUrl)}`;
}

export function buildReportExternalLinks(record = {}) {
  const fflogsUrl = buildFflogsReportUrl(record);
  const xivanalysisUrl = buildXivanalysisReportUrl(record);
  const ffreplayUrl = buildFfreplayReportUrl(record);

  return [
    fflogsUrl
      ? {
          key: "fflogs",
          label: "FFLogs",
          url: fflogsUrl,
          title: "在 FFLogs 開啟這場戰鬥",
        }
      : null,
    xivanalysisUrl
      ? {
          key: "xivanalysis",
          label: "XIV Analysis",
          url: xivanalysisUrl,
          title: getFflogsSourceId(record) === null ? "在 XIV Analysis 開啟這份報告" : "在 XIV Analysis 開啟這名玩家",
        }
      : null,
    ffreplayUrl
      ? {
          key: "ffreplay",
          label: "FF Replay",
          url: ffreplayUrl,
          title: "在 FF Replay 開啟這場戰鬥",
        }
      : null,
  ].filter(Boolean);
}
