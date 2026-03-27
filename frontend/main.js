const api = {
  async get(path) {
    const response = await fetch(path);
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }
    return response.json();
  },
  async post(path, body, isForm = false) {
    const response = await fetch(path, {
      method: "POST",
      headers: isForm ? undefined : { "Content-Type": "application/json" },
      body: isForm ? body : JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || `Request failed: ${response.status}`);
    }
    return data;
  },
  async del(path) {
    const response = await fetch(path, { method: "DELETE" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || `Request failed: ${response.status}`);
    }
    return data;
  },
};

const carouselTrack = document.getElementById("carousel-track");
const dotsContainer = document.getElementById("carousel-dots");
const prevBtn = document.getElementById("prev-btn");
const nextBtn = document.getElementById("next-btn");
const uploadForm = document.getElementById("upload-form");
const uploadInput = document.getElementById("carousel-upload");
const uploadCaption = document.getElementById("upload-caption");
const uploadStatus = document.getElementById("upload-status");

const announcementsGrid = document.getElementById("announcements-grid");
const eventsList = document.getElementById("events-list");
const resourcesGrid = document.getElementById("resources-grid");
const aboutText = document.getElementById("about-text");

const serviceForm = document.getElementById("service-form");
const serviceStatus = document.getElementById("service-status");
const recentServiceList = document.getElementById("recent-service-list");
const ticketLookupForm = document.getElementById("ticket-lookup-form");
const ticketLookupInput = document.getElementById("ticket-lookup");
const ticketLookupStatus = document.getElementById("ticket-lookup-status");

const messageForm = document.getElementById("message-form");
const messageStatus = document.getElementById("message-status");

let slides = [];
let currentSlide = 0;
let autoplayTimer = null;

function setText(element, text) {
  element.textContent = text;
}

function createEl(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (typeof text === "string") element.textContent = text;
  return element;
}

function setEmpty(container, text) {
  container.innerHTML = "";
  container.appendChild(createEl("div", "empty-state", text));
}

function renderCarousel() {
  if (!slides.length) {
    carouselTrack.innerHTML = `<div class="slide"><div class="empty-state">No photos available yet.</div></div>`;
    dotsContainer.innerHTML = "";
    return;
  }

  carouselTrack.innerHTML = "";
  dotsContainer.innerHTML = "";
  slides.forEach((slide, index) => {
    const figure = document.createElement("figure");
    figure.className = "slide";

    const image = document.createElement("img");
    image.src = slide.url;
    image.alt = slide.caption || "GolfMeadows photo";
    figure.appendChild(image);

    const caption = document.createElement("figcaption");
    caption.className = "slide-caption";
    caption.textContent = slide.caption || "GolfMeadows";
    figure.appendChild(caption);

    carouselTrack.appendChild(figure);

    const dot = document.createElement("button");
    dot.className = `dot ${index === currentSlide ? "active" : ""}`;
    dot.dataset.index = String(index);
    dot.setAttribute("aria-label", `Go to slide ${index + 1}`);
    dotsContainer.appendChild(dot);
  });

  moveToSlide(currentSlide);
}

function moveToSlide(index) {
  if (!slides.length) return;
  currentSlide = (index + slides.length) % slides.length;
  carouselTrack.style.transform = `translateX(-${currentSlide * 100}%)`;

  [...dotsContainer.querySelectorAll(".dot")].forEach((dot, dotIndex) => {
    dot.classList.toggle("active", dotIndex === currentSlide);
  });
}

function startAutoplay() {
  stopAutoplay();
  autoplayTimer = setInterval(() => moveToSlide(currentSlide + 1), 5000);
}

function stopAutoplay() {
  if (autoplayTimer) {
    clearInterval(autoplayTimer);
    autoplayTimer = null;
  }
}

function resetAutoplay() {
  stopAutoplay();
  startAutoplay();
}

async function loadCarousel() {
  const data = await api.get("/api/v1/carousel");
  slides = data.items || [];
  if (currentSlide >= slides.length) currentSlide = 0;
  renderCarousel();
  startAutoplay();
}

async function loadBootstrap() {
  const data = await api.get("/api/v1/bootstrap");
  renderAnnouncements(data.announcements || []);
  renderEvents(data.events || []);
  renderResources(data.resources || []);
  aboutText.textContent =
    data.about_text ||
    "GolfMeadows is a resident-driven society in Panvel focused on safety, transparency, and quality of life for all families.";
  renderRecentRequests(data.recent_service_requests || []);
}

