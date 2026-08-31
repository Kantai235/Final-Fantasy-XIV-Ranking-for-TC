<script>
import { h } from "vue";

export default {
  name: "AchievementDescription",
  props: {
    as: {
      type: String,
      default: "span",
      validator: (標籤) => ["span", "p"].includes(標籤),
    },
    text: {
      type: String,
      default: "",
    },
    segments: {
      type: Array,
      default: () => [],
    },
  },
  setup(props) {
    return () => {
      const 片段列表 = Array.isArray(props.segments) ? props.segments : [];
      const 有效片段 = 片段列表.filter((片段) => (
        片段
        && typeof 片段 === "object"
        && typeof 片段.文字 === "string"
        && 片段.文字.length > 0
      ));
      const 內容 = 有效片段.length > 0
        ? 有效片段.map((片段, 索引) => (
          片段.刪除線
            ? h("s", { key: `${索引}-${片段.文字}` }, 片段.文字)
            : 片段.文字
        ))
        : props.text;

      return h(props.as, { class: "成就格式化說明" }, 內容);
    };
  },
};
</script>
