<script>
import { computed, nextTick, onUnmounted, ref, watch } from "vue";
import JobIcon from "../components/JobIcon.vue";
import { injectRankingApp } from "../composables/useRankingApp";

function 台詞段落(角色, 位置, 台詞) {
  return { 類型: "dialogue", 角色, 位置, 台詞 };
}

function 讀條段落(技能名稱) {
  return { 類型: "cast", 技能名稱 };
}

function 轉場段落(技能名稱, 主題) {
  return { 類型: "transition", 技能名稱, 主題 };
}

// 劇本順序對應使用者提供的 M2S 演出流程；讀條與轉場也保留在同一條時間軸，避免對話先後錯位。
const 蜂蜂自動對話劇本 = [
  台詞段落("梅特莫", "left", ["大家的偶像！蜂蜂小甜心閃耀登場！"]),
  台詞段落("蜂蜂小甜心", "right", ["甜到心坎小蜜蜂，蜂蜂小甜心！", "來場甜蜜的表演吧！"]),
  讀條段落("甜蜜應援"),
  讀條段落("毒液雨"),
  台詞段落("蜂蜂小甜心", "right", ["向你們的女王臣服吧！"]),
  讀條段落("甜心旋風"),
  台詞段落("梅特莫", "left", ["小心她的毒刺！那可是很可怕的！"]),
  讀條段落("甜心烈風"),
  讀條段落("殺人針"),
  台詞段落("蜂蜂小甜心", "right", ["大家準備好了嗎？小甜心要開始連發了唷！"]),
  轉場段落("蜂蜂演唱會：首演", "first-show"),
  台詞段落("梅特莫", "left", ["大家久等了～！蜂蜂無敵可愛的魅力大爆發！"]),
  讀條段落("環環心連心"),
  台詞段落("梅特莫", "left", ["觀眾席上傳來盛大的歡呼聲！"]),
  台詞段落("梅特莫", "left", ["挑戰者能夠抵抗這危險的魅力嗎？"]),
  台詞段落("蜂蜂小甜心", "right", ["來吧！迷上我吧～！"]),
  讀條段落("溫柔地愛我"),
  台詞段落("梅特莫", "left", ["哎呀～！", "挑戰者已經被徹底迷住了！"]),
  讀條段落("求愛"),
  讀條段落("溫柔地愛我"),
  讀條段落("圓圓心連心"),
  台詞段落("蜂蜂小甜心", "right", ["大家～！", "還要繼續high下去喔！　B！"]),
  轉場段落("蜂蜂落幕曲", "curtain-call"),
  台詞段落("蜂蜂小甜心", "right", ["現場真的非常熱鬧呢！"]),
  讀條段落("殺人斬"),
  台詞段落("蜂蜂小甜心", "right", ["B！　B！　甜到你心裡☆"]),
  讀條段落("警示費洛蒙"),
  台詞段落("梅特莫", "left", ["欸？蜂蜂居然改變了戰術嗎！"]),
  台詞段落("蜂蜂小甜心", "right", ["表演還會繼續哦～☆"]),
  轉場段落("蜂蜂演唱會：再演", "encore"),
  讀條段落("愛之雨"),
  台詞段落("蜂蜂小甜心", "right", ["今天開始成為我的小工蜂，對吧？"]),
  讀條段落("溫柔地愛我"),
  讀條段落("甜心旋風"),
  台詞段落("蜂蜂小甜心", "right", ["謝謝大家的應援～！愛你們唷！"]),
  轉場段落("蜂蜂落幕曲", "curtain-call"),
  台詞段落("蜂蜂小甜心", "right", ["可能會死哦，抱歉囉？"]),
  讀條段落("毒液滴落"),
  台詞段落("蜂蜂小甜心", "right", ["看招，這可是超厲害的毒～～！"]),
  讀條段落("毒針"),
  台詞段落("蜂蜂小甜心", "right", ["稍微刺一下下唷☆"]),
  讀條段落("小蜂刺"),
  台詞段落("梅特莫", "left", ["雙方互不退讓，真是激烈的戰鬥！"]),
  讀條段落("殺人斬"),
  台詞段落("蜂蜂小甜心", "right", ["今天的戰鬥，真的太棒了吧！？"]),
  讀條段落("甜心烈風"),
  台詞段落("蜂蜂小甜心", "right", ["表演還會繼續哦～☆"]),
  轉場段落("蜂蜂演唱會：三演", "third-show"),
  讀條段落("愛之雨"),
  讀條段落("圓圓心連心"),
  讀條段落("環環心連心"),
  讀條段落("甜心旋風"),
  台詞段落("蜂蜂小甜心", "right", ["謝謝大家的應援～！愛你們唷！"]),
  轉場段落("蜂蜂落幕曲", "curtain-call"),
  台詞段落("蜂蜂小甜心", "right", ["B……B……宰了你們……"]),
  讀條段落("殺人斬"),
  台詞段落("蜂蜂小甜心", "right", ["我說啊，你憑什麼比老娘更出風頭啊……？"]),
  轉場段落("黑心", "black-heart"),
  讀條段落("甜蜜應援"),
  台詞段落("蜂蜂小甜心", "right", ["老娘受夠了……你差不多可以滾了吧……？"]),
  讀條段落("甜蜜應援"),
  台詞段落("蜂蜂小甜心", "right", ["給老娘……去死啦！"]),
  轉場段落("驟然心痛", "heartbreak"),
].map((段落, index) => ({ ...段落, id: `honey-script:${index}` }));

const 蜂蜂轉場停留時間 = 6200;
const 蜂蜂驟然心痛轉場停留倍率 = 3;
const 蜂蜂轉場結束站台主題 = {
  "first-show": "dark",
  "curtain-call": "light",
  encore: "dark",
  "third-show": "dark",
  "black-heart": "dark",
  heartbreak: "light",
};

function 計算蜂蜂台詞停留時間(台詞) {
  const 字數 = 台詞.join("").length;
  return Math.min(16000, Math.max(8200, 字數 * 250));
}

function 計算蜂蜂段落停留時間(段落) {
  if (段落?.類型 === "transition") {
    return 段落.主題 === "heartbreak" ? 蜂蜂轉場停留時間 * 蜂蜂驟然心痛轉場停留倍率 : 蜂蜂轉場停留時間;
  }

  if (段落?.類型 === "cast") {
    return 4600;
  }

  return 計算蜂蜂台詞停留時間(段落?.台詞 || []);
}

const 蜂蜂轉場燈光列表 = Array.from({ length: 14 }, (_, index) => ({
  id: `spotlight:${index}`,
  style: {
    "--燈光x": `${(index * 19) % 100}%`,
    "--燈光角度": `${index % 2 === 0 ? -28 - (index % 5) * 7 : 28 + (index % 5) * 7}deg`,
    "--燈光延遲": `${-(index * 0.32).toFixed(2)}s`,
    "--燈光寬度": `${132 + (index % 4) * 28}px`,
  },
}));

