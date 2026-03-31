const STATUS_OPTIONS = ["Submitted", "In Review", "In Progress", "Resolved", "Closed"];
const MESSAGE_STATUS_OPTIONS = ["New", "Reviewed", "Replied", "Archived"];
const ADMIN_TOKEN_STORAGE_KEY = "golfmeadows_admin_token";

const api = {
  async request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    const token = getAdminToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(path, { ...options, headers });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || `Request failed: ${response.status}`);
    }
    return data;
  },
  get(path) {
    return this.request(path);
  },
  post(path, payload) {
    return this.request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  postForm(path, payload) {
    return this.request(path, {
      method: "POST",
      body: payload,
    });
  },
  patch(path, payload) {
    return this.request(path, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  put(path, payload) {
    return this.request(path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  delete(path) {
    return this.request(path, { method: "DELETE" });
  },
};

const $ = (selector) => document.querySelector(selector);

const statusEl = $("#admin-status");
const announcementForm = $("#announcement-form");
const announcementList = $("#announcement-list");
const eventForm = $("#event-form");
const eventList = $("#event-list");
const resourceForm = $("#resource-form");
const resourceList = $("#resource-list");
const aboutForm = $("#about-form");
const aboutValue = $("#about-value");
const heroBackgroundUrl = $("#hero-background-url");
const heroOverlayOpacity = $("#hero-overlay-opacity");
const serviceList = $("#service-admin-list");
const messageList = $("#messages-admin-list");
const carouselList = $("#carousel-admin-list");
const authTokenInput = $("#admin-auth-token");
const authSaveBtn = $("#admin-auth-save");
const authClearBtn = $("#admin-auth-clear");
const authGoogleBtn = $("#admin-auth-google");
const authEmailInput = $("#admin-auth-email");
const authPasswordInput = $("#admin-auth-password");
const authFormBtn = $("#admin-auth-login");
const authLogoutBtn = $("#admin-auth-logout");
const adminUserCreateForm = $("#admin-user-create-form");
const adminUserList = $("#admin-user-list");
const googleSigninContainer = $("#google-signin-container");
const carouselUploadForm = $("#carousel-upload-form");
const carouselUploadInput = $("#carousel-upload-input");
const carouselUploadCaption = $("#carousel-upload-caption");

let googleAuthConfigured = false;
let googleClientId = "";
let googleInitialized = false;
let googleScriptPromise = null;
let sessionIdentity = "";

function getAdminToken() {
  return window.localStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) || "";
}

function setAdminToken(value) {
  const trimmed = (value || "").trim();
  if (!trimmed) {
    window.localStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, trimmed);
}

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? "#ffd2d8" : "#cde0fb";
}

function currentAdminIdentity() {
  const token = getAdminToken();
  if (!token) return "";
  const parts = token.split(".");
  if (parts.length === 3) {
    try {
      const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
      const email = String(payload.email || "").trim().toLowerCase();
      if (email) return email;
    } catch {
      // fall back to token identity.
    }
  }
  return "admin-token";
}

function createButton(text, className, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = text;
  button.addEventListener("click", onClick);
  return button;
}

function createTextLine(tag, text, strongPrefix = null) {
  const line = document.createElement(tag);
  if (strongPrefix) {
    const strong = document.createElement("strong");
    strong.textContent = `${strongPrefix}: `;
    line.appendChild(strong);
  }
  line.appendChild(document.createTextNode(text));
  return line;
}

async function loadAdminUsers() {
  if (!adminUserList) return;
  const users = await api.get("/api/v1/admin/users");
  renderList(
    adminUserList,
    users,
    (user) => {
      const root = document.createElement("article");
      root.className = "admin-item";
      root.appendChild(createTextLine("h4", user.email));
      root.appendChild(createTextLine("p", user.role, "Role"));
      root.appendChild(createTextLine("p", user.is_active ? "Active" : "Inactive", "Status"));

      const actions = document.createElement("div");
      actions.className = "admin-item-actions";

      const toggleBtn = createButton(
        user.is_active ? "Disable" : "Enable",
        "btn btn-secondary",
        async () => {
          await api.patch(`/api/v1/admin/users/${user.id}`, {
            is_active: !user.is_active,
          });
          setStatus(`${user.email} ${user.is_active ? "disabled" : "enabled"}.`);
          await loadAdminUsers();
        }
      );
      actions.appendChild(toggleBtn);

      const resetBtn = createButton("Reset Password", "btn btn-secondary", async () => {
        const password = window.prompt(`New password for ${user.email}`);
        if (!password) return;
        await api.patch(`/api/v1/admin/users/${user.id}`, { password });
        setStatus(`Password reset for ${user.email}.`);
      });
      actions.appendChild(resetBtn);

      root.appendChild(actions);
      return root;
    },
    "No admin users found."
  );
}

async function loadGoogleIdentityScript() {
  if (window.google?.accounts?.id) return;
  if (!googleScriptPromise) {
    googleScriptPromise = new Promise((resolve, reject) => {
      const existing = document.getElementById("google-client-script");
      const script = existing || document.createElement("script");

      if (!existing) {
        script.id = "google-client-script";
        script.src = "https://accounts.google.com/gsi/client";
        script.async = true;
        script.defer = true;
        document.head.appendChild(script);
      }

      const timeout = window.setTimeout(() => {
        reject(
          new Error(
            "Timed out loading Google Identity Services. Check network/CSP settings."
          )
        );
      }, 10000);

      const onLoad = () => {
        window.clearTimeout(timeout);
        if (!window.google?.accounts?.id) {
          reject(new Error("Google script loaded but GIS API is unavailable."));
          return;
        }
        resolve();
      };

      const onError = () => {
        window.clearTimeout(timeout);
        reject(new Error("Could not load Google Identity Services script."));
      };

      script.addEventListener("load", onLoad, { once: true });
      script.addEventListener("error", onError, { once: true });

      if (window.google?.accounts?.id) {
        window.clearTimeout(timeout);
        resolve();
      }
    });
  }
  try {
    await googleScriptPromise;
  } catch (error) {
    googleScriptPromise = null;
    throw error;
  }
}

async function ensureGoogleInitialized() {
  if (!googleAuthConfigured || !googleClientId) {
    throw new Error("Google sign-in is not configured on this deployment.");
  }

  await loadGoogleIdentityScript();
  if (!window.google?.accounts?.id) {
    throw new Error("Google Identity Services is unavailable in this browser.");
  }

  if (googleInitialized) return;

  window.google.accounts.id.initialize({
    client_id: googleClientId,
    auto_select: false,
    cancel_on_tap_outside: true,
    callback: async (response) => {
      if (!response.credential) {
        setStatus("Google sign-in did not return an ID token.", true);
        return;
      }
      setAdminToken(response.credential);
      authTokenInput.value = getAdminToken();
      await init();
    },
  });

  if (googleSigninContainer) {
    googleSigninContainer.innerHTML = "";
    window.google.accounts.id.renderButton(googleSigninContainer, {
      type: "standard",
      theme: "outline",
      shape: "pill",
      size: "large",
      text: "signin_with",
      width: 280,
    });
  }

  googleInitialized = true;
}

function promptMomentMessage(notification) {
  try {
    if (notification?.isNotDisplayed?.()) {
      const reason = notification.getNotDisplayedReason?.() || "unknown";
      return `Google prompt not displayed (${reason}). Use the Google button below.`;
    }
    if (notification?.isSkippedMoment?.()) {
      const reason = notification.getSkippedReason?.() || "unknown";
      return `Google prompt skipped (${reason}). Use the Google button below.`;
    }
  } catch {
    return "";
  }
  return "";
}

function renderList(container, items, renderer, emptyText) {
  container.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = emptyText;
    container.appendChild(empty);
    return;
  }
  items.forEach((item) => container.appendChild(renderer(item)));
}

async function loadAnnouncements() {
  const items = await api.get("/api/v1/announcements");
  renderList(
    announcementList,
    items,
    (item) => {
      const root = document.createElement("article");
      root.className = "admin-item";
      root.appendChild(createTextLine("h4", item.title));
      root.appendChild(createTextLine("p", item.tag, "Tag"));
      root.appendChild(createTextLine("p", item.body));

      const actions = document.createElement("div");
      actions.className = "admin-item-actions";
      actions.appendChild(
        createButton("Delete", "btn btn-danger", async () => {
          await api.delete(`/api/v1/admin/announcements/${item.id}`);
          setStatus("Announcement deleted.");
          await loadAnnouncements();
        })
      );
      root.appendChild(actions);
      return root;
    },
    "No announcements yet."
  );
}

async function loadEvents() {
  const items = await api.get("/api/v1/events");
  renderList(
    eventList,
    items,
    (item) => {
      const root = document.createElement("article");
      root.className = "admin-item";
      root.appendChild(createTextLine("h4", item.title));
      root.appendChild(createTextLine("p", item.event_date, "Date"));
      root.appendChild(createTextLine("p", item.details));

      const actions = document.createElement("div");
      actions.className = "admin-item-actions";
      actions.appendChild(
        createButton("Delete", "btn btn-danger", async () => {
          await api.delete(`/api/v1/admin/events/${item.id}`);
          setStatus("Event deleted.");
          await loadEvents();
        })
      );
      root.appendChild(actions);
      return root;
    },
    "No events yet."
  );
}

async function loadResources() {
  const items = await api.get("/api/v1/resources");
  renderList(
    resourceList,
    items,
    (item) => {
      const root = document.createElement("article");
      root.className = "admin-item";
      root.appendChild(createTextLine("h4", item.title));
      root.appendChild(createTextLine("p", item.description));
      root.appendChild(createTextLine("p", item.file_url, "URL"));

      const actions = document.createElement("div");
      actions.className = "admin-item-actions";
      actions.appendChild(
        createButton("Delete", "btn btn-danger", async () => {
          await api.delete(`/api/v1/admin/resources/${item.id}`);
          setStatus("Resource deleted.");
          await loadResources();
        })
      );
      root.appendChild(actions);
      return root;
    },
    "No resources yet."
  );
}

async function loadAboutSetting() {
  try {
    const data = await api.get("/api/v1/admin/site-settings/about_text");
    aboutValue.value = data.value || "";
  } catch {
    aboutValue.value = "";
  }

  try {
    const heroData = await api.get("/api/v1/admin/site-settings/hero_background_url");
    heroBackgroundUrl.value = heroData.value || "";
  } catch {
    heroBackgroundUrl.value = "";
  }

  try {
    const overlayData = await api.get("/api/v1/admin/site-settings/hero_overlay_opacity");
    heroOverlayOpacity.value = overlayData.value || "0.48";
  } catch {
    heroOverlayOpacity.value = "0.48";
  }
}

function buildSelect(options, currentValue, onChange) {
  const select = document.createElement("select");
  options.forEach((option) => {
    const el = document.createElement("option");
    el.value = option;
    el.textContent = option;
    if (option === currentValue) el.selected = true;
    select.appendChild(el);
  });
  select.addEventListener("change", onChange);
  return select;
}

async function loadServiceRequests() {
  const items = await api.get("/api/v1/admin/service-requests");
  const me = sessionIdentity || currentAdminIdentity();
  renderList(
    serviceList,
    items,
    (item) => {
      const root = document.createElement("article");
      root.className = "admin-item";
      root.appendChild(createTextLine("h4", item.ticket_ref));
      root.appendChild(
        createTextLine(
          "p",
          `${item.category} (${item.priority}) - ${item.resident_name} (${item.flat_number})`
        )
      );
      root.appendChild(createTextLine("p", item.description));
      root.appendChild(createTextLine("p", item.admin_notes || "No internal note yet.", "Notes"));
      const assignee = item.assigned_to || "Unassigned";
      root.appendChild(createTextLine("p", assignee, "Assigned To"));

      const actions = document.createElement("div");
      actions.className = "admin-item-actions";

      const assignedToCurrent = item.assigned_to && item.assigned_to === me;
      const assignedToOther = item.assigned_to && item.assigned_to !== me;

      const assignSelfButton = createButton("Assign to Me", "btn btn-secondary", async () => {
        await api.post(`/api/v1/admin/service-requests/${item.id}/assign`, {});
        setStatus(`Assigned ${item.ticket_ref} to you.`);
        await loadServiceRequests();
      });
      assignSelfButton.disabled = Boolean(item.assigned_to);
      actions.appendChild(assignSelfButton);

      const takeoverButton = createButton("Take Over", "btn btn-secondary", async () => {
        await api.post(`/api/v1/admin/service-requests/${item.id}/takeover`, {});
        setStatus(`Took over ${item.ticket_ref}.`);
        await loadServiceRequests();
      });
      takeoverButton.disabled = !assignedToOther;
      actions.appendChild(takeoverButton);

      actions.appendChild(
        buildSelect(STATUS_OPTIONS, item.status, async (event) => {
          await api.patch(`/api/v1/admin/service-requests/${item.id}`, {
            status: event.target.value,
          });
          setStatus(`Updated ${item.ticket_ref} to ${event.target.value}.`);
          await loadServiceRequests();
        })
      );
      actions.lastChild.disabled = !assignedToCurrent;

      const noteButton = createButton("Add Admin Note", "btn btn-secondary", async () => {
        const note = window.prompt("Enter admin note");
        if (!note) return;
        await api.patch(`/api/v1/admin/service-requests/${item.id}`, {
          admin_notes: note,
        });
        setStatus(`Saved note for ${item.ticket_ref}.`);
        await loadServiceRequests();
      });
      noteButton.disabled = !assignedToCurrent;
      actions.appendChild(noteButton);

      const timelineButton = createButton("Add Timeline Update", "btn btn-secondary", async () => {
        const note = window.prompt("Timeline note");
        if (note === null) return;
        await api.post(`/api/v1/admin/service-requests/${item.id}/activities`, {
          note,
          status: item.status,
        });
        setStatus(`Timeline updated for ${item.ticket_ref}.`);
      });
      timelineButton.disabled = !assignedToCurrent;
      actions.appendChild(timelineButton);

      root.appendChild(actions);
      return root;
    },
    "No service requests yet."
  );
}

async function loadMessages() {
  const items = await api.get("/api/v1/admin/messages");
  renderList(
    messageList,
    items,
    (item) => {
      const root = document.createElement("article");
      root.className = "admin-item";
      root.appendChild(createTextLine("h4", item.subject));
      root.appendChild(createTextLine("p", `${item.resident_name} (${item.contact})`));
      root.appendChild(createTextLine("p", item.message));

      const actions = document.createElement("div");
      actions.className = "admin-item-actions";
      actions.appendChild(
        buildSelect(MESSAGE_STATUS_OPTIONS, item.status, async (event) => {
          await api.patch(`/api/v1/admin/messages/${item.id}`, {
            status: event.target.value,
          });
          setStatus(`Message status changed to ${event.target.value}.`);
          await loadMessages();
        })
      );
      root.appendChild(actions);
      return root;
    },
    "No messages yet."
  );
}

async function loadCarouselAdmin() {
  const data = await api.get("/api/v1/carousel");
  const uploaded = (data.items || []).filter((item) => item.source === "uploaded");
  renderList(
    carouselList,
    uploaded,
    (item) => {
      const root = document.createElement("article");
      root.className = "admin-item";
      const image = document.createElement("img");
      image.src = item.url;
      image.alt = item.caption || "Uploaded image";
      image.className = "admin-image-preview";
      root.appendChild(image);
      root.appendChild(createTextLine("p", item.caption || "Untitled"));

      const actions = document.createElement("div");
      actions.className = "admin-item-actions";
      actions.appendChild(
        createButton("Delete", "btn btn-danger", async () => {
          await api.delete(`/api/v1/admin/carousel/${item.id}`);
          setStatus("Carousel image deleted.");
          await loadCarouselAdmin();
        })
      );
      root.appendChild(actions);
      return root;
    },
    "No uploaded carousel images yet."
  );
}

carouselUploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = carouselUploadInput.files?.[0];
  if (!file) {
    setStatus("Select an image to upload.", true);
    return;
  }
  const form = new FormData();
  form.append("caption", carouselUploadCaption.value.trim());
  form.append("image", file);
  try {
    await api.postForm("/api/v1/admin/carousel/upload", form);
    carouselUploadForm.reset();
    setStatus("Carousel photo uploaded.");
    await loadCarouselAdmin();
  } catch (error) {
    setStatus(error.message, true);
  }
});

announcementForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(announcementForm).entries());
  try {
    await api.post("/api/v1/admin/announcements", payload);
    announcementForm.reset();
    setStatus("Announcement added.");
    await loadAnnouncements();
  } catch (error) {
    setStatus(error.message, true);
  }
});

eventForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(eventForm).entries());
  try {
    await api.post("/api/v1/admin/events", payload);
    eventForm.reset();
    setStatus("Event added.");
    await loadEvents();
  } catch (error) {
    setStatus(error.message, true);
  }
});

resourceForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(resourceForm).entries());
  try {
    await api.post("/api/v1/admin/resources", payload);
    resourceForm.reset();
    setStatus("Resource added.");
    await loadResources();
  } catch (error) {
    setStatus(error.message, true);
  }
});

aboutForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const parsedOverlay = Number.parseFloat(heroOverlayOpacity.value || "0.48");
    const clampedOverlay = Number.isFinite(parsedOverlay)
      ? Math.max(0, Math.min(1, parsedOverlay))
      : 0.48;
    await api.put("/api/v1/admin/site-settings/about_text", { value: aboutValue.value });
    await api.put("/api/v1/admin/site-settings/hero_background_url", {
      value: heroBackgroundUrl.value.trim(),
    });
    await api.put("/api/v1/admin/site-settings/hero_overlay_opacity", {
      value: String(clampedOverlay),
    });
    heroOverlayOpacity.value = String(clampedOverlay);
    setStatus("About section updated.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

authSaveBtn.addEventListener("click", async () => {
  setAdminToken(authTokenInput.value);
  authTokenInput.value = getAdminToken();
  await init();
});

authFormBtn.addEventListener("click", async () => {
  const email = (authEmailInput.value || "").trim();
  const password = authPasswordInput.value || "";
  if (!email || !password) {
    setStatus("Enter email and password for form login.", true);
    return;
  }
  try {
    const session = await api.post("/api/v1/admin/auth/login", { email, password });
    setAdminToken(session.access_token);
    authTokenInput.value = getAdminToken();
    authPasswordInput.value = "";
    await init();
  } catch (error) {
    setStatus(error.message, true);
  }
});

if (adminUserCreateForm) {
  adminUserCreateForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(adminUserCreateForm).entries());
    try {
      await api.post("/api/v1/admin/users", {
        email: String(payload.email || "").trim(),
        password: String(payload.password || ""),
        role: String(payload.role || "admin").trim().toLowerCase(),
        is_active: true,
      });
      adminUserCreateForm.reset();
      setStatus("Admin user created.");
      await loadAdminUsers();
    } catch (error) {
      setStatus(error.message, true);
    }
  });
}

