// 近期動態與個人成績趨勢共用同一份時間軸事件，避免同一個繁中服版本更新
// 在兩張圖表各自維護日期與副本名稱，日後新增開放事件時只需更新這裡。
export const activityLogTimelineAnnotations = Object.freeze([
  {
    date: "2025-12-16",
    region: "international",
    patch: "7.4",
    title: "國際服 7.4",
    detail: "霧中奇境",
    importance: "secondary",
  },
  {
    date: "2026-01-27",
    region: "international",
    patch: "7.41",
    title: "國際服 7.41",
    detail: "霧中奇境",
    importance: "secondary",
  },
  {
    date: "2026-02-10",
    region: "tc",
    patch: "7.01",
    title: "繁中服 7.01",
    detail: "輕量級",
  },
  {
    date: "2026-03-03",
    region: "international",
    patch: "7.45",
    title: "國際服 7.45",
    detail: "霧中奇境",
    importance: "secondary",
  },
  {
    date: "2026-03-10",
    region: "tc",
    patch: "7.05",
    title: "繁中服 7.05",
    detail: "零式 輕量級",
  },
  {
    date: "2026-04-21",
    region: "tc",
    patch: "7.1",
    title: "繁中服 7.1",
    detail: "極 永恆女王、幻 白虎",
  },
  {
    date: "2026-04-28",
    region: "international",
    patch: "7.5",
    title: "國際服 7.5",
    detail: "天際的行路",
    importance: "secondary",
  },
  {
    date: "2026-05-26",
    region: "tc",
    patch: "7.11",
    title: "繁中服 7.11",
    detail: "絕 伊甸",
  },
  {
    date: "2026-06-02",
    region: "international",
    patch: "7.51",
    title: "國際服 7.51",
    detail: "天際的行路",
    importance: "secondary",
  },
  {
    date: "2026-06-23",
    region: "tc",
    patch: "7.15",
    title: "繁中服 7.15",
    detail: "滅 黑暗之雲",
  },
  {
    date: "2026-07-28",
    region: "international",
    patch: "7.55",
    title: "國際服 7.55",
    detail: "天際的行路",
    importance: "secondary",
  },
  {
    date: "2026-07-28",
    region: "tc",
    patch: "7.2",
    title: "繁中服 7.2",
    detail: "極 澤蓮尼亞、次重量級",
  },
  {
    date: "2026-08-04",
    region: "tc",
    patch: "7.2",
    title: "繁中服 7.2",
    detail: "零式 次重量級",
  },
  {
    date: "2026-09-08",
    region: "international",
    patch: "7.56",
    title: "國際服 7.56",
    detail: "天際的行路",
    importance: "secondary",
  },
]);

/**
 * 建立個人成績趨勢使用的繁中服版本更新切點。
 *
 * 近期動態以繁中服日曆日標記事件，因此這裡也固定用 UTC+8 的當日零時
 * 對齊時間軸。顯示文字刻意移除地區前綴，並收斂副本名稱中的排版空白，
 * 例如「繁中服 7.11」與「絕 伊甸」會顯示為「7.11 絕伊甸」。
 */
export function 建立繁中服版本更新切點(起始時間戳記, 結束時間戳記) {
  if (
    !Number.isFinite(起始時間戳記)
    || !Number.isFinite(結束時間戳記)
    || 結束時間戳記 <= 起始時間戳記
  ) {
    return [];
  }

  const 時間範圍 = 結束時間戳記 - 起始時間戳記;
  return activityLogTimelineAnnotations
    .filter((標註) => 標註.region === "tc")
    .map((標註, index) => {
      const 切點時間戳記 = Date.parse(`${標註.date}T00:00:00+08:00`);
      // 邊界上的事件不另畫線，避免標籤被裁切，也避免與起迄刻度重疊。
      if (!Number.isFinite(切點時間戳記) || 切點時間戳記 <= 起始時間戳記 || 切點時間戳記 >= 結束時間戳記) {
        return null;
      }

      const 副本名稱 = String(標註.detail || "").replace(/\s+/g, "").trim();
      return {
        key: `tc-version-update-${標註.date}-${標註.patch}-${index}`,
        date: 標註.date,
        patch: 標註.patch,
        detail: 副本名稱,
        label: [標註.patch, 副本名稱].filter(Boolean).join(" "),
        starts_at_iso: new Date(切點時間戳記).toISOString(),
        x: Number((((切點時間戳記 - 起始時間戳記) / 時間範圍) * 100).toFixed(2)),
      };
    })
    .filter(Boolean);
}
