import { onMounted, onUnmounted, ref, computed, watch, nextTick } from "vue";
import Typed from "typed.js";

// Types text into an element character by character.
// `strings` can be a string, array, computed ref, or a getter function.
// Re-types when the element ref changes OR the strings change.
export function useTypewriter(elRef, strings, opts = {}) {
  const done = ref(false);
  let instance = null;

  function getStrings() {
    const s = typeof strings === "function" ? strings() : (strings?.value ?? strings);
    return Array.isArray(s) ? s : [String(s || "")];
  }

  function start() {
    if (!elRef.value) return;
    if (instance) instance.destroy();
    done.value = false;
    instance = new Typed(elRef.value, {
      strings: getStrings(),
      typeSpeed: opts.typeSpeed || 20,
      startDelay: opts.startDelay || 0,
      showCursor: opts.showCursor !== undefined ? opts.showCursor : false,
      cursorChar: opts.cursorChar || "█",
      onComplete: (self) => {
        done.value = true;
        if (self.cursor) self.cursor.remove();
      },
    });
  }

  onMounted(() => {
    nextTick(start);
  });

  // Re-type when the element ref changes (Vue :key re-mount)
  watch(elRef, (el) => {
    if (el) nextTick(start);
  });

  // Re-type when the strings change (for computed refs / getter functions)
  const source = computed(() => getStrings().join(""));
  watch(source, () => {
    nextTick(start);
  });

  onUnmounted(() => {
    if (instance) instance.destroy();
  });

  return { done, restart: start };
}
