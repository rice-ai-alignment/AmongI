import { provide, inject, computed } from "vue";

export const BOX_KEY = Symbol("boxWidth");

export function provideBoxWidth(ref) {
  provide(BOX_KEY, ref);
}

export function useBoxWidth() {
  const shared = inject(BOX_KEY, null);

  function register(lineLength, title = "") {
    if (shared && lineLength > shared.value) {
      shared.value = lineLength;
    }
    const w = shared ? shared.value : 46;
    const makeHdr = (t) => {
      if (!t) return "┌" + "─".repeat(w - 2) + "┐";
      const inner = "─ " + t + " ";
      const fill = w - 2 - inner.length;
      if (fill < 0) return "┌" + "─".repeat(w - 2) + "┐";
      return "┌" + inner + "─".repeat(fill) + "┐";
    };
    return {
      w,
      pad(line) { return line.padEnd(w); },
      hdr: makeHdr(title),
      btm: "└" + "─".repeat(w - 2) + "┘",
    };
  }

  return { register };
}
