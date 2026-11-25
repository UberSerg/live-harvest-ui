(() => {
  const data = window.LH_DATA;
  const titleEl = document.getElementById("pageTitle");
  const asOf = document.getElementById("asOfChip");
  const views = {
    overview: document.getElementById("view-overview"),
    personality: document.getElementById("view-personality"),
    stub: document.getElementById("view-stub"),
  };
  const titles = {
    overview: "Обзор",
    personality: "Личность",
    knowledge: "База знаний",
    goals: "Цели",
    projects: "Проекты",
    finance: "Финансы",
    health: "Здоровье",
    plan: "Планирование",
    journal: "Дневник",
    retro: "Ретроспектива",
    harvester: "Harvester",
    advisor: "Advisor",
    razvivator: "Развиватор",
  };

  asOf.textContent = `as of ${data.meta.asOf}`;

  function epList(items) {
    return `<ul class="ep-list">${items
      .map((i) => `<li data-ep="${i.ep}">${escapeHtml(i.text)}</li>`)
      .join("")}</ul>`;
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function stateCell(label, value) {
    if (value == null || value === "") {
      return `<div class="state-cell"><div class="state-k">${label}</div><div class="state-empty">нет данных</div></div>`;
    }
    return `<div class="state-cell has-data"><div class="state-k">${label}</div><div class="state-v">${escapeHtml(value)}</div></div>`;
  }

  function renderOverview() {
    const p = data.profile;
    const s = data.state;
    const mq = data.mainQuest;
    const bal = data.balance
      .map((b) => {
        const fillClass = b.status === "empty" ? "empty" : b.status === "watch" ? "watch" : "active";
        const trackClass = b.status === "empty" ? "balance-track is-empty" : "balance-track";
        return `<div class="balance-row">
          <div class="balance-label">${escapeHtml(b.label)}</div>
          <div>
            <div class="${trackClass}"><div class="balance-fill ${fillClass}"></div></div>
            <div class="balance-note">${escapeHtml(b.note)}</div>
          </div>
        </div>`;
      })
      .join("");

    const sides = data.sideQuests
      .map(
        (q) => `<div class="row"><span class="row-dot"></span><div>
        <div class="row-title">${escapeHtml(q.title)}</div>
        <div class="row-meta">${escapeHtml(q.meta)}</div></div></div>`
      )
      .join("");

    const raz = data.razvivator.items
      .map(
        (i) => `<div class="raz-item"><div class="raz-type">${escapeHtml(i.type)}</div>
        <div class="raz-text">${escapeHtml(i.text)}</div></div>`
      )
      .join("");

    const waves = data.waves.map((w) => `<span class="wave-tag">${escapeHtml(w)}</span>`).join("");

    const achievements = data.progress.achievements
      .map(
        (a) => `<div class="progress-line"><span>${escapeHtml(a.title)}</span><span>${escapeHtml(a.when)}</span></div>`
      )
      .join("");
    const measurable = data.progress.measurable
      .map(
        (m) => `<div class="progress-line"><span>${escapeHtml(m.label)}</span><span>${escapeHtml(m.value)}</span></div>`
      )
      .join("");

    const recent = data.recent
      .map(
        (r) => `<div class="row"><span class="row-dot" style="background:var(--accent)"></span><div>
        <div class="row-title">${escapeHtml(r.what)}</div>
        <div class="row-meta">${escapeHtml(r.kind)}</div></div></div>`
      )
      .join("");

    views.overview.innerHTML = `
      <div class="dash">
        <article class="panel span-5">
          <div class="panel-h">
            <h2 class="panel-title">Мой профиль</h2>
            <button class="panel-link" type="button" data-go="personality">открыть портрет</button>
          </div>
          <h3 class="profile-name">${escapeHtml(p.name)}</h3>
          <p class="profile-role">${escapeHtml(p.role)}</p>
          <p class="profile-stage">${escapeHtml(p.stage)}</p>
          <div class="values">${p.values.map((v) => `<span class="pill">${escapeHtml(v)}</span>`).join("")}</div>
          <p class="motto">«${escapeHtml(p.motto)}»</p>
        </article>

        <article class="panel span-7">
          <div class="panel-h">
            <h2 class="panel-title">Текущее состояние</h2>
            <span class="chip">пусто = нет среза</span>
          </div>
          <div class="state-grid">
            ${stateCell("настроение", s.mood)}
            ${stateCell("энергия", s.energy)}
            ${stateCell("фокус", s.focus)}
            ${stateCell("волна вдохновения", s.wave)}
          </div>
          <div style="margin-top:10px">${stateCell("последняя запись дневника", s.lastJournal)}</div>
        </article>

        <article class="panel span-7 quest-main">
          <div class="quest-badge">main quest</div>
          <h3 class="quest-title">${escapeHtml(mq.title)}</h3>
          <p class="quest-detail">${escapeHtml(mq.detail)}</p>
          <p class="quest-check">checkpoint · ${escapeHtml(mq.checkpoint)}</p>
        </article>

        <article class="panel span-5">
          <div class="panel-h"><h2 class="panel-title">Побочные квесты</h2></div>
          <div class="list-rows">${sides}</div>
        </article>

        <article class="panel span-6">
          <div class="panel-h">
            <h2 class="panel-title">Жизненный баланс</h2>
            <span class="chip">без оценок личности</span>
          </div>
          <div class="balance">${bal}</div>
        </article>

        <article class="panel span-6">
          <div class="panel-h">
            <h2 class="panel-title">Развиватор</h2>
            ${data.razvivator.demo ? '<span class="chip chip-demo">демо</span>' : ""}
          </div>
          ${raz}
        </article>

        <article class="panel span-5">
          <div class="panel-h"><h2 class="panel-title">Волны вдохновения</h2></div>
          <div class="wave-cloud">${waves}</div>
        </article>

        <article class="panel span-7">
          <div class="panel-h"><h2 class="panel-title">Прогресс</h2></div>
          <div class="progress-block">
            <div>
              <div class="state-k" style="margin-bottom:8px">достижения</div>
              ${achievements}
            </div>
            <div>
              <div class="state-k" style="margin-bottom:8px">измеримое</div>
              ${measurable}
            </div>
            <div class="state-empty">привычки / итог недели — нет данных</div>
          </div>
        </article>

        <article class="panel span-12">
          <div class="panel-h"><h2 class="panel-title">Последние изменения Harvest</h2></div>
          <div class="list-rows">${recent}</div>
        </article>
      </div>
    `;

    views.overview.querySelectorAll("[data-go]").forEach((btn) => {
      btn.addEventListener("click", () => navigate(btn.getAttribute("data-go")));
    });
  }

  function renderPersonality() {
    const sections = [
      ["values", "Ценности и принципы", data.portrait.values],
      ["motivation", "Мотивация", data.portrait.motivation],
      ["thinking", "Особенности мышления", data.portrait.thinking],
      ["skills", "Компетенции", data.portrait.skills],
      ["interests", "Интересы", data.portrait.interests],
      ["strengths", "Сильные стороны", data.portrait.strengths],
      ["growth", "Зоны развития", data.portrait.growth],
      ["tensions", "Потенциальные напряжения", data.portrait.tensions],
      ["desired", "Желаемый образ себя", data.portrait.desired],
    ];

    const toc = sections
      .map(([id, label]) => `<button type="button" data-jump="${id}">${escapeHtml(label)}</button>`)
      .join("");

    const body = sections
      .map(
        ([id, label, items]) => `<article class="panel" id="sec-${id}">
        <div class="panel-h"><h2 class="panel-title">${escapeHtml(label)}</h2></div>
        ${epList(items)}
      </article>`
      )
      .join("");

    const history = data.portrait.history
      .map((h) => `<div class="progress-line"><span>${escapeHtml(h.text)}</span><span>${escapeHtml(h.when)}</span></div>`)
      .join("");

    views.personality.innerHTML = `
      <div class="ep-legend" style="margin-bottom:12px">
        <span><i style="background:var(--fact)"></i>факт</span>
        <span><i style="background:var(--intent)"></i>намерение</span>
        <span><i style="background:var(--hypo)"></i>гипотеза</span>
        <span><i style="background:var(--open)"></i>открытый вопрос</span>
      </div>
      <div class="actions-row" style="margin:0 0 14px">
        <button class="btn is-disabled" type="button" title="скоро">Открыть источник</button>
        <button class="btn is-disabled" type="button" title="скоро">Оспорить вывод</button>
        <button class="btn is-disabled" type="button" title="скоро">Дополнить знание</button>
        <button class="btn is-disabled" type="button" title="скоро">Посмотреть историю</button>
        <span class="chip">скоро</span>
      </div>
      <div class="portrait-layout">
        <nav class="portrait-toc" aria-label="Разделы портрета">${toc}
          <button type="button" data-jump="history">История изменений</button>
        </nav>
        <div class="portrait-sections">
          ${body}
          <article class="panel" id="sec-history">
            <div class="panel-h"><h2 class="panel-title">История изменений</h2></div>
            <div class="progress-block">${history}</div>
          </article>
        </div>
      </div>
    `;

    views.personality.querySelectorAll("[data-jump]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const el = document.getElementById(`sec-${btn.getAttribute("data-jump")}`);
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
        views.personality.querySelectorAll("[data-jump]").forEach((b) => b.classList.remove("is-active"));
        btn.classList.add("is-active");
      });
    });
  }

  function renderStub(route) {
    views.stub.innerHTML = `
      <div class="stub">
        <h2>${escapeHtml(titles[route] || route)}</h2>
        <p>Раздел в композиции продукта. Полноценная функциональность не реализована в UI 0.2.</p>
        <p class="muted">Знания по-прежнему живут в harvest/. Этот экран — навигационный каркас.</p>
      </div>
    `;
  }

  function navigate(route) {
    const implemented = route === "overview" || route === "personality";
    const activeRoute = implemented ? route : "stub";

    Object.entries(views).forEach(([key, v]) => {
      const on = key === activeRoute;
      v.hidden = !on;
      if (on) v.removeAttribute("inert");
      else {
        v.setAttribute("inert", "");
        if (key !== activeRoute) v.innerHTML = "";
      }
    });
    titleEl.textContent = titles[route] || "Live Harvest";

    document.querySelectorAll(".nav-item[data-route]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.getAttribute("data-route") === route);
    });

    if (route === "overview") renderOverview();
    else if (route === "personality") renderPersonality();
    else renderStub(route);

    location.hash = route;
  }

  document.querySelectorAll(".nav-item[data-route]").forEach((btn) => {
    btn.addEventListener("click", () => navigate(btn.getAttribute("data-route")));
  });

  window.addEventListener("hashchange", () => {
    const route = (location.hash || "#overview").replace("#", "") || "overview";
    navigate(titles[route] ? route : "overview");
  });

  const initial = (location.hash || "#overview").replace("#", "") || "overview";
  navigate(titles[initial] ? initial : "overview");
})();
