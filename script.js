const DEFAULT_SLIDES = [
  {
    src: "https://images.unsplash.com/photo-1519167758481-83f550bb49b3?auto=format&fit=crop&w=1800&q=80",
    caption: "Main entrance and landscaped drive",
  },
  {
    src: "https://images.unsplash.com/photo-1460317442991-0ec209397118?auto=format&fit=crop&w=1800&q=80",
    caption: "Clubhouse gathering and community moments",
  },
  {
    src: "https://images.unsplash.com/photo-1505691938895-1758d7feb511?auto=format&fit=crop&w=1800&q=80",
    caption: "Green spaces and family leisure zones",
  },
];

const CAROUSEL_STORAGE_KEY = "golfmeadows-carousel-custom";
const COMPLAINTS_STORAGE_KEY = "golfmeadows-complaints";

const track = document.getElementById("carousel-track");
const dotsContainer = document.getElementById("carousel-dots");
const prevBtn = document.getElementById("prev-btn");
const nextBtn = document.getElementById("next-btn");
const uploadForm = document.getElementById("upload-form");
const uploadInput = document.getElementById("carousel-upload");
const uploadStatus = document.getElementById("upload-status");
const clearCustomBtn = document.getElementById("clear-custom");

const complaintForm = document.getElementById("complaint-form");
const complaintList = document.getElementById("complaint-list");
const complaintStatus = document.getElementById("complaint-status");

let currentSlide = 0;
let autoplayTimer = null;

function isSafeImageSrc(value) {
  return (
    typeof value === "string" &&
    (value.startsWith("https://") || value.startsWith("data:image/"))
  );
}

function readStoredCustomSlides() {
  try {
    const raw = localStorage.getItem(CAROUSEL_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => isSafeImageSrc(item?.src))
      .map((item) => ({
        src: item.src,
        caption: typeof item?.caption === "string" ? item.caption : "GolfMeadows",
      }));
  } catch {
    return [];
  }
}

function getSlides() {
  return [...DEFAULT_SLIDES, ...readStoredCustomSlides()];
}

function storeCustomSlides(customSlides) {
  localStorage.setItem(CAROUSEL_STORAGE_KEY, JSON.stringify(customSlides));
}

function renderCarousel() {
  const slides = getSlides();
  track.innerHTML = "";
  slides.forEach((slide) => {
    const figure = document.createElement("figure");
    figure.className = "slide";

    const image = document.createElement("img");
    image.src = slide.src;
    image.alt = slide.caption || "GolfMeadows photo";
    figure.appendChild(image);

    const caption = document.createElement("figcaption");
    caption.className = "slide-caption";
    caption.textContent = slide.caption || "GolfMeadows";
    figure.appendChild(caption);

    track.appendChild(figure);
  });

  dotsContainer.innerHTML = "";
  slides.forEach((_, index) => {
    const dot = document.createElement("button");
    dot.className = `dot ${index === currentSlide ? "active" : ""}`;
    dot.setAttribute("aria-label", `Go to slide ${index + 1}`);
    dot.dataset.index = String(index);
    dotsContainer.appendChild(dot);
  });

  if (currentSlide >= slides.length) {
    currentSlide = 0;
  }
  moveToSlide(currentSlide);
}

function moveToSlide(index) {
  const slides = getSlides();
  if (!slides.length) return;
  currentSlide = (index + slides.length) % slides.length;
  track.style.transform = `translateX(-${currentSlide * 100}%)`;

  const dots = [...dotsContainer.querySelectorAll(".dot")];
  dots.forEach((dot, dotIndex) => {
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

function resetCarouselAutoPlay() {
  stopAutoplay();
  startAutoplay();
}

prevBtn.addEventListener("click", () => {
  moveToSlide(currentSlide - 1);
  resetCarouselAutoPlay();
});

nextBtn.addEventListener("click", () => {
  moveToSlide(currentSlide + 1);
  resetCarouselAutoPlay();
});

dotsContainer.addEventListener("click", (event) => {
  const target = event.target.closest(".dot");
  if (!target) return;
  const index = Number(target.dataset.index);
  if (Number.isNaN(index)) return;
  moveToSlide(index);
  resetCarouselAutoPlay();
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const files = [...uploadInput.files];
  if (!files.length) {
    uploadStatus.textContent = "Please select at least one image.";
    return;
  }

  const oversized = files.find((file) => file.size > 2.5 * 1024 * 1024);
  if (oversized) {
    uploadStatus.textContent = `File "${oversized.name}" is too large. Keep each image under 2.5 MB.`;
    return;
  }

  try {
    const customSlides = readStoredCustomSlides();
    const encodedFiles = await Promise.all(
      files.map(
        (file) =>
          new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () =>
              resolve({
                src: reader.result,
                caption: file.name.replace(/\.[^.]+$/, ""),
              });
            reader.onerror = () => reject(new Error(`Failed to read ${file.name}`));
            reader.readAsDataURL(file);
          })
      )
    );

    storeCustomSlides([...customSlides, ...encodedFiles]);
    uploadStatus.textContent = `${encodedFiles.length} photo(s) added to the carousel.`;
    uploadInput.value = "";
    renderCarousel();
    startAutoplay();
  } catch {
    uploadStatus.textContent = "Could not upload files. Please try again.";
  }
});

clearCustomBtn.addEventListener("click", () => {
  localStorage.removeItem(CAROUSEL_STORAGE_KEY);
  uploadStatus.textContent = "Uploaded photos were cleared from this browser.";
  currentSlide = 0;
  renderCarousel();
  startAutoplay();
});

function generateTicketRef() {
  const random = Math.floor(Math.random() * 900 + 100);
  return `GM-${new Date().getFullYear()}-${random}`;
}

function readComplaints() {
  try {
    const raw = localStorage.getItem(COMPLAINTS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed;
  } catch {
    return [];
  }
}

function storeComplaints(data) {
  localStorage.setItem(COMPLAINTS_STORAGE_KEY, JSON.stringify(data));
}

function renderComplaints() {
  const complaints = readComplaints();
  if (!complaints.length) {
    complaintList.innerHTML = "<li>No complaint submissions yet.</li>";
    return;
  }

  complaintList.innerHTML = "";
  complaints
    .slice(-6)
    .reverse()
    .forEach((item) => {
      const listItem = document.createElement("li");
      const ticket = document.createElement("strong");
      ticket.textContent = `${item.ticket || "GM-REF"}`;
      listItem.appendChild(ticket);

      const details = document.createTextNode(
        ` - ${item.issueType || "Issue"} (${item.priority || "Priority"}) by ${item.residentName || "Resident"}`
      );
      listItem.appendChild(details);
      complaintList.appendChild(listItem);
    });
}

complaintForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const formData = new FormData(complaintForm);
  const payload = Object.fromEntries(formData.entries());
  const ticket = generateTicketRef();

  const complaints = readComplaints();
  complaints.push({ ...payload, ticket, createdAt: new Date().toISOString() });
  storeComplaints(complaints);
  renderComplaints();
  complaintForm.reset();
  complaintStatus.textContent = `Complaint submitted. Reference: ${ticket}`;
});

document.getElementById("current-year").textContent = new Date().getFullYear();

renderCarousel();
renderComplaints();
startAutoplay();
