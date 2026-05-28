export const 公告關閉儲存鍵 = "ffxiv-tc-dismissed-announcements";

const 允許公告層級 = new Set(["info", "update", "warning"]);
const 允許連結協定 = new Set(["http:", "https:", "mailto:"]);

function 轉為乾淨文字(value) {
  return String(value ?? "").trim();
}

function 解析公告時間(value) {
  const 文字 = 轉為乾淨文字(value);
  if (!文字) {
    return null;
  }

  const 時間 = new Date(文字).getTime();
  return Number.isFinite(時間) ? 時間 : null;
}

function 取得目前時間毫秒(nowMs = Date.now()) {
  if (nowMs instanceof Date) {
    return nowMs.getTime();
  }

  const 時間 = Number(nowMs);
  return Number.isFinite(時間) ? 時間 : Date.now();
}

export function 正規化公告連結(link) {
  const label = 轉為乾淨文字(link?.label || link?.name || link?.title);
  const url = 轉為乾淨文字(link?.url || link?.href);
  if (!label || !url) {
    return null;
  }

  try {
    const parsedUrl = new URL(url, "https://ranking.init.engineer");
    if (!允許連結協定.has(parsedUrl.protocol)) {
      return null;
    }
  } catch {
    return null;
  }

  return {
    label,
    url,
  };
}

function 正規化公告(item, index) {
  const id = 轉為乾淨文字(item?.id);
  const title = 轉為乾淨文字(item?.title);
  const summary = 轉為乾淨文字(item?.summary);
  if (!id || !title || !summary) {
    return null;
  }

  const detailsMarkdown = 轉為乾淨文字(item?.details_markdown ?? item?.body_markdown ?? item?.detail_markdown ?? summary);
  const severity = 允許公告層級.has(item?.severity) ? item.severity : "info";
  const links = Array.isArray(item?.links) ? item.links.map(正規化公告連結).filter(Boolean) : [];

  return {
    id,
    title,
    summary,
    details_markdown: detailsMarkdown || summary,
    starts_at_iso: 轉為乾淨文字(item?.starts_at_iso ?? item?.start_at_iso),
    expires_at_iso: 轉為乾淨文字(item?.expires_at_iso ?? item?.expire_at_iso),
    published_at_iso: 轉為乾淨文字(item?.published_at_iso),
    severity,
    links,
    排序序號: index,
  };
}

function 公告排序時間(announcement) {
  return (
    解析公告時間(announcement.starts_at_iso)
    ?? 解析公告時間(announcement.published_at_iso)
    ?? 解析公告時間(announcement.expires_at_iso)
    ?? 0
  );
}

export function 正規化公告資料(payload) {
  const list = Array.isArray(payload) ? payload : payload?.announcements;
  if (!Array.isArray(list)) {
    return [];
  }

  return list
    .map(正規化公告)
    .filter(Boolean)
    .sort((left, right) => {
      const timeDiff = 公告排序時間(right) - 公告排序時間(left);
      return timeDiff || left.排序序號 - right.排序序號 || left.id.localeCompare(right.id, "zh-Hant-TW");
    });
}

export function 取得公告狀態(announcement, nowMs = Date.now()) {
  const now = 取得目前時間毫秒(nowMs);
  const startsAt = 解析公告時間(announcement?.starts_at_iso);
  const expiresAt = 解析公告時間(announcement?.expires_at_iso);

  if (startsAt !== null && now < startsAt) {
    return "scheduled";
  }
  if (expiresAt !== null && now > expiresAt) {
    return "expired";
  }
  return "active";
}

export function 取得公告狀態文字(announcement, nowMs = Date.now()) {
  const 狀態 = 取得公告狀態(announcement, nowMs);
  if (狀態 === "scheduled") {
    return "尚未開始";
  }
  if (狀態 === "expired") {
    return "已過期";
  }
  return "進行中";
}

