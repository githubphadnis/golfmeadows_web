const STATUS_OPTIONS = ["Submitted", "In Review", "In Progress", "Resolved", "Closed"];
const MESSAGE_STATUS_OPTIONS = ["New", "Reviewed", "Replied", "Archived"];

const api = {
  async request(path, options = {}) {
    const response = await fetch(path, options);
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
const serviceList = $("#service-admin-list");
const messageList = $("#messages-admin-list");
const carouselList = $("#carousel-admin-list");
const recipientsForm = $("#recipients-form");
const serviceRecipientsInput = $("#service-recipients");
const feedbackRecipientsInput = $("#feedback-recipients");
const heroImageForm = $("#hero-form");
const heroImageUrlInput = $("#hero-image-url");
const notificationAuditList = $("#notification-audit-list");

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? "#ffd2d8" : "#cde0fb";
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
          await api.delete(`/api/v1/announcements/${item.id}`);
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
          await api.delete(`/api/v1/events/${item.id}`);
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
          await api.delete(`/api/v1/resources/${item.id}`);
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
    const data = await api.get("/api/v1/site-settings/about_text");
    aboutValue.value = data.value || "";
  } catch {
    aboutValue.value = "";
  }
}

function parseRecipientInput(value) {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function formatRecipientInput(values) {
  if (!Array.isArray(values) || !values.length) return "";
  return values.join(", ");
}

async function loadRecipientSettings() {
  try {
    const data = await api.get("/api/v1/admin/recipient-settings");
    serviceRecipientsInput.value = formatRecipientInput(data.service_request_recipients);
    feedbackRecipientsInput.value = formatRecipientInput(data.feedback_recipients);
  } catch (error) {
    setStatus(`Could not load recipient settings: ${error.message}`, true);
  }
}

async function loadHeroImageSetting() {
  try {
    const data = await api.get("/api/v1/site-settings/hero_image_url");
    heroImageUrlInput.value = data.value || "";
  } catch {
    heroImageUrlInput.value = "";
  }
}

async function loadNotificationAudit() {
  const items = await api.get("/api/v1/admin/notification-audit");
  renderList(
    notificationAuditList,
    items,
    (item) => {
      const root = document.createElement("article");
      root.className = "admin-item";
      root.appendChild(createTextLine("h4", item.subject || item.event_type));
      root.appendChild(createTextLine("p", item.event_type, "Type"));
      root.appendChild(createTextLine("p", (item.recipients || []).join(", ") || "No recipients", "Recipients"));
      root.appendChild(createTextLine("p", item.status, "Status"));
      root.appendChild(createTextLine("p", item.detail || "-", "Detail"));
      root.appendChild(createTextLine("p", item.created_at, "At"));
      return root;
    },
    "No notification activity yet."
  );
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
  const items = await api.get("/api/v1/service-requests");
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
      if (item.response_due_at || item.resolve_due_at) {
        root.appendChild(
          createTextLine(
            "p",
            `${item.response_due_at || "-"} / ${item.resolve_due_at || "-"}`,
            "SLA response/resolve due"
          )
        );
      }
      if (item.response_sla_breached || item.resolve_sla_breached) {
        const breachBits = [];
        if (item.response_sla_breached) breachBits.push("Response SLA breached");
        if (item.resolve_sla_breached) breachBits.push("Resolution SLA breached");
        root.appendChild(createTextLine("p", breachBits.join(" | "), "SLA"));
      }
      root.appendChild(createTextLine("p", item.admin_notes || "No internal note yet.", "Notes"));

      const actions = document.createElement("div");
      actions.className = "admin-item-actions";
      actions.appendChild(
        buildSelect(STATUS_OPTIONS, item.status, async (event) => {
          await api.patch(`/api/v1/service-requests/${item.id}`, {
            status: event.target.value,
          });
          setStatus(`Updated ${item.ticket_ref} to ${event.target.value}.`);
          await loadServiceRequests();
        })
      );

      const noteButton = createButton("Add Admin Note", "btn btn-secondary", async () => {
        const note = window.prompt("Enter admin note");
        if (!note) return;
        await api.patch(`/api/v1/service-requests/${item.id}`, {
          admin_notes: note,
        });
        setStatus(`Saved note for ${item.ticket_ref}.`);
        await loadServiceRequests();
      });
      actions.appendChild(noteButton);

      const timelineButton = createButton("Add Timeline Update", "btn btn-secondary", async () => {
        const note = window.prompt("Timeline note");
        if (note === null) return;
        await api.post(`/api/v1/service-requests/${item.id}/activities`, {
          note,
          actor: "admin",
          status: item.status,
        });
        setStatus(`Timeline updated for ${item.ticket_ref}.`);
      });
      actions.appendChild(timelineButton);

      root.appendChild(actions);
      return root;
    },
    "No service requests yet."
  );
}

async function loadMessages() {
  const items = await api.get("/api/v1/messages");
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
          await api.patch(`/api/v1/messages/${item.id}`, {
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
          await api.delete(`/api/v1/carousel/${item.id}`);
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

announcementForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(announcementForm).entries());
  try {
    await api.post("/api/v1/announcements", payload);
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
    await api.post("/api/v1/events", payload);
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
    await api.post("/api/v1/resources", payload);
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
    await api.put("/api/v1/site-settings/about_text", { value: aboutValue.value });
    setStatus("About section updated.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

recipientsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    service_request_recipients: parseRecipientInput(serviceRecipientsInput.value),
    feedback_recipients: parseRecipientInput(feedbackRecipientsInput.value),
  };
  try {
    const saved = await api.put("/api/v1/admin/recipient-settings", payload);
    serviceRecipientsInput.value = formatRecipientInput(saved.service_request_recipients);
    feedbackRecipientsInput.value = formatRecipientInput(saved.feedback_recipients);
    setStatus("Notification recipient lists updated.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

heroImageForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const payload = { hero_image_url: heroImageUrlInput.value.trim() };
    await api.put("/api/v1/admin/hero-image", payload);
    setStatus("Hero background image setting updated.");
  } catch (error) {
    setStatus(error.message, true);
  }
});

async function init() {
  setStatus("Loading admin data...");
  try {
    await Promise.all([
      loadAnnouncements(),
      loadEvents(),
      loadResources(),
      loadAboutSetting(),
      loadRecipientSettings(),
      loadHeroImageSetting(),
      loadServiceRequests(),
      loadMessages(),
      loadCarouselAdmin(),
      loadNotificationAudit(),
    ]);
    setStatus("Admin dashboard loaded.");
  } catch (error) {
    setStatus(error.message, true);
  }
}

init();
