import { 轉為數字 } from "./formatters";

export function 隱藏載入失敗圖片(event) {
  event.currentTarget.style.display = "none";
}

export function 排名色彩類別(排名) {
  return {
    第一名: 排名 === 1,
    第二名: 排名 === 2,
    第三名: 排名 === 3,
  };
}

export function 比例條樣式(比例) {
  const 數值 = Math.min(Math.max(轉為數字(比例) ?? 0, 0), 100);
  return {
    width: `${數值}%`,
  };
}

export function 趨勢點樣式(點) {
  return {
    left: `${點.x}%`,
    top: `${(點.y / 52) * 100}%`,
  };
}

export function 熱力格樣式(比例) {
  const 數值 = Math.min(Math.max(轉為數字(比例) ?? 0, 0), 100);
  return {
    "--熱度": `${Math.round(8 + (數值 / 100) * 50)}%`,
  };
}
