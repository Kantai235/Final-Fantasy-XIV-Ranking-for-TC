<script>
import { computed } from "vue";
import { buildReportExternalLinks } from "../utils/reportLinks";

export default {
  name: "ReportExternalLinks",
  props: {
    record: {
      type: Object,
      required: true,
    },
    ariaLabel: {
      type: String,
      default: "外部報告工具",
    },
  },
  setup(props) {
    const links = computed(() => buildReportExternalLinks(props.record));

    return {
      links,
    };
  },
};
</script>

<template>
  <span v-if="links.length > 0" class="報告工具連結列" :aria-label="ariaLabel">
    <a
      v-for="link in links"
      :key="link.key"
      class="報告工具連結"
      :href="link.url"
      target="_blank"
      rel="noreferrer"
      :title="link.title"
    >
      {{ link.label }}
    </a>
  </span>
</template>