function renderAnnouncements(items) {
  if (!items.length) {
    setEmpty(announcementsGrid, "No announcements yet.");
    return;
  }
  announcementsGrid.innerHTML = "";
  items.forEach((item) => {
    const article = createEl("article", "card");
    article.appendChild(createEl("span", "badge", item.tag));
    article.appendChild(createEl("h3", "", item.title));
    article.appendChild(createEl("p", "", item.body));
    announcementsGrid.appendChild(article);
  });
}

function renderEvents(items) {
  if (!items.length) {
    setEmpty(eventsList, "No events posted yet.");
    return;
  }
  eventsList.innerHTML = "";
  items.forEach((item) => {
    const article = createEl("article", "timeline-item");
    article.appendChild(createEl("p", "timeline-date", item.event_date));
    const wrap = createEl("div");
    wrap.appendChild(createEl("h3", "", item.title));
    wrap.appendChild(createEl("p", "", item.details));
    article.appendChild(wrap);
    eventsList.appendChild(article);
  });
}

function renderResources(items) {
  if (!items.length) {
    setEmpty(resourcesGrid, "No resources uploaded yet.");
    return;
  }
  resourcesGrid.innerHTML = "";
  items.forEach((item) => {
    const article = createEl("article", "card");
    article.appendChild(createEl("h3", "", item.title));
    article.appendChild(createEl("p", "", item.description));
    const link = createEl("a", "text-link", "Open Resource");
    link.href = item.file_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    article.appendChild(link);
    resourcesGrid.appendChild(article);
  });
}

function renderRecentRequests(items) {
  if (!items.length) {
    recentServiceList.innerHTML = "";
    recentServiceList.appendChild(createEl("li", "", "No service requests yet."));
    return;
  }
  recentServiceList.innerHTML = "";
  items.forEach((item) => {
    const li = createEl("li");
    const strong = createEl("strong", "", item.ticket_ref);
    li.appendChild(strong);
    li.appendChild(
      document.createTextNode(` - ${item.category} (${item.priority}) - ${item.status}`)
    );
    recentServiceList.appendChild(li);
  });
}

prevBtn.addEventListener("click", () => {
  moveToSlide(currentSlide - 1);
  resetAutoplay();
});

nextBtn.addEventListener("click", () => {
  moveToSlide(currentSlide + 1);
  resetAutoplay();
});

dotsContainer.addEventListener("click", (event) => {
  const target = event.target.closest(".dot");
  if (!target) return;
  const index = Number(target.dataset.index);
  if (Number.isNaN(index)) return;
  moveToSlide(index);
  resetAutoplay();
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = uploadInput.files?.[0];
  if (!file) {
    uploadStatus.textContent = "Please choose an image.";
    return;
  }
  const form = new FormData();
  form.append("caption", uploadCaption.value.trim());
  form.append("image", file);
  uploadStatus.textContent = "Uploading and optimizing image...";

  try {
    await api.post("/api/v1/carousel/upload", form, true);
    uploadForm.reset();
    uploadStatus.textContent = "Photo uploaded and optimized successfully.";
    await loadCarousel();
  } catch (error) {
    uploadStatus.textContent = error.message;
  }
});

serviceForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(serviceForm).entries());
  try {
    const item = await api.post("/api/v1/service-requests", payload);
    serviceForm.reset();
    setText(serviceStatus, `Service request submitted. Reference: ${item.ticket_ref}`);
    const all = await api.get("/api/v1/service-requests");
    renderRecentRequests(all.slice(0, 6));
  } catch (error) {
    setText(serviceStatus, error.message);
  }
});

ticketLookupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const ticket = ticketLookupInput.value.trim();
  if (!ticket) return;
  try {
    const data = await api.get(`/api/v1/service-requests/${encodeURIComponent(ticket)}`);
    ticketLookupStatus.innerHTML = "";
    const wrap = createEl("span", "status-result");
    wrap.appendChild(createEl("strong", "", data.ticket_ref));
    wrap.appendChild(document.createTextNode(" is currently "));
    wrap.appendChild(createEl("strong", "", data.status));
    wrap.appendChild(document.createTextNode("."));
    ticketLookupStatus.appendChild(wrap);
  } catch {
    setText(ticketLookupStatus, "No service request found for that reference.");
  }
});

messageForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(messageForm).entries());
  try {
    await api.post("/api/v1/messages", payload);
    messageForm.reset();
    setText(messageStatus, "Message sent to society office.");
  } catch (error) {
    setText(messageStatus, error.message);
  }
});

document.getElementById("current-year").textContent = new Date().getFullYear();

Promise.all([loadCarousel(), loadBootstrap()]).catch((error) => {
  console.error(error);
});
