(() => {
  const D = window.LH_DATA;
  const stage = document.getElementById("stage");
  const title = document.getElementById("pageTitle");
  const kicker = document.getElementById("kicker");
  const asOf = document.getElementById("asOf");
  asOf.textContent = `as of ${D.meta.asOf}`;

  const titles = {
    home: ["Command Center", "Обзор"],
    self: ["Character sheet", "Личность"],
    knowledge: ["Knowledge", "База знаний"],
    goals: ["Goals", "Цели"],
    projects: ["Projects", "Проекты"],
    finance: ["Finance", "Финансы"],
    health: ["Health", "Здоровье"],
    plan: ["Planning", "Планирование"],
    journal: ["Journal", "Дневник"],
    retro: ["Retro", "Ретроспектива"],
    harvester: ["Module", "Harvester"],
    advisor: ["Module", "Advisor"],
    razvivator: ["Module", "Развиватор"],
  };

  const esc = (s) =>
    String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");

  function stateBoard() {
    const s = D.state;
    const cell = (k, v) =>
      `<div class="state-item"><div class="k">${k}</div><div class="empty">${v == null || v === "" ? "нет данных" : esc(v)}</div></div>`;
    return `${cell("настроение", s.mood)}${cell("энергия", s.energy)}${cell("фокус", s.focus)}${cell("волна", s.wave)}`;
  }

  function universeSVG(selectedId) {
    const cx = 200, cy = 200, r = 118;
    const nodes = D.universe
      .map((u) => {
        const a = ((u.angle - 90) * Math.PI) / 180;
        const x = cx + Math.cos(a) * r;
        const y = cy + Math.sin(a) * r;
        const selected = u.id === selectedId ? " active" : "";
        return `<g class="node ${u.status}${selected}" data-node="${u.id}" transform="translate(${x},${y})">
          <circle class="leaf" r="22"></circle>
          <text text-anchor="middle" dy="4">${esc(u.label)}</text>
        </g>`;
      })
      .join("");
    return `<svg class="universe-svg" viewBox="0 0 400 400" role="img" aria-label="Моя вселенная">
      <circle class="orbit" cx="200" cy="200" r="78"></circle>
      <circle class="orbit orbit-2" cx="200" cy="200" r="118"></circle>
      <circle class="orbit" cx="200" cy="200" r="158" stroke-dasharray="2 6"></circle>
      <g class="node" transform="translate(200,200)">
        <circle class="core" r="36"></circle>
        <text text-anchor="middle" dy="-2" style="font-size:13px;font-weight:600">${esc(D.profile.name)}</text>
        <text class="sub" text-anchor="middle" dy="14">ядро</text>
      </g>
      ${nodes}
    </svg>`;
  }

  function universeDetail(id) {
    const u = D.universe.find((x) => x.id === id) || D.universe[0];
    return `<div class="universe-detail" id="universeDetail">
      <h3>${esc(u.label)}</h3>
      <p>${esc(u.blurb)}</p>
      <div class="universe-hint">Визуализация связей, не аналитический KPI. Статус: ${esc(u.status)}.</div>
    </div>`;
  }

  function renderHome() {
    const p = D.profile;
    const mq = D.mainQuest;
    const selected = D.universe[0].id;
    stage.innerHTML = `
      <div class="bento">
        <article class="cell s5 r2">
          <div class="cell-h"><p class="cell-title">Личный статус</p><button class="linkish" type="button" data-go="self">портрет →</button></div>
          <h2 class="status-name">${esc(p.name)}</h2>
          <p class="status-role">${esc(p.role)}</p>
          <p class="status-stage">${esc(p.stage)}</p>
          <p class="status-focus">${esc(p.focus)}</p>
          <div class="pills">${p.values.map((v) => `<span class="pill">${esc(v)}</span>`).join("")}</div>
          <p class="motto">«${esc(p.motto)}»</p>
        </article>

        <article class="cell s7">
          <div class="cell-h"><p class="cell-title">Состояние</p><span class="chip">пусто = нет среза</span></div>
          <div class="state-board">${stateBoard()}</div>
        </article>

        <article class="cell s7 quest">
          <div class="quest-badge">main quest</div>
          <h3>${esc(mq.title)}</h3>
          <p>${esc(mq.detail)}</p>
          <p class="cp">checkpoint · ${esc(mq.checkpoint)}</p>
        </article>

        <article class="cell s12 universe-cell">
          <div class="cell-h"><p class="cell-title">Моя вселенная</p><span class="chip">сигнатура продукта</span></div>
          <div class="universe-wrap">
            <div id="universeMount">${universeSVG(selected)}</div>
            ${universeDetail(selected)}
          </div>
        </article>

        <article class="cell s5">
          <div class="cell-h"><p class="cell-title">Активные квесты</p></div>
          <div class="rows">${D.sideQuests
            .map(
              (q) => `<div class="row"><span class="dot"></span><div><div class="row-t">${esc(q.title)}</div><div class="row-m">${esc(q.meta)}</div></div></div>`
            )
            .join("")}</div>
        </article>

        <article class="cell s7">
          <div class="cell-h"><p class="cell-title">Волны вдохновения</p></div>
          <div class="waves">${D.waves.map((w) => `<span class="wave">${esc(w)}</span>`).join("")}</div>
        </article>

        <article class="cell s6">
          <div class="cell-h"><p class="cell-title">Развиватор</p>${D.razvivator.demo ? '<span class="chip demo">демо</span>' : ""}</div>
          <div class="raz-card">
            <div class="raz-type">${esc(D.razvivator.type)}</div>
            <div class="raz-text">${esc(D.razvivator.text)}</div>
          </div>
        </article>

        <article class="cell s6">
          <div class="cell-h"><p class="cell-title">Прогресс</p></div>
          ${D.progress.achievements
            .map((a) => `<div class="prog-line"><span>${esc(a.title)}</span><span>${esc(a.when)}</span></div>`)
            .join("")}
          ${D.progress.measurable
            .map((m) => `<div class="prog-line"><span>${esc(m.label)}</span><span>${esc(m.value)}</span></div>`)
            .join("")}
        </article>

        <article class="cell s12">
          <div class="cell-h"><p class="cell-title">Активность Harvest</p></div>
          <div class="rows">${D.recent
            .map(
              (r) => `<div class="row"><span class="dot" style="background:var(--accent)"></span><div><div class="row-t">${esc(r.what)}</div><div class="row-m">${esc(r.kind)}</div></div></div>`
            )
            .join("")}</div>
        </article>
      </div>`;

    bindUniverse();
    stage.querySelector("[data-go]")?.addEventListener("click", () => go("self"));
  }

  function bindUniverse() {
    const mount = document.getElementById("universeMount");
    const detail = document.getElementById("universeDetail");
    if (!mount) return;
    mount.querySelectorAll("[data-node]").forEach((g) => {
      g.addEventListener("click", () => {
        const id = g.getAttribute("data-node");
        mount.innerHTML = universeSVG(id);
        detail.outerHTML = universeDetail(id);
        bindUniverse();
      });
    });
  }

  function renderSelf() {
    const core = D.portrait.core;
    const clusters = D.portrait.clusters
      .map(
        (c, i) => `<div class="cluster${i === 0 ? " is-open" : ""}" data-cluster="${c.id}">
        <h3>${esc(c.title)}</h3>
        <ul>${c.items.map((it) => `<li data-ep="${it.ep}">${esc(it.text)}</li>`).join("")}</ul>
      </div>`
      )
      .join("");

    stage.innerHTML = `
      <div class="legend">
        <span><i style="background:var(--life)"></i>факт</span>
        <span><i style="background:var(--intent)"></i>намерение</span>
        <span><i style="background:var(--hypo)"></i>гипотеза</span>
        <span><i style="background:var(--open)"></i>открытый вопрос</span>
      </div>
      <div class="actions">
        <button class="btn" type="button" disabled>Открыть источник</button>
        <button class="btn" type="button" disabled>Оспорить вывод</button>
        <button class="btn" type="button" disabled>Дополнить</button>
        <span class="chip">скоро</span>
      </div>
      <div class="char">
        <section class="core">
          <p class="eyebrow">${esc(core.title)}</p>
          <h2>${esc(D.profile.name)}</h2>
          <p class="lead">${esc(core.lead)}</p>
          <div class="meta">${D.profile.values.map((v) => `<span class="pill">${esc(v)}</span>`).join("")}</div>
          <p class="motto" style="margin-top:18px">«${esc(D.profile.motto)}»</p>
        </section>
        <div>
          <div class="cluster-grid">${clusters}</div>
          <div class="history">
            <p class="cell-title" style="margin-bottom:8px">История изменений</p>
            ${D.portrait.history
              .map((h) => `<div class="prog-line"><span>${esc(h.text)}</span><span>${esc(h.when)}</span></div>`)
              .join("")}
          </div>
        </div>
      </div>`;

    stage.querySelectorAll("[data-cluster]").forEach((el) => {
      el.addEventListener("click", () => {
        el.classList.toggle("is-open");
      });
    });
  }

  function renderStub(route) {
    const t = titles[route]?.[1] || route;
    stage.innerHTML = `<div class="stub"><h2>${esc(t)}</h2><p>Раздел в композиции Life OS. Функциональность появится позже. Знания остаются в harvest/.</p></div>`;
  }

  function go(route) {
    const meta = titles[route] || ["Live Harvest", route];
    kicker.textContent = meta[0];
    title.textContent = meta[1];
    document.querySelectorAll(".nav-btn[data-route]").forEach((b) => {
      b.classList.toggle("is-active", b.getAttribute("data-route") === route);
    });
    if (route === "home") renderHome();
    else if (route === "self") renderSelf();
    else renderStub(route);
    if (location.hash.slice(1) !== route) location.hash = route;
  }

  document.querySelectorAll(".nav-btn[data-route]").forEach((b) => {
    b.addEventListener("click", () => go(b.getAttribute("data-route")));
  });
  window.addEventListener("hashchange", () => {
    const r = (location.hash || "#home").slice(1);
    go(titles[r] ? r : "home");
  });
  go(titles[(location.hash || "#home").slice(1)] ? (location.hash || "#home").slice(1) : "home");
})();