export function 取得主動公告列表(announcements, dismissedIds = [], nowMs = Date.now()) {
  const 已關閉 = dismissedIds instanceof Set ? dismissedIds : new Set(dismissedIds);
  return (Array.isArray(announcements) ? announcements : []).filter((announcement) => {
    return 取得公告狀態(announcement, nowMs) === "active" && !已關閉.has(announcement.id);
  });
}

function 取得Storage(storage) {
  if (storage) {
    return storage;
  }
  if (typeof globalThis !== "undefined" && globalThis.localStorage) {
    return globalThis.localStorage;
  }
  return null;
}

export function 讀取已關閉公告(storage) {
  const storageTarget = 取得Storage(storage);
  if (!storageTarget) {
    return new Set();
  }

  try {
    const rawValue = storageTarget.getItem(公告關閉儲存鍵);
    if (!rawValue) {
      return new Set();
    }

    const parsedValue = JSON.parse(rawValue);
    const ids = Array.isArray(parsedValue) ? parsedValue : parsedValue?.ids;
    if (!Array.isArray(ids)) {
      return new Set();
    }

    return new Set(ids.map(轉為乾淨文字).filter(Boolean));
  } catch {
    return new Set();
  }
}

export function 寫入已關閉公告(ids, storage) {
  const storageTarget = 取得Storage(storage);
  if (!storageTarget) {
    return;
  }

  const payload = {
    schema_version: 1,
    ids: Array.from(ids instanceof Set ? ids : new Set(ids)).filter(Boolean),
  };
  storageTarget.setItem(公告關閉儲存鍵, JSON.stringify(payload));
}

function 建立文字片段(text) {
  return {
    type: "text",
    text,
  };
}

function 解析行內Markdown(text) {
  const parts = [];
  const source = String(text ?? "");
  const tokenPattern = /(\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)\s]+)\))/g;
  let cursor = 0;

  for (const match of source.matchAll(tokenPattern)) {
    if (match.index > cursor) {
      parts.push(建立文字片段(source.slice(cursor, match.index)));
    }

    if (match[2]) {
      parts.push({
        type: "strong",
        text: match[2],
      });
    } else if (match[3]) {
      parts.push({
        type: "code",
        text: match[3],
      });
    } else if (match[4] && match[5]) {
      const link = 正規化公告連結({
        label: match[4],
        url: match[5],
      });
      parts.push(link ? { type: "link", ...link } : 建立文字片段(match[0]));
    }

    cursor = match.index + match[0].length;
  }

  if (cursor < source.length) {
    parts.push(建立文字片段(source.slice(cursor)));
  }

  return parts.length > 0 ? parts : [建立文字片段(source)];
}

export function 解析公告Markdown(markdown) {
  const blocks = [];
  const paragraphLines = [];
  let activeList = null;

  function flushParagraph() {
    if (paragraphLines.length === 0) {
      return;
    }
    blocks.push({
      type: "paragraph",
      parts: 解析行內Markdown(paragraphLines.join(" ")),
    });
    paragraphLines.length = 0;
  }

  function flushList() {
    if (!activeList) {
      return;
    }
    blocks.push(activeList);
    activeList = null;
  }

  for (const rawLine of String(markdown ?? "").replace(/\r\n/g, "\n").split("\n")) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }

    const headingMatch = line.match(/^(#{1,4})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      blocks.push({
        type: "heading",
        level: headingMatch[1].length,
        parts: 解析行內Markdown(headingMatch[2]),
      });
      continue;
    }

    const unorderedMatch = line.match(/^[-*]\s+(.+)$/);
    const orderedMatch = line.match(/^\d+[.)]\s+(.+)$/);
    const listMatch = unorderedMatch || orderedMatch;
    if (listMatch) {
      flushParagraph();
      const ordered = Boolean(orderedMatch);
      if (!activeList || activeList.ordered !== ordered) {
        flushList();
        activeList = {
          type: "list",
          ordered,
          items: [],
        };
      }
      activeList.items.push(解析行內Markdown(listMatch[1]));
      continue;
    }

    flushList();
    paragraphLines.push(line);
  }

  flushParagraph();
  flushList();
  return blocks;
}
