import { createApp } from "vue";

// One app for the whole site. App.vue picks its initial view from the
// pathname: "/" shows the live-stats home page, everything else is the
// existing dashboard (/dashboard, /studies, /servers, ...).
import App from "./App.vue";

createApp(App).mount("#app");
