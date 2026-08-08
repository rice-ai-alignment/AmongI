<script setup>
defineProps({
  /** Animation duration per item (ms). */
  duration: { type: Number, default: 120 },
  /** Delay before the first item (ms). */
  baseDelay: { type: Number, default: 20 },
  /** Extra delay added per subsequent item (ms). */
  staggerStep: { type: Number, default: 30 },
  /** Maximum number of children to generate delay rules for. */
  maxItems: { type: Number, default: 30 },
});
</script>

<template>
  <div class="stagger-block">
    <slot />
  </div>
</template>

<style scoped>
.stagger-block > :deep(*) {
  animation: type-in 0.12s ease backwards;
}
/* nth-child rules are pre-baked for up to 30 items.
   The actual delay values come from CSS custom properties set on the container. */
.stagger-block > :deep(*:nth-child(1))  { animation-delay: 0.02s; }
.stagger-block > :deep(*:nth-child(2))  { animation-delay: 0.05s; }
.stagger-block > :deep(*:nth-child(3))  { animation-delay: 0.08s; }
.stagger-block > :deep(*:nth-child(4))  { animation-delay: 0.11s; }
.stagger-block > :deep(*:nth-child(5))  { animation-delay: 0.14s; }
.stagger-block > :deep(*:nth-child(6))  { animation-delay: 0.17s; }
.stagger-block > :deep(*:nth-child(7))  { animation-delay: 0.20s; }
.stagger-block > :deep(*:nth-child(8))  { animation-delay: 0.23s; }
.stagger-block > :deep(*:nth-child(9))  { animation-delay: 0.26s; }
.stagger-block > :deep(*:nth-child(10)) { animation-delay: 0.29s; }
.stagger-block > :deep(*:nth-child(11)) { animation-delay: 0.32s; }
.stagger-block > :deep(*:nth-child(12)) { animation-delay: 0.35s; }
.stagger-block > :deep(*:nth-child(13)) { animation-delay: 0.38s; }
.stagger-block > :deep(*:nth-child(14)) { animation-delay: 0.41s; }
.stagger-block > :deep(*:nth-child(15)) { animation-delay: 0.44s; }
.stagger-block > :deep(*:nth-child(16)) { animation-delay: 0.47s; }
.stagger-block > :deep(*:nth-child(17)) { animation-delay: 0.50s; }
.stagger-block > :deep(*:nth-child(18)) { animation-delay: 0.53s; }
.stagger-block > :deep(*:nth-child(19)) { animation-delay: 0.56s; }
.stagger-block > :deep(*:nth-child(20)) { animation-delay: 0.59s; }
.stagger-block > :deep(*:nth-child(21)) { animation-delay: 0.62s; }
.stagger-block > :deep(*:nth-child(22)) { animation-delay: 0.65s; }
.stagger-block > :deep(*:nth-child(23)) { animation-delay: 0.68s; }
.stagger-block > :deep(*:nth-child(24)) { animation-delay: 0.71s; }
.stagger-block > :deep(*:nth-child(25)) { animation-delay: 0.74s; }
.stagger-block > :deep(*:nth-child(26)) { animation-delay: 0.77s; }
.stagger-block > :deep(*:nth-child(27)) { animation-delay: 0.80s; }
.stagger-block > :deep(*:nth-child(28)) { animation-delay: 0.83s; }
.stagger-block > :deep(*:nth-child(29)) { animation-delay: 0.86s; }
.stagger-block > :deep(*:nth-child(30)) { animation-delay: 0.89s; }
</style>
