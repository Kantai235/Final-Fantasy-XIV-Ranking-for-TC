<script>
export default {
  name: "AnnouncementMarkdown",
  props: {
    blocks: {
      type: Array,
      default: () => [],
    },
  },
  methods: {
    headingTag(block) {
      return block?.level <= 2 ? "h3" : "h4";
    },
    listTag(block) {
      return block?.ordered ? "ol" : "ul";
    },
  },
};
</script>

<template>
  <div class="公告Markdown">
    <template v-for="(block, blockIndex) in blocks" :key="`${block.type}-${blockIndex}`">
      <component :is="headingTag(block)" v-if="block.type === 'heading'" class="公告Markdown標題">
        <template v-for="(part, partIndex) in block.parts" :key="`${blockIndex}-${partIndex}`">
          <a v-if="part.type === 'link'" :href="part.url" target="_blank" rel="noopener noreferrer">{{ part.label }}</a>
          <strong v-else-if="part.type === 'strong'">{{ part.text }}</strong>
          <code v-else-if="part.type === 'code'">{{ part.text }}</code>
          <span v-else>{{ part.text }}</span>
        </template>
      </component>

      <p v-else-if="block.type === 'paragraph'">
        <template v-for="(part, partIndex) in block.parts" :key="`${blockIndex}-${partIndex}`">
          <a v-if="part.type === 'link'" :href="part.url" target="_blank" rel="noopener noreferrer">{{ part.label }}</a>
          <strong v-else-if="part.type === 'strong'">{{ part.text }}</strong>
          <code v-else-if="part.type === 'code'">{{ part.text }}</code>
          <span v-else>{{ part.text }}</span>
        </template>
      </p>

      <component :is="listTag(block)" v-else-if="block.type === 'list'">
        <li v-for="(item, itemIndex) in block.items" :key="`${blockIndex}-${itemIndex}`">
          <template v-for="(part, partIndex) in item" :key="`${blockIndex}-${itemIndex}-${partIndex}`">
            <a v-if="part.type === 'link'" :href="part.url" target="_blank" rel="noopener noreferrer">{{ part.label }}</a>
            <strong v-else-if="part.type === 'strong'">{{ part.text }}</strong>
            <code v-else-if="part.type === 'code'">{{ part.text }}</code>
            <span v-else>{{ part.text }}</span>
          </template>
        </li>
      </component>
    </template>
  </div>
</template>