const 蜂蜂主題色票 = {
  opening: {
    "--粉絲榜主題光": "rgba(255, 216, 93, 0.32)",
    "--粉絲榜主題柔光": "rgba(255, 122, 182, 0.24)",
    "--粉絲榜主題深": "#7a2859",
    "--粉絲榜讀條色": "#e33482",
    "--粉絲榜讀條尾色": "#ffd95e",
    "--粉絲榜燈光色": "rgba(255, 233, 128, 0.66)",
  },
  "first-show": {
    "--粉絲榜主題光": "rgba(255, 216, 93, 0.38)",
    "--粉絲榜主題柔光": "rgba(255, 118, 185, 0.3)",
    "--粉絲榜主題深": "#9b1f62",
    "--粉絲榜讀條色": "#ff4e9c",
    "--粉絲榜讀條尾色": "#ffe36c",
    "--粉絲榜燈光色": "rgba(255, 240, 140, 0.72)",
  },
  "curtain-call": {
    "--粉絲榜主題光": "rgba(170, 221, 255, 0.28)",
    "--粉絲榜主題柔光": "rgba(255, 192, 227, 0.28)",
    "--粉絲榜主題深": "#4b2c7a",
    "--粉絲榜讀條色": "#8f69ff",
    "--粉絲榜讀條尾色": "#ff9ed2",
    "--粉絲榜燈光色": "rgba(187, 222, 255, 0.66)",
  },
  encore: {
    "--粉絲榜主題光": "rgba(139, 255, 214, 0.3)",
    "--粉絲榜主題柔光": "rgba(255, 216, 93, 0.3)",
    "--粉絲榜主題深": "#1f6f67",
    "--粉絲榜讀條色": "#27c4a2",
    "--粉絲榜讀條尾色": "#ffe36c",
    "--粉絲榜燈光色": "rgba(147, 255, 220, 0.66)",
  },
  "third-show": {
    "--粉絲榜主題光": "rgba(255, 153, 92, 0.34)",
    "--粉絲榜主題柔光": "rgba(255, 91, 155, 0.32)",
    "--粉絲榜主題深": "#8d3150",
    "--粉絲榜讀條色": "#ff6a66",
    "--粉絲榜讀條尾色": "#ffe36c",
    "--粉絲榜燈光色": "rgba(255, 180, 112, 0.68)",
  },
  "black-heart": {
    "--粉絲榜主題光": "rgba(45, 24, 62, 0.6)",
    "--粉絲榜主題柔光": "rgba(191, 26, 86, 0.34)",
    "--粉絲榜主題深": "#1d1024",
    "--粉絲榜讀條色": "#2d183e",
    "--粉絲榜讀條尾色": "#ff386f",
    "--粉絲榜燈光色": "rgba(255, 56, 111, 0.58)",
  },
  heartbreak: {
    "--粉絲榜主題光": "rgba(255, 56, 111, 0.48)",
    "--粉絲榜主題柔光": "rgba(65, 15, 36, 0.36)",
    "--粉絲榜主題深": "#481626",
    "--粉絲榜讀條色": "#481626",
    "--粉絲榜讀條尾色": "#ff386f",
    "--粉絲榜燈光色": "rgba(255, 86, 116, 0.7)",
  },
};

let 蜂蜂YouTubeApi載入Promise = null;

function 載入蜂蜂YouTubeIframeApi() {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("目前環境無法載入 YouTube 播放器。"));
  }
  if (window.YT?.Player) {
    return Promise.resolve(window.YT);
  }
  if (蜂蜂YouTubeApi載入Promise) {
    return 蜂蜂YouTubeApi載入Promise;
  }

  蜂蜂YouTubeApi載入Promise = new Promise((resolve, reject) => {
    const 既有回呼 = window.onYouTubeIframeAPIReady;
    const 載入逾時計時器 = window.setTimeout(() => {
      if (window.YT?.Player) {
        resolve(window.YT);
        return;
      }
      reject(new Error("YouTube IFrame Player API 載入逾時。"));
    }, 9000);

    window.onYouTubeIframeAPIReady = () => {
      window.clearTimeout(載入逾時計時器);
      if (typeof 既有回呼 === "function") {
        既有回呼();
      }
      resolve(window.YT);
    };

    const 既有腳本 = document.querySelector('script[src="https://www.youtube.com/iframe_api"]');
    if (既有腳本) {
      return;
    }

    const 腳本 = document.createElement("script");
    腳本.src = "https://www.youtube.com/iframe_api";
    腳本.async = true;
    腳本.onerror = () => {
      window.clearTimeout(載入逾時計時器);
      reject(new Error("YouTube IFrame Player API 載入失敗。"));
    };
    document.head.appendChild(腳本);
  }).catch((錯誤) => {
    蜂蜂YouTubeApi載入Promise = null;
    throw 錯誤;
  });

  return 蜂蜂YouTubeApi載入Promise;
}

