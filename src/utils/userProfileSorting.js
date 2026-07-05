import {
  分位顯示模式PR,
  計算PR值,
  正規化分位顯示模式,
  轉為數字,
} from "./formatters.js";

function 取得有效排名數值(排名) {
  const 數值 = 轉為數字(排名);
  return 數值 !== null && 數值 > 0 ? 數值 : null;
}

export function 取得成績職業排名值(成績) {
  return 取得有效排名數值(成績?.job_rank ?? 成績?.rank);
}

export function 取得成績前段百分位(成績) {
  const 百分位 = 轉為數字(成績?.performance?.top_percent);
  return 百分位 !== null && 百分位 >= 0 ? 百分位 : null;
}

export function 取得成績PR值(成績) {
  return 計算PR值(成績?.performance);
}

function 比較可空數值(左值, 右值, 方向) {
  if (左值 !== null || 右值 !== null) {
    if (左值 === null) {
      return 1;
    }
    if (右值 === null) {
      return -1;
    }
    if (左值 !== 右值) {
      return 方向 === "desc" ? 右值 - 左值 : 左值 - 右值;
    }
  }

  return 0;
}

export function 比較個人成績分位顯示排序(左成績, 右成績, 顯示模式) {
  if (正規化分位顯示模式(顯示模式) === 分位顯示模式PR) {
    return 比較可空數值(取得成績PR值(左成績), 取得成績PR值(右成績), "desc");
  }

  return 比較可空數值(取得成績前段百分位(左成績), 取得成績前段百分位(右成績), "asc");
}

export function 個人成績代表是否較佳(候選, 目前最佳, 顯示模式, 後援比較) {
  const 後援 = typeof 後援比較 === "function" ? 後援比較 : () => false;
  if (!候選) {
    return false;
  }
  if (!目前最佳) {
    return true;
  }

  if (正規化分位顯示模式(顯示模式) === 分位顯示模式PR) {
    const PR差 = 比較可空數值(取得成績PR值(候選), 取得成績PR值(目前最佳), "desc");
    if (PR差 !== 0) {
      return PR差 < 0;
    }
    return 後援(候選, 目前最佳);
  }

  // 前 N% 模式延續既有代表列語意：先看同職 Rank，再看 top_percent。
  // 這是為了保留原本「排名數字越前面越亮眼」的顯示順序，避免切回前 N% 時排序行為改變。
  const 排名差 = 比較可空數值(取得成績職業排名值(候選), 取得成績職業排名值(目前最佳), "asc");
  if (排名差 !== 0) {
    return 排名差 < 0;
  }

  const 前段百分位差 = 比較個人成績分位顯示排序(候選, 目前最佳, 顯示模式);
  if (前段百分位差 !== 0) {
    return 前段百分位差 < 0;
  }

  return 後援(候選, 目前最佳);
}
