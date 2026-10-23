const unlockForm = document.getElementById("offlineUnlock");
if (unlockForm) {
  const message = document.getElementById("offlineMessage");
  const dataPanel = document.getElementById("offlineData");
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
  const table = (headers, rows) => {
    if (!rows.length) return "<p>Aucune donnée synchronisée dans cette rubrique.</p>";
    return `<table><thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  };

  unlockForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const username = document.getElementById("offlineUsername").value.trim();
    const passwordInput = document.getElementById("offlinePassword");
    const password = passwordInput.value;
    message.textContent = "Déchiffrement des données…";
    dataPanel.hidden = true;
    try {
      const record = await window.NdnOfflineStore.get(username);
      if (!record) throw new Error("Aucune copie n’existe pour cet identifiant. Reconnectez-vous au serveur, puis réessayez.");
      const unlocked = await window.NdnOfflineStore.unlock(record, password);
      const { snapshot } = unlocked;
      const enrollmentMap = new Map(snapshot.students.map((student) => [student.enrollment_id, student]));
      const classRows = snapshot.classes.map((schoolClass) => [
        schoolClass.name, schoolClass.level, schoolClass.track,
        snapshot.students.filter((student) => student.class_id === schoolClass.id).length,
      ]);
      document.getElementById("offlineMeta").textContent =
        `Compte : ${snapshot.username} · Année : ${snapshot.year || "non configurée"} · Copie locale du ${new Date(unlocked.savedAt).toLocaleString("fr-FR")}`;
      document.getElementById("offlineClasses").innerHTML =
        table(["Classe", "Niveau", "Parcours", "Élèves"], classRows);
      document.getElementById("offlineSubjects").innerHTML =
        table(["Classe", "Matière", "Coefficient"], snapshot.subjects.map((subject) => [
          subject.class_name, subject.name, subject.coefficient,
        ]));
      const gradeRows = snapshot.evaluations.flatMap((evaluation) => evaluation.grades.map((grade) => {
        const student = enrollmentMap.get(grade.enrollment_id);
        return [
          evaluation.class_name,
          evaluation.subject,
          evaluation.title,
          evaluation.period,
          student ? `${student.name} (${student.matricule})` : "Élève non disponible",
          grade.status === "Note" && grade.score !== null
            ? `${grade.score}/${evaluation.max_score}` : grade.status,
          evaluation.status,
        ];
      }));
      document.getElementById("offlineGrades").innerHTML =
        table(["Classe", "Matière", "Évaluation", "Période", "Élève", "Résultat", "État"], gradeRows);
      document.getElementById("deleteOfflineCopy").onclick = async () => {
        try {
          await window.NdnOfflineStore.remove(username);
          dataPanel.hidden = true;
          message.textContent = "La copie chiffrée a été supprimée de cet appareil.";
        } catch (error) {
          message.textContent = error.message || "Impossible de supprimer la copie locale.";
        }
      };
      dataPanel.hidden = false;
      message.textContent = "";
      passwordInput.value = "";
    } catch (error) {
      message.textContent = error.name === "OperationError"
        ? "Mot de passe incorrect ou copie locale endommagée."
        : error.message || "Impossible de déverrouiller les données.";
    }
  });
}
