function formatCurrencyInr(value) {
  const amount = Number.parseFloat(value || "0");
  if (!Number.isFinite(amount)) return "INR 0.00";
  return `INR ${amount.toFixed(2)}`;
}

function setupAmenitiesBooking() {
  const bookingPanel = document.getElementById("booking-panel");
  if (!bookingPanel) return;

  const amenityCards = Array.from(document.querySelectorAll(".amenity-select-card"));
  const amenityIdInput = document.getElementById("booking-amenity-id");
  const amenityTitle = document.getElementById("booking-amenity-title");
  const bookingDateInput = document.getElementById("booking_date");
  const startTimeInput = document.getElementById("start_time");
  const endTimeInput = document.getElementById("end_time");
  const summary = document.getElementById("booking-summary");
  const costDisplay = document.getElementById("booking-cost-display");
  const form = document.getElementById("booking-form");
  const errorBox = document.getElementById("booking-form-error");
  const successBox = document.getElementById("booking-form-success");
  const calendarEl = document.getElementById("amenity-calendar");
  const selectedAmenityAvailableFrom = document.getElementById("selected-amenity-available-from");
  const selectedAmenityAvailableTo = document.getElementById("selected-amenity-available-to");
  const selectedAmenityWindowHint = document.getElementById("selected-amenity-window-hint");

  if (!amenityIdInput || !amenityTitle || !bookingDateInput || !startTimeInput || !endTimeInput || !summary || !costDisplay || !form || !calendarEl) {
    return;
  }

  let selectedAmenityId = "";
  let selectedAmenityName = "";
  let selectedAmenityCost = 0;
  let selectedAmenityAvailableFromValue = "06:00";
  let selectedAmenityAvailableToValue = "22:00";
  let calendar = null;
  const todayIso = new Date().toISOString().slice(0, 10);
  bookingDateInput.min = todayIso;

  const applyCalendarMobileLayout = () => {
    if (!calendarEl) return;
    const compact = window.innerWidth < 768;
    const toolbar = compact
      ? {
          left: "prev,next",
          center: "title",
          right: "dayGridMonth,timeGridWeek",
        }
      : {
          left: "prev,next today",
          center: "title",
          right: "dayGridMonth,timeGridWeek,timeGridDay",
        };
    if (calendar) {
      calendar.setOption("headerToolbar", toolbar);
    }
  };

  const resetMessages = () => {
    if (errorBox) {
      errorBox.classList.add("hidden");
      errorBox.textContent = "";
    }
    if (successBox) {
      successBox.classList.add("hidden");
      successBox.textContent = "";
    }
  };

  const updateSummary = () => {
    const chosenDate = bookingDateInput.value || "date";
    const chosenStart = startTimeInput.value || "start";
    const chosenEnd = endTimeInput.value || "end";
    const costText = selectedAmenityCost > 0 ? formatCurrencyInr(selectedAmenityCost) : "Free";
    summary.textContent = `${selectedAmenityName || "Amenity"} on ${chosenDate} from ${chosenStart} to ${chosenEnd}. Total: ${costText}`;
  };

  const setTimeOptionAvailability = () => {
    const selectedDate = bookingDateInput.value;
    const now = new Date();
    const nowHm = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    const disableBeforeNow = selectedDate === todayIso;

    [startTimeInput, endTimeInput].forEach((selectEl) => {
      Array.from(selectEl.options).forEach((option) => {
        const value = option.value;
        if (!value) {
          option.disabled = false;
          return;
        }
        const outsideWindow =
          value < selectedAmenityAvailableFromValue || value > selectedAmenityAvailableToValue;
        const pastTime = disableBeforeNow && value <= nowHm;
        option.disabled = outsideWindow || pastTime;
      });
    });
  };

  const updateTimeWindowUi = () => {
    if (selectedAmenityAvailableFrom) {
      selectedAmenityAvailableFrom.value = selectedAmenityAvailableFromValue;
    }
    if (selectedAmenityAvailableTo) {
      selectedAmenityAvailableTo.value = selectedAmenityAvailableToValue;
    }
    if (selectedAmenityWindowHint) {
      selectedAmenityWindowHint.textContent = `Allowed time window: ${selectedAmenityAvailableFromValue} to ${selectedAmenityAvailableToValue}.`;
    }
    setTimeOptionAvailability();
  };

  const renderCalendar = async (amenityId) => {
    if (!window.FullCalendar) return;
    if (calendar) {
      calendar.destroy();
      calendar = null;
    }
    const response = await fetch(`/api/amenities/${amenityId}/bookings`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not load booking slots.");
    }
    const compact = window.innerWidth < 768;
    const headerToolbar = compact
      ? {
          left: "prev,next",
          center: "title",
          right: "dayGridMonth,timeGridWeek",
        }
      : {
          left: "prev,next today",
          center: "title",
          right: "dayGridMonth,timeGridWeek,timeGridDay",
        };
    calendar = new window.FullCalendar.Calendar(calendarEl, {
      initialView: "dayGridMonth",
      height: "auto",
      headerToolbar,
      validRange: { start: todayIso },
      dayCellClassNames(info) {
        if (info.dateStr < todayIso) {
          return ["fc-day-past-disabled"];
        }
        return [];
      },
      events: payload.events || [],
      eventColor: "#0ea5e9",
      selectable: true,
      select(info) {
        bookingDateInput.value = info.startStr.slice(0, 10);
        setTimeOptionAvailability();
        updateSummary();
      },
    });
    calendar.render();
  };

  const selectAmenity = async (card) => {
    selectedAmenityId = card.dataset.amenityId || "";
    selectedAmenityName = card.dataset.amenityName || "";
    selectedAmenityCost = Number.parseFloat(card.dataset.amenityCost || "0");
    selectedAmenityAvailableFromValue = card.dataset.availableFrom || card.dataset.amenityAvailableFrom || "06:00";
    selectedAmenityAvailableToValue = card.dataset.availableTo || card.dataset.amenityAvailableTo || "22:00";

    amenityCards.forEach((entry) => entry.classList.remove("ring-4", "ring-emerald-300"));
    card.classList.add("ring-4", "ring-emerald-300");

    amenityIdInput.value = selectedAmenityId;
    amenityTitle.textContent = `${selectedAmenityName} - Amenity Booking Calendar`;
    costDisplay.textContent = selectedAmenityCost > 0 ? `Estimated Cost: ${formatCurrencyInr(selectedAmenityCost)}` : "Estimated Cost: Free";
    bookingPanel.classList.remove("hidden");
    bookingPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    updateSummary();
    updateTimeWindowUi();
    resetMessages();

    await renderCalendar(selectedAmenityId);
  };

  amenityCards.forEach((card) => {
    card.addEventListener("click", () => {
      selectAmenity(card).catch((error) => {
        if (errorBox) {
          errorBox.classList.remove("hidden");
          errorBox.textContent = error.message || "Unable to load calendar.";
        }
      });
    });
  });

  bookingDateInput.addEventListener("change", () => {
    setTimeOptionAvailability();
    updateSummary();
  });
  startTimeInput.addEventListener("change", updateSummary);
  endTimeInput.addEventListener("change", updateSummary);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    resetMessages();

    const payload = {
      amenity_id: amenityIdInput.value,
      resident_name: (document.getElementById("resident_name") || {}).value || "",
      resident_email: (document.getElementById("resident_email") || {}).value || "",
      booking_date: bookingDateInput.value,
      start_time: startTimeInput.value,
      end_time: endTimeInput.value,
    };

    const response = await fetch("/api/amenities/book", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      if (errorBox) {
        errorBox.classList.remove("hidden");
        errorBox.textContent = data.error || "Booking failed.";
      }
      return;
    }

    if (successBox) {
      successBox.classList.remove("hidden");
      const cost = Number.parseFloat(data.cost || "0");
      successBox.textContent = `Booking confirmed for ${data.amenity} on ${data.booking_date} from ${data.start_time} to ${data.end_time}. Total cost: ${cost > 0 ? formatCurrencyInr(cost) : "Free"}.`;
    }
    await renderCalendar(payload.amenity_id);
    updateSummary();
  });

  const preselectedCard = amenityCards.find((card) => card.dataset.preselected === "true");
  if (preselectedCard) {
    selectAmenity(preselectedCard).catch(() => {});
  }

  const styleEl = document.createElement("style");
  styleEl.textContent = ".fc-day-past-disabled { background-color: #f1f5f9 !important; color: #94a3b8 !important; }";
  document.head.appendChild(styleEl);

  window.addEventListener("resize", applyCalendarMobileLayout);
}

document.addEventListener("DOMContentLoaded", setupAmenitiesBooking);