authLogoutBtn.addEventListener("click", async () => {
  try {
    const token = getAdminToken();
    if (token) {
      await api.post("/api/v1/admin/auth/logout", {});
    }
  } catch {
    // Best-effort logout; always clear local token.
  } finally {
    setAdminToken("");
    authTokenInput.value = "";
    authPasswordInput.value = "";
    sessionIdentity = "";
    setStatus("Logged out.");
  }
});

authClearBtn.addEventListener("click", () => {
  setAdminToken("");
  authTokenInput.value = "";
  setStatus("Admin token cleared.");
});

authGoogleBtn.addEventListener("click", async () => {
  try {
    setStatus("Opening Google account chooser...");
    await ensureGoogleInitialized();
    window.google.accounts.id.prompt((notification) => {
      const message = promptMomentMessage(notification);
      if (message) setStatus(message, true);
    });
  } catch (error) {
    setStatus(error.message, true);
  }
});

async function loadAuthConfig() {
  const data = await api.get("/api/v1/admin/auth/config");
  googleAuthConfigured = Boolean(data.google_enabled);
  googleClientId = data.google_client_id || "";
  if (authGoogleBtn) {
    authGoogleBtn.disabled = !googleAuthConfigured;
  }
  if (!googleAuthConfigured && googleSigninContainer) {
    googleSigninContainer.innerHTML = "";
    googleInitialized = false;
  }
  if (googleAuthConfigured) {
    try {
      await ensureGoogleInitialized();
      setStatus("Google sign-in is ready.");
    } catch (error) {
      setStatus(`Google sign-in setup issue: ${error.message}`, true);
    }
  }
}

async function validateSession() {
  const session = await api.get("/api/v1/admin/session");
  sessionIdentity = String(session.identity || "").trim().toLowerCase();
  return session;
}

async function init() {
  setStatus("Loading admin data...");
  try {
    await loadAuthConfig();
    authTokenInput.value = getAdminToken();
    await validateSession();
    await Promise.all([
      loadAnnouncements(),
      loadEvents(),
      loadResources(),
      loadAboutSetting(),
      loadServiceRequests(),
      loadMessages(),
      loadCarouselAdmin(),
      loadAdminUsers(),
    ]);
    setStatus("Admin dashboard loaded.");
  } catch (error) {
    const msg =
      error.message === "Admin authentication required."
        ? "Admin authentication required. Enter token or use Google sign-in."
        : error.message;
    setStatus(msg, true);
  }
}

init();
