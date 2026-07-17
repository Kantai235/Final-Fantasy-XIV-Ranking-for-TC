// 副本分類與量級屬於公開副本清單的領域語意。集中在這裡可讓排行榜、統計與隊伍榜
// 使用同一個選單結構，而不是在每個頁面各自猜測「零式」該怎麼再分組。
export const 副本分類順序 = Object.freeze(["零式", "絕", "極", "滅", "幻"]);
const 副本選單分類順序 = Object.freeze(["全部", ...副本分類順序]);

const 副本分類顯示名稱 = Object.freeze({
  零式: "零式",
  絕: "絕本",
  極: "極本",
  滅: "滅本",
  幻: "幻本",
  全部: "全部",
});

function 比較文字(left, right) {
  return String(left || "").localeCompare(String(right || ""), "zh-Hant");
}

/**
 * 將不同公開資料產物中的副本列正規化成選單所需的兩層結構。
 *
 * 外層固定是副本類型；只有零式會再依資料管線已輸出的
 * `profile_summary_savage_tier` 分量級。這樣新增量級時，只要公開清單帶有
 * key、label、order 與 floor，選單便會自動出現，不需要再為每個 Vue 頁面補條件。
 *
 * @template T
 * @param {T[]} 項目列表
 * @param {{
 *   取鍵值: (項目: T) => string,
 *   取名稱: (項目: T) => string,
 *   取分類: (項目: T) => string,
 *   取零式量級?: (項目: T) => {key?: string, label?: string, order?: number, floor?: number} | null,
 * }} 設定
 * @returns {{分類: string, 顯示名稱: string, 子分組: {鍵值: string, 名稱: string, 顯示標題: boolean, 項目: {鍵值: string, 名稱: string, 原始資料: T, 排序索引: number, 樓層: number}[]}[]}[]}
 */
export function 建立副本選單分組(項目列表, { 取鍵值, 取名稱, 取分類, 取零式量級 = () => null }) {
  const 分類索引 = new Map();

  for (const 分類 of 副本選單分類順序) {
    分類索引.set(分類, []);
  }

  for (const [排序索引, 原始資料] of (Array.isArray(項目列表) ? 項目列表 : []).entries()) {
    const 鍵值 = 取鍵值(原始資料);
    if (!鍵值) {
      continue;
    }

    const 分類 = 取分類(原始資料) || "其他";
    if (!分類索引.has(分類)) {
      分類索引.set(分類, []);
    }

    const 量級 = 分類 === "零式" ? 取零式量級(原始資料) : null;
    分類索引.get(分類).push({
      鍵值,
      名稱: 取名稱(原始資料) || 鍵值,
      原始資料,
      排序索引,
      量級鍵值: 量級?.key || "未分類量級",
      量級名稱: 量級?.label || "其他量級",
      量級順序: Number.isFinite(Number(量級?.order)) ? Number(量級.order) : Number.MAX_SAFE_INTEGER,
      樓層: Number.isFinite(Number(量級?.floor)) ? Number(量級.floor) : Number.MAX_SAFE_INTEGER,
    });
  }

  return Array.from(分類索引.entries())
    .map(([分類, 項目]) => {
      if (分類 !== "零式") {
        return {
          分類,
          顯示名稱: 副本分類顯示名稱[分類] || 分類,
          子分組: [{
            鍵值: 分類,
            名稱: "",
            顯示標題: false,
            項目: 項目.sort((left, right) => left.排序索引 - right.排序索引),
          }],
        };
      }

      const 量級索引 = new Map();
      for (const 副本 of 項目) {
        if (!量級索引.has(副本.量級鍵值)) {
          量級索引.set(副本.量級鍵值, {
            鍵值: 副本.量級鍵值,
            名稱: 副本.量級名稱,
            順序: 副本.量級順序,
            項目: [],
          });
        }
        量級索引.get(副本.量級鍵值).項目.push(副本);
      }

      return {
        分類,
        顯示名稱: 副本分類顯示名稱[分類] || 分類,
        子分組: Array.from(量級索引.values())
          .sort((left, right) => left.順序 - right.順序 || 比較文字(left.名稱, right.名稱))
          .map((量級) => ({
            鍵值: 量級.鍵值,
            名稱: 量級.名稱,
            顯示標題: true,
            項目: 量級.項目.sort((left, right) => left.樓層 - right.樓層 || left.排序索引 - right.排序索引),
          })),
      };
    })
    .filter((分組) => 分組.子分組.some((子分組) => 子分組.項目.length > 0))
    .sort((left, right) => {
      const leftIndex = 副本選單分類順序.indexOf(left.分類);
      const rightIndex = 副本選單分類順序.indexOf(right.分類);
      return (leftIndex < 0 ? Number.MAX_SAFE_INTEGER : leftIndex) - (rightIndex < 0 ? Number.MAX_SAFE_INTEGER : rightIndex)
        || 比較文字(left.顯示名稱, right.顯示名稱);
    });
}
