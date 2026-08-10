<script setup>
import { ref, reactive } from "vue";
import TypedSpan from "./TypedSpan.vue";
import TerminalCard from "./TerminalCard.vue";

const props = defineProps({
  title: { type: String, default: "form" },
  /** Array of { key, label, placeholder?, type?, required?, options? }
   *  type: "text" | "select" — select fields need options: [{value, label}] */
  fields: { type: Array, default: () => [] },
  confirmText: { type: String, default: "[ create ]" },
  cancelText: { type: String, default: "[ cancel ]" },
});

const emit = defineEmits(["confirm", "cancel"]);

const form = reactive(
  Object.fromEntries(props.fields.map(f => [f.key, f.default || ""]))
);

function onOverlayClick() { emit("cancel"); }
function onSubmit() { emit("confirm", { ...form }); }
</script>

<template>
  <div class="popup-overlay" @click="onOverlayClick">
    <div class="popup" @click.stop>
      <TerminalCard :title="title" :min-width="48" :collapsible="false" :headSpeed="8">
        <div v-for="f in fields" :key="f.key" class="form-field">
          <span class="dim">{{ f.label }}: </span>
          <input
            v-if="!f.type || f.type === 'text'"
            v-model="form[f.key]"
            type="text"
            :placeholder="f.placeholder || ''"
            :required="f.required !== false"
            class="form-inp"
            autofocus
            @keyup.enter="onSubmit"
            @keyup.escape="$emit('cancel')"
          />
          <select
            v-else-if="f.type === 'select'"
            v-model="form[f.key]"
            class="form-inp"
            @keyup.escape="$emit('cancel')"
          >
            <option v-for="opt in (f.options || [])" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </div>
        <div class="popup-acts">
          <span class="pop-link" @click="$emit('cancel')">
            <TypedSpan :text="cancelText" :speed="15" :delay="200" />
          </span>
          <span class="pop-link g" @click="onSubmit">
            <TypedSpan :text="confirmText" :speed="15" :delay="400" />
          </span>
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
.pop-link.g:hover { color: var(--green); text-shadow: var(--glow-soft); }

.form-field {
  font-size: var(--fs-ui); padding: var(--sp-xxs) 0;
  display: flex; align-items: baseline; gap: var(--sp-xxs);
}
.form-inp {
  background: transparent; border: none; border-bottom: 1px solid rgba(79,232,124,0.2);
  color: var(--text); font: var(--fs-ui) var(--font-mono); outline: none; flex: 1; min-width: 0;
}
.form-inp:focus { border-bottom-color: var(--green); }
.form-inp::placeholder { color: var(--text-dim); }
select.form-inp {
  cursor: pointer;
}
select.form-inp option {
  background: var(--surface-2); color: var(--text);
}
</style>