export default {
  name: "HoneyFansPage",
  components: {
    JobIcon,
  },
  setup() {
    const rankingApp = injectRankingApp();
    rankingApp.準備蜂蜂背景音樂偏好();
    const 蜂蜂目前對話索引 = ref(0);
    const 蜂蜂進場前站台主題 = ref(null);
    const 蜂蜂背景音樂播放器容器 = ref(null);
    const 蜂蜂背景音樂播放警告 = ref("");
    const 蜂蜂背景音樂播放器已就緒 = ref(false);
    const 蜂蜂超高難度啟用 = ref(false);
    const 粉絲榜歷史紀錄彈窗粉絲 = ref(null);
    let 蜂蜂對話計時器 = null;
    let 蜂蜂背景音樂Player = null;
    let 蜂蜂背景音樂播放檢查計時器 = null;
    let 蜂蜂背景音樂播放請求序號 = 0;

    const 蜂蜂目前劇本段落 = computed(() => 蜂蜂自動對話劇本[蜂蜂目前對話索引.value] || 蜂蜂自動對話劇本[0]);
    const 蜂蜂目前對話 = computed(() => (
      蜂蜂目前劇本段落.value?.類型 === "dialogue"
        ? 蜂蜂目前劇本段落.value
        : { 角色: "", 位置: "", 台詞: [] }
    ));
    const 蜂蜂目前讀條 = computed(() => (
      蜂蜂目前劇本段落.value?.類型 === "cast" || 蜂蜂目前劇本段落.value?.類型 === "transition"
        ? 蜂蜂目前劇本段落.value
        : null
    ));
    const 蜂蜂目前讀條樣式 = computed(() => ({
      "--蜂蜂讀條時間": `${計算蜂蜂段落停留時間(蜂蜂目前劇本段落.value)}ms`,
    }));
    const 蜂蜂演出主題 = computed(() => {
      let 主題 = "opening";

      for (let index = 0; index <= 蜂蜂目前對話索引.value; index += 1) {
        const 段落 = 蜂蜂自動對話劇本[index];
        if (段落?.類型 === "transition" && 段落.主題) {
          主題 = 段落.主題;
        }
      }

      return 主題;
    });
    const 蜂蜂目前主題樣式 = computed(() => 蜂蜂主題色票[蜂蜂演出主題.value] || 蜂蜂主題色票.opening);
    const 蜂蜂背景音樂播放器參數 = computed(() => {
      const 參數 = {
        autoplay: rankingApp.蜂蜂背景音樂啟用.value ? "1" : "0",
        loop: "1",
        playlist: rankingApp.蜂蜂背景音樂影片Id,
        playsinline: "1",
        controls: "0",
        modestbranding: "1",
        rel: "0",
        iv_load_policy: "3",
      };

      if (typeof window !== "undefined") {
        參數.origin = window.location.origin;
      }

      return 參數;
    });
    const 粉絲榜歷史紀錄列表 = computed(() => (
      Array.isArray(粉絲榜歷史紀錄彈窗粉絲.value?.records)
        ? 粉絲榜歷史紀錄彈窗粉絲.value.records
        : []
    ));
    const 蜂蜂團隊榜列表 = computed(() => (
      Array.isArray(rankingApp.蜂蜂粉絲榜資料.value?.team_rankings)
        ? rankingApp.蜂蜂粉絲榜資料.value.team_rankings.slice(0, 50)
        : []
    ));
    const 蜂蜂團隊榜第一名 = computed(() => 蜂蜂團隊榜列表.value[0] || null);
    const 蜂蜂顯示概要 = computed(() => {
      if (!蜂蜂超高難度啟用.value) {
        return rankingApp.蜂蜂粉絲榜概要.value;
      }

      const summary = rankingApp.蜂蜂粉絲榜資料.value?.summary || {};
      return [
        { 標籤: "活動通關場次", 數值: rankingApp.格式化整數(summary.team_ranking_record_count ?? summary.historical_team_record_count) },
        { 標籤: "最高團隊吃心心", 數值: rankingApp.格式化整數(summary.top_team_event_count) },
        { 標籤: "活動通關事件", 數值: rankingApp.格式化整數(summary.team_ranking_event_count ?? summary.historical_kill_event_count) },
      ];
    });
    const 蜂蜂模式標籤列表 = computed(() => (
      蜂蜂超高難度啟用.value
        ? ["2026/05/30 起", "僅通關場次", "同場上傳去重", "全隊奴役總次數", "超高難度 ON"]
        : ["近 7 天榜單", "M2S 公開戰鬥紀錄", "第 4 顆愛心", "心醉魂迷：奴役", "ブリリアント☆"]
    ));

    function 粉絲榜紀錄預覽粉絲(紀錄) {
      return Array.isArray(紀錄?.fans) ? 紀錄.fans.slice(0, 2) : [];
    }

    function 粉絲榜紀錄剩餘粉絲數(紀錄) {
      return Math.max(0, (Array.isArray(紀錄?.fans) ? 紀錄.fans.length : 0) - 2);
    }

    function 團隊榜成員預覽(紀錄) {
      return Array.isArray(紀錄?.members) ? 紀錄.members.slice(0, 8) : [];
    }

    function 格式化粉絲榜短時間(iso時間) {
      const 日期 = rankingApp.格式化紀錄日期?.(iso時間) || "";
      const 時刻 = rankingApp.格式化紀錄時刻?.(iso時間) || "";
      if (!日期 || 日期 === "-") {
        return "-";
      }

      const 短日期 = 日期.replace(/^\d{4}\//, "");
      const 短時刻 = 時刻 && 時刻 !== "-" ? 時刻.slice(0, 5) : "";
      return [短日期, 短時刻].filter(Boolean).join(" ");
    }

    function 格式化粉絲榜戰鬥時間(紀錄) {
      const 是滅團 = 紀錄?.fight_status === "wipe" || 紀錄?.is_kill === false;
      const 秒數 = 紀錄?.fight_duration_seconds ?? 紀錄?.clear_time_seconds;
      return `${是滅團 ? "滅團" : "通關"} ${rankingApp.格式化通關時間(秒數)}`;
    }

    function 格式化粉絲榜連續入榜(粉絲) {
      const 週數 = Number(粉絲?.current_streak_weeks || 0);
      if (!Number.isFinite(週數) || 週數 < 2) {
        return "";
      }

      return `連續 ${rankingApp.格式化整數(週數)} 週入榜`;
    }

    function 開啟粉絲榜歷史紀錄(粉絲) {
      粉絲榜歷史紀錄彈窗粉絲.value = 粉絲;
    }

    function 關閉粉絲榜歷史紀錄() {
      粉絲榜歷史紀錄彈窗粉絲.value = null;
    }

    function 清除蜂蜂對話計時器() {
      if (typeof window === "undefined" || !蜂蜂對話計時器) {
        return;
      }

      window.clearTimeout(蜂蜂對話計時器);
      蜂蜂對話計時器 = null;
    }

    function 清除蜂蜂背景音樂播放檢查計時器() {
      if (typeof window === "undefined" || !蜂蜂背景音樂播放檢查計時器) {
        return;
      }

      window.clearTimeout(蜂蜂背景音樂播放檢查計時器);
      蜂蜂背景音樂播放檢查計時器 = null;
    }

    function 建立蜂蜂背景音樂播放錯誤訊息(錯誤碼) {
      if (錯誤碼 === 100) {
        return "YouTube 背景音樂無法播放，影片可能不存在、轉為私人影片，或目前地區無法觀看。";
      }
      if (錯誤碼 === 101 || 錯誤碼 === 150) {
        return "YouTube 背景音樂無法播放，影片目前不允許被嵌入播放。";
      }
      if (錯誤碼 === 153) {
        return "YouTube 背景音樂無法播放，瀏覽器可能封鎖 referrer 或隱私設定阻擋播放器驗證。";
      }

      return "YouTube 背景音樂沒有成功播放，可能被瀏覽器自動播放政策、廣告/隱私外掛或網路/DNS 阻擋。";
    }

    function 取得蜂蜂背景音樂播放狀態() {
      try {
        return 蜂蜂背景音樂Player?.getPlayerState?.() ?? null;
      } catch {
        return null;
      }
    }

    function 蜂蜂背景音樂是否正在播放() {
      const 播放狀態 = 取得蜂蜂背景音樂播放狀態();
      return typeof window !== "undefined" && 播放狀態 === window.YT?.PlayerState?.PLAYING;
    }

    function 排程蜂蜂背景音樂播放檢查() {
      清除蜂蜂背景音樂播放檢查計時器();
      if (typeof window === "undefined" || !rankingApp.蜂蜂背景音樂啟用.value) {
        return;
      }

      const 目前請求序號 = ++蜂蜂背景音樂播放請求序號;
      蜂蜂背景音樂播放檢查計時器 = window.setTimeout(() => {
        const 仍是目前請求 = 目前請求序號 === 蜂蜂背景音樂播放請求序號;
        if (!仍是目前請求 || !rankingApp.蜂蜂背景音樂啟用.value || 蜂蜂背景音樂是否正在播放()) {
          蜂蜂背景音樂播放檢查計時器 = null;
          return;
        }

        蜂蜂背景音樂播放警告.value = 建立蜂蜂背景音樂播放錯誤訊息();
        蜂蜂背景音樂播放檢查計時器 = null;
      }, 7600);
    }

    function 送出蜂蜂背景音樂播放() {
      if (!rankingApp.蜂蜂背景音樂啟用.value || !蜂蜂背景音樂Player) {
        return;
      }

      try {
        蜂蜂背景音樂Player.setVolume?.(62);
        蜂蜂背景音樂Player.playVideo?.();
      } catch {
        蜂蜂背景音樂播放警告.value = 建立蜂蜂背景音樂播放錯誤訊息();
      }
      排程蜂蜂背景音樂播放檢查();
    }

    function 銷毀蜂蜂背景音樂播放器() {
      蜂蜂背景音樂播放器已就緒.value = false;
      try {
        蜂蜂背景音樂Player?.stopVideo?.();
        蜂蜂背景音樂Player?.destroy?.();
      } catch {
        // YouTube iframe 是播放器 API 放進容器的子節點；銷毀失敗時只需要清掉容器與本地參照。
      }
      蜂蜂背景音樂Player = null;
      蜂蜂背景音樂播放器容器.value?.replaceChildren();
    }

    function 處理蜂蜂背景音樂播放器就緒(event) {
      蜂蜂背景音樂Player = event.target;
      蜂蜂背景音樂播放器已就緒.value = true;
      送出蜂蜂背景音樂播放();
    }

    function 處理蜂蜂背景音樂播放狀態(event) {
      if (event.data === window.YT?.PlayerState?.PLAYING) {
        蜂蜂背景音樂播放警告.value = "";
        清除蜂蜂背景音樂播放檢查計時器();
      }
      if (event.data === window.YT?.PlayerState?.ENDED && rankingApp.蜂蜂背景音樂啟用.value) {
        送出蜂蜂背景音樂播放();
      }
    }

    function 處理蜂蜂背景音樂播放器錯誤(event) {
      蜂蜂背景音樂播放警告.value = 建立蜂蜂背景音樂播放錯誤訊息(event.data);
      清除蜂蜂背景音樂播放檢查計時器();
    }

    async function 建立蜂蜂背景音樂播放器() {
      try {
        const YouTube = await 載入蜂蜂YouTubeIframeApi();
        const 容器 = 蜂蜂背景音樂播放器容器.value;
        if (!rankingApp.蜂蜂背景音樂啟用.value || !容器 || 蜂蜂背景音樂Player) {
          return;
        }

        容器.replaceChildren();
        const 播放器節點 = document.createElement("div");
        播放器節點.id = `honey-youtube-player-${Date.now()}`;
        容器.appendChild(播放器節點);

        蜂蜂背景音樂Player = new YouTube.Player(播放器節點, {
          videoId: rankingApp.蜂蜂背景音樂影片Id,
          playerVars: 蜂蜂背景音樂播放器參數.value,
          events: {
            onReady: 處理蜂蜂背景音樂播放器就緒,
            onStateChange: 處理蜂蜂背景音樂播放狀態,
            onError: 處理蜂蜂背景音樂播放器錯誤,
          },
        });
      } catch (錯誤) {
        蜂蜂背景音樂播放警告.value = 錯誤 instanceof Error
          ? `${錯誤.message} 可能被廣告/隱私外掛或網路/DNS 阻擋。`
          : 建立蜂蜂背景音樂播放錯誤訊息();
      }
    }

    async function 嘗試播放蜂蜂背景音樂({ 重設偵測 = false } = {}) {
      if (typeof window === "undefined" || !rankingApp.蜂蜂背景音樂啟用.value) {
        return;
      }

      if (重設偵測) {
        蜂蜂背景音樂播放警告.value = "";
      }

      await nextTick();
      window.requestAnimationFrame(() => {
        if (!蜂蜂背景音樂播放器容器.value) {
          return;
        }
        if (蜂蜂背景音樂Player && 蜂蜂背景音樂播放器已就緒.value) {
          送出蜂蜂背景音樂播放();
          return;
        }

        建立蜂蜂背景音樂播放器();
        排程蜂蜂背景音樂播放檢查();
      });
    }

    function 暫停蜂蜂背景音樂() {
      清除蜂蜂背景音樂播放檢查計時器();
      蜂蜂背景音樂播放警告.value = "";
      銷毀蜂蜂背景音樂播放器();
    }

    function 關閉蜂蜂背景音樂播放警告() {
      清除蜂蜂背景音樂播放檢查計時器();
      蜂蜂背景音樂播放警告.value = "";
    }

    function 設定蜂蜂背景音樂並播放(啟用) {
      rankingApp.設定蜂蜂背景音樂偏好(啟用);
      if (啟用) {
        嘗試播放蜂蜂背景音樂({ 重設偵測: true });
      }
    }

    function 互動後補播蜂蜂背景音樂() {
      if (rankingApp.蜂蜂背景音樂啟用.value) {
        嘗試播放蜂蜂背景音樂();
      }
    }

    function 排程下一句蜂蜂對話() {
      if (typeof window === "undefined") {
        return;
      }

      const 目前段落 = 蜂蜂目前劇本段落.value;
      清除蜂蜂對話計時器();
      蜂蜂對話計時器 = window.setTimeout(() => {
        蜂蜂目前對話索引.value = (蜂蜂目前對話索引.value + 1) % 蜂蜂自動對話劇本.length;
        排程下一句蜂蜂對話();
        處理蜂蜂段落結束(目前段落);
      }, 計算蜂蜂段落停留時間(蜂蜂目前劇本段落.value));
    }

    function 套用蜂蜂站台主題(站台主題) {
      if (!站台主題) {
        return;
      }

      if (!蜂蜂進場前站台主題.value) {
        蜂蜂進場前站台主題.value = rankingApp.主題模式.value;
      }

      if (rankingApp.主題模式.value !== 站台主題) {
        rankingApp.套用暫時主題(站台主題);
      }
    }

    function 套用蜂蜂預設站台主題() {
      套用蜂蜂站台主題("light");
    }

    function 還原蜂蜂進場前站台主題() {
      const 進場前主題 = 蜂蜂進場前站台主題.value;
      if (!進場前主題) {
        return;
      }

      if (rankingApp.主題模式.value !== 進場前主題) {
        rankingApp.套用暫時主題(進場前主題);
      }
      蜂蜂進場前站台主題.value = null;
    }

    function 處理蜂蜂段落結束(段落) {
      if (段落?.類型 !== "transition") {
        return;
      }

      const 轉場結束主題 = 蜂蜂轉場結束站台主題[段落.主題];
      if (!轉場結束主題) {
        return;
      }

      nextTick(() => {
        window.requestAnimationFrame(() => {
          window.requestAnimationFrame(() => {
            // 每段轉場都有固定的演出亮暗結果；不能只反轉目前主題，
            // 因為最後一段回到開場時會先觸發開場亮色 watcher。
            套用蜂蜂站台主題(轉場結束主題);
          });
        });
      });
    }

    watch(
      () => rankingApp.蜂蜂粉絲榜資料.value,
      (粉絲榜資料) => {
        清除蜂蜂對話計時器();
        if (!粉絲榜資料) {
          return;
        }

        蜂蜂目前對話索引.value = 0;
        排程下一句蜂蜂對話();
      },
      { immediate: true },
    );

    watch(蜂蜂目前劇本段落, () => {
      if (蜂蜂演出主題.value === "opening") {
        套用蜂蜂預設站台主題();
      }
    }, { immediate: true });

    watch(
      () => rankingApp.蜂蜂背景音樂啟用.value,
      (啟用) => {
        if (啟用) {
          嘗試播放蜂蜂背景音樂({ 重設偵測: true });
          return;
        }

        暫停蜂蜂背景音樂();
      },
      { immediate: true },
    );

    if (typeof window !== "undefined") {
      window.addEventListener("pointerdown", 互動後補播蜂蜂背景音樂, { passive: true });
      window.addEventListener("keydown", 互動後補播蜂蜂背景音樂);
    }

    onUnmounted(() => {
      清除蜂蜂對話計時器();
      清除蜂蜂背景音樂播放檢查計時器();
      if (typeof window !== "undefined") {
        window.removeEventListener("pointerdown", 互動後補播蜂蜂背景音樂);
        window.removeEventListener("keydown", 互動後補播蜂蜂背景音樂);
      }
      暫停蜂蜂背景音樂();
      還原蜂蜂進場前站台主題();
    });

    return {
      ...rankingApp,
      蜂蜂目前對話索引,
      蜂蜂目前劇本段落,
      蜂蜂目前對話,
      蜂蜂目前讀條,
      蜂蜂目前讀條樣式,
      蜂蜂演出主題,
      蜂蜂目前主題樣式,
      蜂蜂背景音樂播放器容器,
      蜂蜂背景音樂播放警告,
      嘗試播放蜂蜂背景音樂,
      關閉蜂蜂背景音樂播放警告,
      設定蜂蜂背景音樂並播放,
      蜂蜂轉場燈光列表,
      粉絲榜歷史紀錄彈窗粉絲,
      粉絲榜歷史紀錄列表,
      蜂蜂超高難度啟用,
      蜂蜂團隊榜列表,
      蜂蜂團隊榜第一名,
      蜂蜂顯示概要,
      蜂蜂模式標籤列表,
      粉絲榜紀錄預覽粉絲,
      粉絲榜紀錄剩餘粉絲數,
      團隊榜成員預覽,
      格式化粉絲榜短時間,
      格式化粉絲榜戰鬥時間,
      格式化粉絲榜連續入榜,
      開啟粉絲榜歷史紀錄,
      關閉粉絲榜歷史紀錄,
    };
  },
};
</script>

<template>
  <section class="粉絲榜區" :data-honey-theme="蜂蜂演出主題" :style="蜂蜂目前主題樣式" aria-live="polite">
    <Teleport to="body">
      <div
        v-if="顯示蜂蜂背景音樂詢問"
        class="蜂蜂音樂詢問遮罩"
        role="dialog"
        aria-modal="true"
        aria-labelledby="蜂蜂音樂詢問標題"
        aria-describedby="蜂蜂音樂詢問說明"
        tabindex="-1"
        @click.self="設定蜂蜂背景音樂並播放(false)"
        @keydown.escape="設定蜂蜂背景音樂並播放(false)"
      >
        <section class="蜂蜂音樂詢問視窗">
          <p class="蜂蜂音樂詢問副標">Honey B. Lovely Fan Stage</p>
          <h2 id="蜂蜂音樂詢問標題">開啟背景音樂？</h2>
          <p id="蜂蜂音樂詢問說明">推薦開啟背景音樂，可以享受 Honey B. Lovely 粉絲榜的最佳演出體驗。</p>
          <div class="蜂蜂音樂詢問行動列">
            <button type="button" @click="設定蜂蜂背景音樂並播放(true)">開啟背景音樂</button>
            <button class="蜂蜂音樂詢問次要" type="button" @click="設定蜂蜂背景音樂並播放(false)">暫不開啟</button>
          </div>
        </section>
      </div>
      <div
        v-if="蜂蜂背景音樂啟用"
        ref="蜂蜂背景音樂播放器容器"
        class="蜂蜂背景音樂播放器"
        :data-video-id="蜂蜂背景音樂影片Id"
        aria-hidden="true"
      ></div>
      <div v-if="蜂蜂背景音樂播放警告" class="蜂蜂音樂播放警告" role="status" aria-live="polite">
        <strong>背景音樂未播放</strong>
        <span>{{ 蜂蜂背景音樂播放警告 }}</span>
        <button type="button" @click="關閉蜂蜂背景音樂播放警告">關閉</button>
      </div>
      <div
        v-if="粉絲榜歷史紀錄彈窗粉絲"
        class="粉絲榜歷史彈窗遮罩"
        role="dialog"
        aria-modal="true"
        aria-labelledby="粉絲榜歷史彈窗標題"
        tabindex="-1"
        @click.self="關閉粉絲榜歷史紀錄"
        @keydown.escape="關閉粉絲榜歷史紀錄"
      >
        <section class="粉絲榜歷史彈窗">
          <header class="粉絲榜歷史彈窗標題">
            <div>
              <span>Honey B. Lovely Fan Log</span>
              <h2 id="粉絲榜歷史彈窗標題">{{ 粉絲榜歷史紀錄彈窗粉絲.character_name }}</h2>
              <p>{{ 粉絲榜歷史紀錄彈窗粉絲.server }}・{{ 顯示職業名稱(粉絲榜歷史紀錄彈窗粉絲.main_job) || 粉絲榜歷史紀錄彈窗粉絲.main_job || "-" }}</p>
            </div>
            <button type="button" @click="關閉粉絲榜歷史紀錄">關閉</button>
          </header>
          <div class="粉絲榜歷史概要">
            <span>本期吃心心 <strong>{{ 格式化整數(粉絲榜歷史紀錄彈窗粉絲.total_event_count) }}</strong></span>
            <span>本期戰鬥次數 <strong>{{ 格式化整數(粉絲榜歷史紀錄彈窗粉絲.fight_count) }}</strong></span>
            <span>歷史吃心心 <strong>{{ 格式化整數(粉絲榜歷史紀錄彈窗粉絲.historical_total_event_count ?? 粉絲榜歷史紀錄彈窗粉絲.total_event_count) }}</strong></span>
            <span v-if="格式化粉絲榜連續入榜(粉絲榜歷史紀錄彈窗粉絲)" class="粉絲榜連續徽章">{{ 格式化粉絲榜連續入榜(粉絲榜歷史紀錄彈窗粉絲) }}</span>
          </div>
          <div v-if="粉絲榜歷史紀錄列表.length === 0" class="狀態列">目前沒有近 7 天紀錄</div>
          <div v-else class="粉絲榜歷史列表">
            <article v-for="紀錄 in 粉絲榜歷史紀錄列表" :key="紀錄.id" class="粉絲榜歷史項">
              <div>
                <strong>{{ 格式化紀錄時間(紀錄.fight_completed_at_iso) }}</strong>
                <span>
                  {{ 顯示職業名稱(紀錄.job) || 紀錄.job || "-" }}・{{ 格式化整數(紀錄.event_count) }} 次・{{ 格式化粉絲榜戰鬥時間(紀錄) }}
                </span>
              </div>
              <span class="粉絲榜歷史報告代碼">{{ 紀錄.report_code || "-" }}</span>
              <a v-if="紀錄.report_url" :href="紀錄.report_url" target="_blank" rel="noreferrer">FFLogs</a>
            </article>
          </div>
        </section>
      </div>
    </Teleport>

    <div v-if="蜂蜂粉絲榜讀取中" class="狀態列">讀取 Honey B. Lovely 粉絲榜中</div>
    <div v-else-if="蜂蜂粉絲榜錯誤訊息" class="狀態列 錯誤">{{ 蜂蜂粉絲榜錯誤訊息 }}</div>
    <div v-else-if="!蜂蜂粉絲榜資料" class="狀態列">正在準備 Honey B. Lovely 粉絲榜資料</div>

    <template v-else>
      <Teleport to="body">
        <div
          class="粉絲榜演出主題光暈"
          :data-honey-theme="蜂蜂演出主題"
          :style="蜂蜂目前主題樣式"
          aria-hidden="true"
        ></div>
        <div
          v-if="蜂蜂目前劇本段落.類型 === 'transition'"
          :key="`curtain:${蜂蜂目前對話索引}`"
          class="粉絲榜轉場遮幕"
          :data-honey-theme="蜂蜂演出主題"
          :style="[蜂蜂目前主題樣式, 蜂蜂目前讀條樣式]"
          aria-hidden="true"
        ></div>
        <div
          v-if="蜂蜂目前劇本段落.類型 === 'transition'"
          :key="`lights:${蜂蜂目前對話索引}`"
          class="粉絲榜轉場燈光層"
          :data-honey-theme="蜂蜂演出主題"
          :style="蜂蜂目前主題樣式"
          aria-hidden="true"
        >
          <span v-for="燈光 in 蜂蜂轉場燈光列表" :key="燈光.id" :style="燈光.style"></span>
        </div>
        <section
          v-if="蜂蜂目前讀條"
          :key="`cast:${蜂蜂目前對話索引}`"
          class="粉絲榜讀條舞台"
          :class="{ 粉絲榜轉場讀條: 蜂蜂目前讀條.類型 === 'transition' }"
          :data-honey-theme="蜂蜂演出主題"
          :style="[蜂蜂目前主題樣式, 蜂蜂目前讀條樣式]"
          aria-live="polite"
        >
          <strong>{{ 蜂蜂目前讀條.技能名稱 }}</strong>
          <span class="粉絲榜讀條軌道" aria-hidden="true">
            <span></span>
          </span>
        </section>
        <section class="粉絲榜對話劇場" aria-label="Honey B. Lovely 戰鬥對話" aria-live="polite">
          <article class="粉絲榜對話欄 粉絲榜對話欄左" :class="{ 目前說話中: 蜂蜂目前對話.位置 === 'left' }">
            <span class="粉絲榜對話名牌">梅特莫</span>
            <div class="粉絲榜對話氣泡">
              <template v-if="蜂蜂目前對話.角色 === '梅特莫'">
                <p v-for="台詞 in 蜂蜂目前對話.台詞" :key="台詞">{{ 台詞 }}</p>
                <span class="粉絲榜對話游標" aria-hidden="true"></span>
              </template>
              <p v-else class="粉絲榜對話待機" aria-hidden="true">……</p>
            </div>
          </article>

          <article class="粉絲榜對話欄 粉絲榜對話欄右" :class="{ 目前說話中: 蜂蜂目前對話.位置 === 'right' }">
            <span class="粉絲榜對話名牌">蜂蜂小甜心</span>
            <div class="粉絲榜對話氣泡">
              <template v-if="蜂蜂目前對話.角色 === '蜂蜂小甜心'">
                <p v-for="台詞 in 蜂蜂目前對話.台詞" :key="台詞">{{ 台詞 }}</p>
                <span class="粉絲榜對話游標" aria-hidden="true"></span>
              </template>
              <p v-else class="粉絲榜對話待機" aria-hidden="true">……</p>
            </div>
          </article>
        </section>
      </Teleport>

      <section class="粉絲榜舞台" aria-label="Honey B. Lovely 粉絲榜舞台">
        <div class="粉絲榜舞台內容">
          <span class="粉絲榜眉標">Honey B. Lovely Fan Stage</span>
          <h2>{{ 蜂蜂超高難度啟用 ? "Honey B. Lovely 超高難度團隊榜" : "さあ、「ハニー・B・ラブリー」の登場です！" }}</h2>
          <p>
            {{ 蜂蜂超高難度啟用
              ? "只計 2026/05/30 00:00:00（台灣時間）之後的通關場次，依全隊進入「心醉魂迷：奴役」總次數排序。同一場多份 FFLogs 上傳會合併計算。"
              : "近一週吃到「心醉魂迷：奴役」，才算進本期粉絲名冊。本榜單屬於娛樂性質，不會列入正式排行榜。"
            }}
          </p>
          <form class="粉絲榜模式切換表單" aria-label="Honey B. Lovely 粉絲榜模式切換" @submit.prevent>
            <label class="粉絲榜超高難度開關">
              <input
                v-model="蜂蜂超高難度啟用"
                type="checkbox"
                role="switch"
                :aria-checked="蜂蜂超高難度啟用 ? 'true' : 'false'"
                :aria-label="蜂蜂超高難度啟用 ? '關閉超高難度團隊榜' : '開啟超高難度團隊榜'"
              />
              <span class="粉絲榜超高難度開關軌道" aria-hidden="true">
                <span class="粉絲榜超高難度滑塊"></span>
                <span class="粉絲榜超高難度選項 粉絲榜超高難度一般">一般</span>
                <span class="粉絲榜超高難度選項 粉絲榜超高難度挑戰">超高難度</span>
              </span>
              <strong class="粉絲榜超高難度狀態">{{ 蜂蜂超高難度啟用 ? "ON" : "OFF" }}</strong>
            </label>
          </form>
          <div class="粉絲榜舞台數據列" aria-label="Honey B. Lovely 粉絲榜概要">
            <div v-for="項目 in 蜂蜂顯示概要" :key="項目.標籤" class="粉絲榜舞台數字卡">
              <span>{{ 項目.標籤 }}</span>
              <strong>{{ 項目.數值 }}</strong>
            </div>
          </div>
          <div class="粉絲榜應援標籤列" aria-label="粉絲榜資料範圍">
            <span v-for="標籤 in 蜂蜂模式標籤列表" :key="標籤">{{ 標籤 }}</span>
          </div>
        </div>
        <aside v-if="蜂蜂超高難度啟用 && 蜂蜂團隊榜第一名" class="粉絲榜頭號票券 粉絲榜團隊票券" aria-label="超高難度冠軍隊伍">
          <span>超高難度冠軍隊伍</span>
          <strong>{{ 格式化整數(蜂蜂團隊榜第一名.total_event_count) }} 次</strong>
          <small>{{ 格式化粉絲榜戰鬥時間(蜂蜂團隊榜第一名) }}・{{ 格式化整數(蜂蜂團隊榜第一名.unique_fan_count) }} 人中招</small>
          <small>{{ 格式化紀錄時間(蜂蜂團隊榜第一名.fight_completed_at_iso) }}</small>
          <div v-if="團隊榜成員預覽(蜂蜂團隊榜第一名).length" class="粉絲榜票券隊員列 粉絲榜團隊成員列" aria-label="超高難度冠軍隊伍成員">
            <button
              v-for="成員 in 團隊榜成員預覽(蜂蜂團隊榜第一名)"
              :key="`champion:${成員.character_name}@${成員.server}:${成員.job}`"
              class="粉絲榜票券隊員 粉絲榜團隊成員"
              type="button"
              :title="`${成員.character_name}@${成員.server}｜${顯示職業名稱(成員.job) || 成員.job || '-'}｜${格式化整數(成員.event_count)} 次`"
              :aria-label="`${成員.character_name}@${成員.server}，${顯示職業名稱(成員.job) || 成員.job || '-'}，${格式化整數(成員.event_count)} 次`"
              @click="載入使用者成績(成員.character_name, 成員.server)"
            >
              <JobIcon class="職業圖示" :code="成員.job" />
              <span>{{ 成員.character_name }}</span>
              <small>{{ 成員.server }}</small>
            </button>
          </div>
          <a v-if="蜂蜂團隊榜第一名.report_url" class="粉絲榜頭號紀錄按鈕" :href="蜂蜂團隊榜第一名.report_url" target="_blank" rel="noreferrer">
            查看 FFLogs
          </a>
        </aside>
        <aside v-else-if="頭號粉絲列表.length" class="粉絲榜頭號票券" aria-label="目前頭號粉絲">
          <span>本期頭號粉絲</span>
          <button class="粉絲榜頭號名字按鈕" type="button" @click="載入使用者成績(頭號粉絲列表[0].character_name, 頭號粉絲列表[0].server)">
            {{ 頭號粉絲列表[0].character_name }}
          </button>
          <small>{{ 頭號粉絲列表[0].server }}・{{ 顯示職業名稱(頭號粉絲列表[0].main_job) || 頭號粉絲列表[0].main_job || "-" }}</small>
          <strong>{{ 格式化整數(頭號粉絲列表[0].total_event_count) }} 次</strong>
          <span v-if="格式化粉絲榜連續入榜(頭號粉絲列表[0])" class="粉絲榜連續徽章">{{ 格式化粉絲榜連續入榜(頭號粉絲列表[0]) }}</span>
          <button class="粉絲榜頭號紀錄按鈕" type="button" @click="開啟粉絲榜歷史紀錄(頭號粉絲列表[0])">
            近 7 天紀錄
          </button>
        </aside>
      </section>

      <section class="統計面板 統計面板寬" aria-label="頭號粉絲">
        <header class="統計面板標題">
          <h2>{{ 蜂蜂超高難度啟用 ? "超高難度團隊榜" : "頭號粉絲" }}</h2>
          <span>{{ 蜂蜂超高難度啟用 ? "依 2026/05/30 00:00:00 後通關場次的全隊奴役總次數排序" : "依近一週進入「心醉魂迷：奴役」次數排序" }}</span>
        </header>
        <template v-if="蜂蜂超高難度啟用">
          <div v-if="蜂蜂團隊榜列表.length === 0" class="狀態列">目前尚未收錄通關團隊紀錄</div>
          <div v-else class="統計表格外框">
            <table class="統計表格 粉絲榜表格 粉絲榜團隊表格">
              <thead>
                <tr>
                  <th scope="col" class="數字">排名</th>
                  <th scope="col">團隊中招名單</th>
                  <th scope="col" class="數字">總心心數</th>
                  <th scope="col" class="數字">粉絲數量</th>
                  <th scope="col" class="粉絲榜合併時間表頭">
                    <span>紀錄時間</span>
                    <small>通關時間</small>
                  </th>
                  <th scope="col">報告</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(紀錄, index) in 蜂蜂團隊榜列表" :key="紀錄.id" :class="{ 粉絲榜冠軍列: index === 0, 粉絲榜上位列: index < 3 }">
                  <td class="數字 粉絲榜排名格">
                    <span class="粉絲榜排名徽章">
                      <span class="粉絲榜排名符號" aria-hidden="true">#</span>
                      <span class="粉絲榜排名數字">{{ 格式化整數(紀錄.rank || index + 1) }}</span>
                    </span>
                  </td>
                  <td>
                    <span class="粉絲榜團隊成員列">
                      <button
                        v-for="成員 in 團隊榜成員預覽(紀錄)"
                        :key="`${紀錄.id}:${成員.character_name}@${成員.server}:${成員.job}`"
                        class="粉絲榜團隊成員"
                        type="button"
                        :title="`${成員.character_name}@${成員.server}｜${顯示職業名稱(成員.job) || 成員.job || '-'}｜${格式化整數(成員.event_count)} 次`"
                        :aria-label="`${成員.character_name}@${成員.server}，${顯示職業名稱(成員.job) || 成員.job || '-'}，${格式化整數(成員.event_count)} 次`"
                        @click="載入使用者成績(成員.character_name, 成員.server)"
                      >
                        <JobIcon class="職業圖示" :code="成員.job" />
                        <span>{{ 成員.character_name }}</span>
                        <small>{{ 成員.server }}</small>
                      </button>
                    </span>
                  </td>
                  <td class="數字 粉絲榜吃心心數格">
                    <span class="粉絲榜數值標籤">總心心數</span>
                    <span class="粉絲榜數值文字">
                      <strong>{{ 格式化整數(紀錄.total_event_count) }}</strong>
                      <span class="粉絲榜數值單位">次</span>
                    </span>
                  </td>
                  <td class="數字 粉絲榜戰鬥次數格">
                    <span class="粉絲榜數值標籤">粉絲數量</span>
                    <span class="粉絲榜數值文字">
                      <strong>{{ 格式化整數(紀錄.unique_fan_count) }}</strong>
                      <span class="粉絲榜數值單位">人</span>
                    </span>
                  </td>
                  <td class="粉絲榜合併時間格">
                    <span class="粉絲榜合併時間">
                      <span>{{ 格式化紀錄日期(紀錄.fight_completed_at_iso) }}</span>
                      <span>{{ 格式化紀錄時刻(紀錄.fight_completed_at_iso) }}</span>
                      <small>{{ 格式化通關時間(紀錄.clear_time_seconds) }}</small>
                    </span>
                  </td>
                  <td>
                    <a v-if="紀錄.report_url" :href="紀錄.report_url" target="_blank" rel="noreferrer">FFLogs</a>
                    <span v-else>-</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
        <template v-else>
          <div v-if="頭號粉絲列表.length === 0" class="狀態列">目前尚未收錄粉絲紀錄</div>
          <div v-else class="統計表格外框">
            <table class="統計表格 粉絲榜表格">
              <thead>
                <tr>
                  <th scope="col" class="數字">排名</th>
                  <th scope="col">粉絲</th>
                  <th scope="col">主要職業</th>
                  <th scope="col" class="數字">吃心心數</th>
                  <th scope="col" class="數字">戰鬥次數</th>
                  <th scope="col">最近紀錄</th>
                  <th scope="col">報告</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(粉絲, index) in 頭號粉絲列表" :key="粉絲.id" :class="{ 粉絲榜冠軍列: index === 0, 粉絲榜上位列: index < 3 }">
                  <td class="數字 粉絲榜排名格">
                    <span class="粉絲榜排名徽章">
                      <span class="粉絲榜排名符號" aria-hidden="true">#</span>
                      <span class="粉絲榜排名數字">{{ 格式化整數(index + 1) }}</span>
                    </span>
                  </td>
                  <td>
                    <span class="粉絲榜玩家身分">
                      <button class="文字連結 粉絲榜玩家名稱" type="button" @click="載入使用者成績(粉絲.character_name, 粉絲.server)">
                        {{ 粉絲.character_name }}
                      </button>
                      <span class="粉絲榜玩家分隔" aria-hidden="true">@</span>
                      <small class="表格補充文字 粉絲榜玩家伺服器">{{ 粉絲.server }}</small>
                    </span>
                    <span v-if="格式化粉絲榜連續入榜(粉絲)" class="粉絲榜連續徽章">{{ 格式化粉絲榜連續入榜(粉絲) }}</span>
                  </td>
                  <td>
                    <span v-if="粉絲.main_job" class="職業標籤 近期動態職業標籤" :class="職業色彩類別(職業代碼色彩(粉絲.main_job))">
                      <img
                        v-if="職業Icon路徑(粉絲.main_job)"
                        class="職業圖示 職業標籤圖示"
                        :src="職業Icon路徑(粉絲.main_job)"
                        alt=""
                        loading="lazy"
                        @error="隱藏載入失敗圖片"
                      />
                      <span>{{ 顯示職業名稱(粉絲.main_job) }}</span>
                    </span>
                    <span v-else>-</span>
                  </td>
                  <td class="數字 粉絲榜吃心心數格">
                    <span class="粉絲榜數值標籤">吃心心數</span>
                    <span class="粉絲榜數值文字">
                      <strong>{{ 格式化整數(粉絲.total_event_count) }}</strong>
                      <span class="粉絲榜數值單位">次</span>
                    </span>
                  </td>
                  <td class="數字 粉絲榜戰鬥次數格">
                    <span class="粉絲榜數值標籤">戰鬥次數</span>
                    <span class="粉絲榜數值文字">
                      <strong>{{ 格式化整數(粉絲.fight_count) }}</strong>
                      <span class="粉絲榜數值單位">場</span>
                    </span>
                  </td>
                  <td>
                    <span class="緊湊紀錄時間">
                      <span>{{ 格式化紀錄日期(粉絲.latest_recorded_at_iso) }}</span>
                      <span>{{ 格式化紀錄時刻(粉絲.latest_recorded_at_iso) }}</span>
                    </span>
                  </td>
                  <td>
                    <button
                      v-if="粉絲.records?.length"
                      class="粉絲榜報告按鈕"
                      type="button"
                      @click="開啟粉絲榜歷史紀錄(粉絲)"
                    >
                      {{ 格式化整數(粉絲.records.length) }} 份紀錄
                    </button>
                    <a v-else-if="粉絲.latest_report_url" :href="粉絲.latest_report_url" target="_blank" rel="noreferrer">FFLogs</a>
                    <span v-else>-</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </section>

      <section v-if="!蜂蜂超高難度啟用" class="近期洞察版面 粉絲榜雙欄" aria-label="Honey B. Lovely 粉絲榜近期資料">
        <article class="統計面板">
          <header class="統計面板標題">
            <h2>最新收錄紀錄</h2>
            <span>依戰鬥結束時間排序</span>
          </header>
          <div v-if="最新粉絲紀錄列表.length === 0" class="狀態列">目前沒有最新紀錄</div>
          <div v-else class="粉絲榜紀錄列表">
            <div v-for="紀錄 in 最新粉絲紀錄列表" :key="紀錄.id" class="粉絲榜紀錄項">
              <div class="粉絲榜紀錄主資訊">
                <strong>{{ 格式化粉絲榜短時間(紀錄.fight_completed_at_iso) }}</strong>
                <span>{{ 格式化粉絲榜戰鬥時間(紀錄) }}・{{ 格式化整數(紀錄.fan_event_count) }} 位粉絲</span>
              </div>
              <div class="粉絲榜紀錄粉絲摘要">
                <button
                  v-for="粉絲 in 粉絲榜紀錄預覽粉絲(紀錄)"
                  :key="`${紀錄.id}:${粉絲.character_name}@${粉絲.server}:${粉絲.event_at_iso}`"
                  class="粉絲榜迷你粉絲"
                  :title="`${粉絲.character_name}（${粉絲.server}）`"
                  type="button"
                  @click="載入使用者成績(粉絲.character_name, 粉絲.server)"
                >
                  <span class="粉絲榜迷你粉絲文字">
                    <span class="粉絲榜迷你粉絲名稱">{{ 粉絲.character_name }}</span>
                    <span class="粉絲榜迷你粉絲副資訊">
                      <small>{{ 粉絲.server }}</small>
                      <small v-if="粉絲.job">{{ 顯示職業名稱(粉絲.job) || 粉絲.job }}</small>
                    </span>
                  </span>
                </button>
                <span v-if="粉絲榜紀錄剩餘粉絲數(紀錄) > 0" class="粉絲榜紀錄更多">
                  +{{ 格式化整數(粉絲榜紀錄剩餘粉絲數(紀錄)) }}
                </span>
              </div>
              <a v-if="紀錄.report_url" :href="紀錄.report_url" target="_blank" rel="noreferrer">查看 FFLogs</a>
            </div>
          </div>
        </article>

        <article class="統計面板">
          <header class="統計面板標題">
            <h2>最新加入粉絲</h2>
            <span>依首次收錄時間排序</span>
          </header>
          <div v-if="最新加入粉絲列表.length === 0" class="狀態列">目前沒有新粉絲</div>
          <div v-else class="近期新角色列表">
            <button
              v-for="粉絲 in 最新加入粉絲列表"
              :key="粉絲.id"
              class="近期新角色項"
              :data-fan-count="`${格式化整數(粉絲.total_event_count)} 次`"
              type="button"
              @click="載入使用者成績(粉絲.character_name, 粉絲.server)"
            >
              <strong>{{ 粉絲.character_name }}</strong>
              <span class="粉絲榜新粉絲資訊">
                <span>{{ 粉絲.server }}・{{ 顯示職業名稱(粉絲.main_job) || 粉絲.main_job || "-" }}</span>
                <time :datetime="粉絲.latest_recorded_at_iso">
                  {{ 格式化粉絲榜短時間(粉絲.latest_recorded_at_iso) }}
                </time>
              </span>
            </button>
          </div>
        </article>
      </section>
    </template>
  </section>
</template>
