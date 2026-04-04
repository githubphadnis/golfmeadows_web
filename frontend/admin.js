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
const faqAdminList = $("#faq-admin-list");
const rotaForm = $("#rota-form");
const rotaContactEmail = $("#rota-contact-email");
const rotaServiceEmail = $("#rota-service-email");
const rotaFaqEmail = $("#rota-faq-email");
const authTokenInput = $("#admin-auth-token");
const authSaveBtn = $("#admin-auth-save");
const authClearBtn = $("#admin-auth-clear");
const authEmailInput = $("#admin-auth-email");
const authPasswordInput = $("#admin-auth-password");
const authFormBtn = $("#admin-auth-login");
const authLogoutBtn = $("#admin-auth-logout");
const tabButtons = document.querySelectorAll(".admin-tab-btn");
const tabPanels = document.querySelectorAll(".admin-tab-panel");
const carouselUploadForm = $("#carousel-upload-form");
const carouselUploadInput = $("#carousel-upload-input");
const carouselUploadCaption = $("#carousel-upload-caption");
const adminContentPanels = document.querySelectorAll("[data-admin-protected]");

let sessionIdentity = "";
let isAuthenticated = false;

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

function setAdminPanelsVisibility(showPanels) {
  adminContentPanels.forEach((panel) => {
    panel.hidden = !showPanels;
  });
}

function setActiveTab(tabName) {
  const target = String(tabName || "content");
  tabButtons.forEach((button) => {
    const isActive = button.dataset.tab === target;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });
  tabPanels.forEach((panel) => {
    panel.hidden = panel.dataset.tabPanel !== target;
  });
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
      root.appendChild(
        createTextLine("p", item.routed_to_email || "Not routed", "Routed Email")
      );

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
      root.appendChild(
        createTextLine("p", item.routed_to_email || "Not routed", "Routed Email")
      );
      root.appendChild(
        createTextLine("p", item.admin_response || "No answer yet.", "Latest Answer")
      );

      const actions = document.createElement("div");
      actions.className = "admin-item-actions";
      actions.appendChild(
        buildSelect(MESSAGE_STATUS_OPTIONS, item.status, async (event) => {
          const answer =
            event.target.value === "Replied"
              ? window.prompt(
                  "Enter answer text (this will auto-create/update FAQ).",
                  item.admin_response || ""
                )
              : item.admin_response || "";
          if (event.target.value === "Replied" && answer === null) {
            event.target.value = item.status;
            return;
          }
          await api.patch(`/api/v1/admin/messages/${item.id}`, {
            status: event.target.value,
            answer: answer || "",
          });
          setStatus(`Message status changed to ${event.target.value}.`);
          await loadMessages();
          await loadAdminFaqs();
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

async function loadAdminFaqs() {
  if (!faqAdminList) return;
  const items = await api.get("/api/v1/admin/faqs");
  renderList(
    faqAdminList,
    items,
    (item) => {
      const root = document.createElement("article");
      root.className = "admin-item";
      root.appendChild(createTextLine("h4", item.question));
      root.appendChild(createTextLine("p", item.answer));
      root.appendChild(
        createTextLine(
          "p",
          `${item.is_public ? "Public" : "Internal"} | ${item.source_type}`,
          "Visibility"
        )
      );
      return root;
    },
    "No FAQ entries yet."
  );
}

async function loadRota() {
  if (!rotaContactEmail || !rotaServiceEmail || !rotaFaqEmail) return;
  const interaction = await api.get("/api/v1/admin/interaction-emails");
  rotaContactEmail.value = interaction.contact_messages || "";
  rotaServiceEmail.value = interaction.service_requests || "";
  rotaFaqEmail.value = interaction.general_announcements || "";
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

if (rotaForm) {
  rotaForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const interactionPayload = {
        service_requests: (rotaServiceEmail.value || "").trim(),
        contact_messages: (rotaContactEmail.value || "").trim(),
        general_announcements: (rotaFaqEmail.value || "").trim(),
      };
      await api.put("/api/v1/admin/interaction-emails", interactionPayload);
      await api.put("/api/v1/admin/rota", {
        service_requests: {
          primary: interactionPayload.service_requests,
          secondary: "",
        },
        contact_messages: {
          primary: interactionPayload.contact_messages,
          secondary: "",
        },
        faq_review: {
          primary: interactionPayload.general_announcements,
          secondary: "",
        },
      });
      setStatus("Rota and interaction routing updated.");
      await loadRota();
    } catch (error) {
      setStatus(error.message, true);
    }
  });
}

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
    isAuthenticated = true;
    await init();
  } catch (error) {
    setStatus(error.message, true);
  }
});

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
    isAuthenticated = false;
    setAdminPanelsVisibility(false);
    setStatus("Logged out.");
  }
});

authClearBtn.addEventListener("click", () => {
  setAdminToken("");
  authTokenInput.value = "";
  setStatus("Admin token cleared.");
});

async function loadAuthConfig() {
  // Reserved for future auth mode metadata.
}

async function validateSession() {
  const session = await api.get("/api/v1/admin/session");
  sessionIdentity = String(session.identity || "").trim().toLowerCase();
  isAuthenticated = true;
  return session;
}

async function init() {
  setStatus("Loading admin data...");
  setAdminPanelsVisibility(false);
  try {
    await loadAuthConfig();
    authTokenInput.value = getAdminToken();
    await validateSession();
    setAdminPanelsVisibility(true);
    await Promise.all([
      loadAnnouncements(),
      loadEvents(),
      loadResources(),
      loadAboutSetting(),
      loadAdminFaqs(),
      loadRota(),
      loadServiceRequests(),
      loadMessages(),
      loadCarouselAdmin(),
    ]);
    setActiveTab("content");
    setStatus("Admin dashboard loaded.");
  } catch (error) {
    isAuthenticated = false;
    setAdminPanelsVisibility(false);
    const msg =
      error.message === "Admin authentication required."
        ? "Please log in to access admin content."
        : error.message;
    setStatus(msg, true);
  }
}

tabButtons.forEach((button) => {
  button.addEventListener("click", () => {
    if (!isAuthenticated) return;
    setActiveTab(button.dataset.tab);
  });
});

init();
