import { createApp } from "vue";

// Public TV landing page lives at "/". The dev/admin dashboard (all existing
// functionality, untouched) lives at "/dashboard" and the routes it already
// manages internally (/studies, /servers, /documentation, /admin).
const path = window.location.pathname;
const isDashboard =
  path === "/dashboard" || path.startsWith("/dashboard/") ||
  path.startsWith("/studies") || path.startsWith("/servers") ||
  path.startsWith("/documentation") || path.startsWith("/admin");

const componentPromise = isDashboard
  ? import("./App.vue")
  : import("./components/LandingPage.vue");

componentPromise.then((mod) => {
  createApp(mod.default).mount("#app");
});
