export async function 讀取Json(網址, 錯誤前綴 = "讀取資料失敗") {
  const 回應 = await fetch(網址, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!回應.ok) {
    throw new Error(`${錯誤前綴}：HTTP ${回應.status}`);
  }

  return 回應.json();
}
