<script setup>
import { ref, computed, onMounted } from "vue";
import { useFirestore } from "../composables/useFirestore.js";
import TerminalCard from "./TerminalCard.vue";

const { isAdmin, listAllUsers, updateUserPermissions } = useFirestore();

const users = ref([]);
const loading = ref(false);
const search = ref("");
const saving = ref({});

onMounted(async () => { await refresh(); });

async function refresh() {
  loading.value = true;
  try { users.value = await listAllUsers(); }
  catch (e) { console.error("Failed to load users:", e); }
  finally { loading.value = false; }
}

const filtered = computed(() => {
  const q = search.value.toLowerCase().trim();
  if (!q) return users.value;
  return users.value.filter(u =>
    u.uid.toLowerCase().includes(q) ||
    (u.email || "").toLowerCase().includes(q) ||
    (u.display_name || "").toLowerCase().includes(q)
  );
});

async function togglePerm(uid, field, current) {
  saving.value[uid + field] = true;
  try {
    await updateUserPermissions(uid, { [field]: !current });
    // Update local state
    const u = users.value.find(x => x.uid === uid);
    if (u) u[field] = !current;
  } catch (e) {
    console.error("Failed to update:", e);
  } finally {
    saving.value[uid + field] = false;
  }
}

function fmtDate(d) {
  if (!d) return "-";
  const t = d.toDate ? d.toDate() : new Date(d);
  return t.toLocaleString("sv").slice(0, 16);
}
</script>

<template>
  <div class="admin-panel" v-if="isAdmin">
    <TerminalCard title="admin" :min-width="80" :collapsible="true">
      <div class="admin-bar">
        <input v-model="search" placeholder="search by id, email, or name..." class="admin-search" />
        <span class="dim">{{ filtered.length }}/{{ users.length }} users</span>
        <span class="spacer"></span>
        <span class="pop-link g" @click="refresh">{{ loading ? 'loading...' : '[ refresh ]' }}</span>
      </div>

      <div class="user-list">
        <div class="user-header dim">
          <span class="u-uid">UID</span>
          <span class="u-name">NAME</span>
          <span class="u-email">EMAIL</span>
          <span class="u-perm">RUN</span>
          <span class="u-perm">ADMIN</span>
          <span class="u-date">CREATED</span>
        </div>
        <div v-for="u in filtered" :key="u.uid" class="user-row">
          <span class="u-uid dim" :title="u.uid">{{ u.uid.slice(0, 12) }}...</span>
          <span class="u-name">{{ u.display_name || "-" }}</span>
          <span class="u-email dim">{{ u.email || "-" }}</span>
          <span class="u-perm">
            <span class="pop-link" :class="u.can_run_experiments ? 'g' : 'r'"
              @click="togglePerm(u.uid, 'can_run_experiments', u.can_run_experiments)">
              {{ saving[u.uid + 'can_run_experiments'] ? '...' : (u.can_run_experiments ? 'yes' : 'no') }}
            </span>
          </span>
          <span class="u-perm">
            <span class="pop-link" :class="u.is_admin ? 'g' : 'r'"
              @click="togglePerm(u.uid, 'is_admin', u.is_admin)">
              {{ saving[u.uid + 'is_admin'] ? '...' : (u.is_admin ? 'yes' : 'no') }}
            </span>
          </span>
          <span class="u-date dim">{{ fmtDate(u.created_at) }}</span>
        </div>
        <div v-if="!filtered.length" class="dim" style="padding:var(--sp-sm) 0">
          {{ search ? 'no users match search' : 'no users found' }}
        </div>
      </div>
    </TerminalCard>
  </div>
</template>

<style scoped>
.admin-panel { margin-top: var(--sp-sm); }
.admin-bar {
  display: flex; align-items: center; gap: var(--sp-sm);
  padding-bottom: var(--sp-xs); margin-bottom: var(--sp-xs);
  border-bottom: var(--border-hair);
}
.admin-search {
  background: var(--bg-deep); border: var(--border-subtle); border-radius: var(--radius-sm);
  color: var(--text); font: var(--fs-ui) var(--font-mono);
  padding: 1px var(--sp-sm); outline: none; width: 28ch;
}
.admin-search:focus { border-color: var(--green); }
.admin-search::placeholder { color: var(--text-dim); }

.user-list { font-size: var(--fs-base); line-height: var(--lh-loose); }
.user-header {
  display: flex; gap: var(--sp-sm);
  font-size: var(--fs-sm); padding: var(--sp-xxs) 0;
  border-bottom: var(--border-hair);
}
.user-row {
  display: flex; gap: var(--sp-sm); align-items: baseline;
  padding: var(--sp-xxs) 0;
  border-bottom: var(--border-hair);
}
.user-row:last-child { border-bottom: none; }

.u-uid   { width: 14ch; flex-shrink: 0; overflow: hidden; }
.u-name  { width: 20ch; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.u-email { width: 24ch; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.u-perm  { width: 6ch; flex-shrink: 0; text-align: center; }
.u-date  { width: 16ch; flex-shrink: 0; }

.pop-link { cursor: pointer; font-size: var(--fs-base); }
.pop-link.g { color: var(--green); }
.pop-link.r { color: var(--red); }
.pop-link:hover { text-decoration: underline; }
</style>
