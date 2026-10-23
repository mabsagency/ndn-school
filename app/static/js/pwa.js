let installPrompt = null;
const installButtons = document.querySelectorAll("[data-install-app]");
const installHint = document.querySelector("[data-install-hint]");
const isIos = /iphone|ipad|ipod/i.test(window.navigator.userAgent);
const isStandalone = window.matchMedia("(display-mode: standalone)").matches
  || window.navigator.standalone === true;

const appShell = document.querySelector(".app-shell");
const offlineIndicator = document.querySelector("[data-offline-indicator]");
const loginForm = document.getElementById("loginForm");

if (appShell || loginForm) {
  let redirectingOffline = false;
  let healthCheckInProgress = false;
  const goOffline = () => {
    if (redirectingOffline) return;
    redirectingOffline = true;
    window.location.replace("/static/offline.html");
  };
  const checkServer = async () => {
    if (healthCheckInProgress || redirectingOffline) return;
    if (!navigator.onLine) {
      goOffline();
      return;
    }
    healthCheckInProgress = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 4000);
    try {
      const response = await fetch("/health", {
        cache: "no-store",
        credentials: "same-origin",
        signal: controller.signal,
      });
      if (!response.ok) goOffline();
    } catch {
      goOffline();
    } finally {
      window.clearTimeout(timeout);
      healthCheckInProgress = false;
    }
  };

  window.addEventListener("offline", goOffline);
  window.addEventListener("online", checkServer);
  window.addEventListener("load", checkServer, { once: true });
  window.setInterval(() => {
    if (document.visibilityState === "visible") checkServer();
  }, 15000);
}

if (appShell && offlineIndicator && window.NdnOfflineStore) {
  window.NdnOfflineStore.get(appShell.dataset.offlineUser).then((record) => {
    offlineIndicator.textContent = record
      ? `Copie hors ligne · ${new Date(record.savedAt).toLocaleDateString("fr-FR")}`
      : "Copie hors ligne à préparer";
    offlineIndicator.title = record
      ? `Dernière copie chiffrée : ${new Date(record.savedAt).toLocaleString("fr-FR")}. Reconnectez-vous pour l’actualiser.`
      : "Connectez-vous lorsque le serveur est accessible pour préparer votre copie hors ligne.";
  }).catch((error) => {
    console.error("Impossible de vérifier la copie hors ligne.", error);
    offlineIndicator.textContent = "État hors ligne indisponible";
  });
}

if ("serviceWorker" in navigator && window.isSecureContext) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js").catch((error) => {
      console.error("Impossible d’activer le mode hors connexion.", error);
    });
  });
}

if (loginForm) {
  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = loginForm.querySelector('[type="submit"]');
    const status = document.getElementById("offlineSyncStatus");
    let password = loginForm.elements.password.value;
    let authenticated = false;
    submitButton.disabled = true;
    status.textContent = "Connexion…";
    try {
      const response = await fetch(loginForm.action || "/login", {
        method: "POST",
        body: new FormData(loginForm),
        headers: { "X-NDN-Offline-Sync": "1" },
        credentials: "same-origin",
      });
      const result = await response.json();
      if (!response.ok || !result.authenticated) {
        status.textContent = result.message || "La connexion a échoué.";
        submitButton.disabled = false;
        return;
      }
      authenticated = true;
      status.textContent = "Connexion établie. Chiffrement de la copie hors ligne…";
      const snapshotResponse = await fetch("/api/offline-snapshot", {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!snapshotResponse.ok) {
        throw new Error("Le serveur n’a pas pu préparer les données hors ligne.");
      }
      const snapshot = await snapshotResponse.json();
      await window.NdnOfflineStore.save(snapshot, password);
      password = "";
      status.textContent = "Copie hors ligne chiffrée et mise à jour.";
      window.location.assign("/");
    } catch (error) {
      console.error("La synchronisation chiffrée hors ligne a échoué.", error);
      password = "";
      if (authenticated) {
        status.textContent = "Connexion réussie, mais la copie hors ligne n’a pas pu être mise à jour.";
        window.setTimeout(() => window.location.assign("/"), 1200);
        return;
      }
      status.textContent = "Connexion ou copie hors ligne indisponible. Réessayez lorsque le serveur est accessible.";
      submitButton.disabled = false;
    }
  });
}

if (!isStandalone) {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installPrompt = event;
    installButtons.forEach((button) => {
      button.hidden = false;
      button.textContent = "Installer l’application";
    });
  });

  if (isIos) {
    installButtons.forEach((button) => {
      button.hidden = false;
      button.textContent = "Ajouter à l’écran d’accueil";
    });
    if (installHint) installHint.hidden = false;
  }
}

installButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    if (!installPrompt) {
      if (isIos && installHint) {
        installHint.hidden = false;
        installHint.textContent = "Dans Safari, touchez Partager puis « Sur l’écran d’accueil ».";
      }
      return;
    }

    await installPrompt.prompt();
    await installPrompt.userChoice;
    installPrompt = null;
    installButtons.forEach((installButton) => {
      installButton.hidden = true;
    });
  });
});

window.addEventListener("appinstalled", () => {
  installPrompt = null;
  installButtons.forEach((button) => {
    button.hidden = true;
  });
});
