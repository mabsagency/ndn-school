const menuButton = document.getElementById("menuButton");
const sidebar = document.getElementById("sidebar");
if (menuButton && sidebar) {
  const backdrop = document.getElementById("mobileNavBackdrop");
  const closeMenu = () => {
    sidebar.classList.remove("open");
    document.body.classList.remove("mobile-nav-open");
    menuButton.setAttribute("aria-expanded", "false");
    menuButton.setAttribute("aria-label", "Ouvrir le menu");
    if (backdrop) backdrop.hidden = true;
  };
  const openMenu = () => {
    sidebar.classList.add("open");
    document.body.classList.add("mobile-nav-open");
    menuButton.setAttribute("aria-expanded", "true");
    menuButton.setAttribute("aria-label", "Fermer le menu");
    if (backdrop) backdrop.hidden = false;
  };
  menuButton.addEventListener("click", () => {
    if (sidebar.classList.contains("open")) {
      closeMenu();
    } else {
      openMenu();
      sidebar.querySelector(".nav-link.active")?.focus();
    }
  });
  backdrop?.addEventListener("click", closeMenu);
  sidebar.querySelectorAll(".nav-link").forEach((link) => {
    link.addEventListener("click", closeMenu);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && sidebar.classList.contains("open")) {
      closeMenu();
      menuButton.focus();
    }
  });
  document.addEventListener("click", (event) => {
    if (!sidebar.contains(event.target) && !menuButton.contains(event.target)) {
      if (sidebar.classList.contains("open")) {
        closeMenu();
      }
    }
  });
  window.matchMedia("(min-width: 801px)").addEventListener("change", (event) => {
    if (event.matches) {
      closeMenu();
    }
  });
}

document.querySelectorAll(".alert-close").forEach((button) => {
  button.addEventListener("click", () => button.closest(".alert").remove());
});

document.querySelectorAll("[data-open]").forEach((button) => {
  button.addEventListener("click", () => document.getElementById(button.dataset.open).showModal());
});
document.querySelectorAll("[data-close]").forEach((button) => {
  button.addEventListener("click", () => button.closest("dialog").close());
});
document.querySelectorAll("dialog").forEach((dialog) => {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
});

const passwordToggle = document.getElementById("togglePassword");
if (passwordToggle) {
  passwordToggle.addEventListener("click", () => {
    const password = document.getElementById("password");
    const visible = password.type === "password";
    password.type = visible ? "text" : "password";
    passwordToggle.setAttribute("aria-label", visible ? "Masquer le mot de passe" : "Afficher le mot de passe");
    passwordToggle.setAttribute("aria-pressed", String(visible));
    passwordToggle.title = visible ? "Masquer le mot de passe" : "Afficher le mot de passe";
  });
}

const logoInput = document.getElementById("schoolLogo");
const logoPreview = document.getElementById("logoPreview");
const logoFileName = document.getElementById("logoFileName");
if (logoInput && logoPreview && logoFileName) {
  let previewUrl = null;
  logoInput.addEventListener("change", () => {
    const file = logoInput.files?.[0];
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    if (!file) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      logoInput.setCustomValidity("Choisissez une image PNG, JPG ou WEBP.");
      logoInput.reportValidity();
      logoInput.value = "";
      logoFileName.textContent = "Format non pris en charge. Choisissez PNG, JPG ou WEBP.";
      return;
    }
    logoInput.setCustomValidity("");
    previewUrl = URL.createObjectURL(file);
    logoPreview.src = previewUrl;
    logoFileName.textContent = file.name;
  });
  window.addEventListener("pagehide", () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, { once: true });
}

const studentSearch = document.getElementById("studentSearch");
if (studentSearch) {
  studentSearch.addEventListener("input", () => {
    const query = studentSearch.value.trim().toLocaleLowerCase("fr");
    document.querySelectorAll(".grade-row").forEach((row) => {
      row.hidden = !row.textContent.toLocaleLowerCase("fr").includes(query);
    });
  });
}

const evaluationClass = document.getElementById("evaluationClass");
if (evaluationClass) {
  const evaluationSubject = document.getElementById("evaluationSubject");
  const evaluationTeacher = document.getElementById("evaluationTeacher");
  const updateEvaluationAssignment = () => {
    const option = evaluationClass.selectedOptions[0];
    evaluationSubject.value = option?.dataset.subject || "";
    if (!evaluationTeacher) return;
    const teacherIds = (option?.dataset.teachers || "").split(",").filter(Boolean);
    evaluationTeacher.value = "";
    [...evaluationTeacher.options].forEach((teacherOption) => {
      teacherOption.disabled = teacherOption.value !== "" && !teacherIds.includes(teacherOption.value);
    });
    if (teacherIds.length === 1) evaluationTeacher.value = teacherIds[0];
  };
  evaluationClass.addEventListener("change", updateEvaluationAssignment);
  updateEvaluationAssignment();
}

document.querySelectorAll(".score-input").forEach((input) => {
  input.addEventListener("change", () => {
    const max = Number(input.max);
    const score = Number(input.value);
    if (input.value !== "" && (score < 0 || score > max)) {
      input.setCustomValidity(`Entrez une note comprise entre 0 et ${max}.`);
      input.reportValidity();
    } else {
      input.setCustomValidity("");
    }
  });
});
