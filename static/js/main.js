async function fetchEmailLink(category, subject, body) {
  const params = new URLSearchParams({
    category,
    subject,
    body,
  });
  const response = await fetch(`/api/email-links?${params.toString()}`);
  if (!response.ok) {
    throw new Error("Recipient email is not configured for this function.");
  }
  return response.json();
}

function attachEmailActions() {
  const buttons = document.querySelectorAll("[data-email-category]");
  buttons.forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const category = button.dataset.emailCategory || "";
      const subject = button.dataset.emailSubject || "Society Portal Request";
      const body = button.dataset.emailBody || "Hello,";
      try {
        const payload = await fetchEmailLink(category, subject, body);
        if (button.dataset.emailMode === "gmail") {
          window.open(payload.gmail, "_blank", "noopener");
        } else {
          window.location.href = payload.mailto;
        }
      } catch (error) {
        alert(error.message);
      }
    });
  });
}

function attachMcNoticeDismissals() {
  const banners = document.querySelectorAll("[data-mc-notice-id]");
  if (!banners.length) return;
  const storageKey = "dismissed_mc_notice_ids";
  let dismissed = [];
  try {
    dismissed = JSON.parse(localStorage.getItem(storageKey) || "[]");
    if (!Array.isArray(dismissed)) dismissed = [];
  } catch {
    dismissed = [];
  }
  const dismissedSet = new Set(dismissed.map((value) => Number.parseInt(value, 10)).filter(Number.isFinite));

  banners.forEach((banner) => {
    const noticeId = Number.parseInt(banner.dataset.mcNoticeId || "", 10);
    if (!Number.isFinite(noticeId)) return;

    if (dismissedSet.has(noticeId)) {
      banner.classList.add("hidden");
      return;
    }

    const closeButton = banner.querySelector("[data-mc-dismiss]");
    if (!closeButton) return;
    closeButton.addEventListener("click", () => {
      banner.classList.add("hidden");
      dismissedSet.add(noticeId);
      localStorage.setItem(storageKey, JSON.stringify(Array.from(dismissedSet)));
    });
  });
}

function startCarousel() {
  const track = document.getElementById("carousel-track");
  if (!track) return;
  const slides = Array.from(track.querySelectorAll("[data-carousel-slide]"));
  if (!slides.length) return;
  let index = 0;
  const dots = document.querySelectorAll(".carousel-dot");

  const activateDot = (activeIndex) => {
    dots.forEach((dot, dotIndex) => {
      const active = dotIndex === activeIndex;
      dot.classList.toggle("bg-white", active);
      dot.classList.toggle("bg-white/50", !active);
    });
  };

  activateDot(0);
  dots.forEach((dot) => {
    dot.addEventListener("click", () => {
      index = Number.parseInt(dot.dataset.index || "0", 10);
      if (Number.isNaN(index)) index = 0;
      track.style.transform = `translateX(-${index * 100}%)`;
      activateDot(index);
    });
  });

  setInterval(() => {
    index = (index + 1) % slides.length;
    track.style.transform = `translateX(-${index * 100}%)`;
    activateDot(index);
  }, 4500);
}

document.addEventListener("DOMContentLoaded", () => {
  attachEmailActions();
  attachMcNoticeDismissals();
  startCarousel();
});
