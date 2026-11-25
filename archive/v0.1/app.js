(() => {
  const asOf = document.getElementById("asOf");
  if (asOf) {
    const d = new Date();
    const iso = d.toISOString().slice(0, 10);
    asOf.textContent = `обновлено ${iso}`;
  }

  const buttons = [...document.querySelectorAll(".rail-item[data-panel]")];
  const panels = [...document.querySelectorAll(".panel")];

  function show(panelId) {
    panels.forEach((panel) => {
      const active = panel.id === `panel-${panelId}`;
      panel.classList.toggle("is-active", active);
      panel.hidden = !active;
    });
    buttons.forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.panel === panelId);
    });
  }

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => show(btn.dataset.panel));
  });
})();
