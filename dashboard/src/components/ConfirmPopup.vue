<script setup>
import TypedSpan from "./TypedSpan.vue";
import TerminalCard from "./TerminalCard.vue";

const props = defineProps({
  message: { type: String, default: "" },
  buttons: {
    type: Array,
    default: () => [
      { text: "[ cancel ]", action: "cancel" },
      { text: "[ confirm ]", action: "confirm", danger: true },
    ],
  },
});

const emit = defineEmits(["action"]);

function onOverlayClick() { emit("action", "cancel"); }
function onClick(btn) { emit("action", btn.action); }
</script>

<template>
  <div class="popup-overlay" @click="onOverlayClick">
    <div class="popup" @click.stop>
      <TerminalCard title="dialog" :min-width="36" :collapsible="false" :headSpeed="8">
        <div><TypedSpan :text="message" :speed="20" /></div>
        <div class="popup-acts">
          <span
            v-for="(btn, i) in buttons"
            :key="btn.action"
            class="pop-link"
            :class="{ r: btn.danger }"
            @click="onClick(btn)"
          ><TypedSpan :text="btn.text" :speed="15" :delay="400 + i * 200" /></span>
        </div>
      </TerminalCard>
    </div>
  </div>
</template>

<style scoped>
.popup-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.7);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.popup-acts { display: flex; gap: var(--sp-xl); justify-content: center; margin-top: var(--sp-sm); }
.pop-link { color: var(--text-dim); cursor: pointer; font-size: var(--fs-ui); }
.pop-link:hover { color: var(--text); }
.pop-link.r { color: var(--red); }
.pop-link.r:hover { color: var(--red); text-shadow: var(--glow-red); }
</style>
