(() => {
  let D = window.LH_DATA;
  let lastGenerated = null;
  const stage = document.getElementById("stage");
  const titleEl = document.getElementById("pageTitle");
  const kicker = document.getElementById("kicker");
  const asOf = document.getElementById("asOf");
  const snapMeta = document.getElementById("snapMeta");
  const btnRefresh = document.getElementById("btnRefresh");

  const titles = {
    home: ["Сегодня", "Обзор"],
    self: ["Портрет", "Личность"],
    universe: ["Исследование", "Моя вселенная"],
  };

  const esc = (s) =>
    String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");

  const epLabel = { fact: "факт", intent: "намерение", hypo: "гипотеза", open: "открытый вопрос" };

  function currentRoute() {
    const r = (location.hash || "#home").slice(1);
    return titles[r] ? r : "home";
  }

  function cluster(id) {
    return D.portrait?.clusters?.find((c) => c.id === id);
  }

  function itemsHtml(items) {
    return (items || []).map((it) => `<li data-ep="${esc(it.ep)}">${esc(it.text)}</li>`).join("");
  }

  function updateChrome() {
    const gen = D.meta?.generated_at || D.meta?.asOf || "—";
    asOf.textContent = `as of ${D.meta?.asOf || "—"}`;
    if (snapMeta) {
      const short = String(gen).replace("T", " ").replace("Z", " UTC");
      const note = D.meta?.presentation_note ? " · интерпретация" : "";
      snapMeta.textContent = `снимок ${short}${note}`;
    }
    lastGenerated = gen;
  }

  async function fetchSnapshot() {
    const res = await fetch(`./snapshot.json?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`snapshot ${res.status}`);
    return res.json();
  }

  async function reloadData({ silent = false } = {}) {
    try {
      const next = await fetchSnapshot();
      D = next;
      window.LH_DATA = next;
      updateChrome();
      go(currentRoute(), { skipHash: true });
      if (!silent && btnRefresh) {
        btnRefresh.textContent = "Обновлено";
        setTimeout(() => {
          btnRefresh.textContent = "Обновить снимок";
        }, 1200);
      }
      return true;
    } catch (e) {
      if (!silent) console.warn("snapshot reload failed, using embedded data.js", e);
      updateChrome();
      return false;
    }
  }

  /* ——— Universe: single SVG, stable handlers ——— */
  function UniverseController(mapHost, detailHost, opts = {}) {
    const page = !!opts.page;
    let selected = opts.initialId || D.universe[0].id;
    let bound = false;

    const cx = 200;
    const cy = 200;
    const r = 118;

    function nodePos(angle) {
      const a = ((angle - 90) * Math.PI) / 180;
      return { x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * r };
    }

    function buildSVG() {
      const nodes = D.universe
        .map((u) => {
          const { x, y } = nodePos(u.angle);
          return `<g class="uni-node" data-node="${esc(u.id)}" data-status="${esc(u.status)}"
            transform="translate(${x.toFixed(1)},${y.toFixed(1)})"
            role="button" tabindex="0" aria-pressed="false"
            aria-label="${esc(u.label)}">
            <circle class="pulse" r="28"></circle>
            <circle class="leaf" r="22"></circle>
            <text class="label" text-anchor="middle" dy="4">${esc(u.label)}</text>
          </g>`;
        })
        .join("");

      return `<svg class="uni-svg" viewBox="0 0 400 400" role="img" aria-label="Карта жизненных областей">
        <circle class="uni-orbit" cx="200" cy="200" r="78"></circle>
        <circle class="uni-orbit mid" cx="200" cy="200" r="118"></circle>
        <circle class="uni-orbit outer" cx="200" cy="200" r="158"></circle>
        <g class="uni-core" transform="translate(200,200)" aria-hidden="true">
          <circle r="34"></circle>
          <text text-anchor="middle" dy="-2">${esc(D.profile.name)}</text>
          <text class="sub" text-anchor="middle" dy="14">ядро</text>
        </g>
        ${nodes}
      </svg>`;
    }

    function writeDetail(id, animate) {
      const u = D.universe.find((x) => x.id === id) || D.universe[0];
      const statusNote =
        u.status === "empty"
          ? "Среза знаний пока нет."
          : u.status === "watch"
            ? "Область требует внимания."
            : "Есть подтверждённый срез.";
      const modeNote = u.mode === "interpreted" ? " · формулировка UI" : u.mode === "literal" ? " · 1:1 из базы" : "";
      detailHost.className = page ? "uni-detail is-page" : "uni-detail";
      if (animate) {
        detailHost.classList.remove("detail-swap");
        void detailHost.offsetWidth;
        detailHost.classList.add("detail-swap");
      }
      detailHost.innerHTML = `
        <p class="d-label">область</p>
        <h3 id="uniDetailTitle">${esc(u.label)}</h3>
        <p class="d-blurb" id="uniDetailBlurb">${esc(u.blurb)}</p>
        <p class="d-meta">${esc(statusNote)}${esc(modeNote)} · не KPI</p>`;
    }

    function setActive(id, { animateDetail = true, focusNode = false } = {}) {
      selected = id;
      mapHost.querySelectorAll(".uni-node").forEach((g) => {
        const on = g.getAttribute("data-node") === id;
        g.classList.toggle("is-active", on);
        g.setAttribute("aria-pressed", on ? "true" : "false");
        if (on && focusNode) g.focus({ preventScroll: true });
      });
      writeDetail(id, animateDetail);
    }

    function onActivate(id) {
      if (!id) return;
      setActive(id, { animateDetail: true });
    }

    function bind() {
      if (bound) return;
      bound = true;
      mapHost.addEventListener("click", (e) => {
        const g = e.target.closest("[data-node]");
        if (!g || !mapHost.contains(g)) return;
        onActivate(g.getAttribute("data-node"));
      });
      mapHost.addEventListener("keydown", (e) => {
        const g = e.target.closest("[data-node]");
        if (!g || !mapHost.contains(g)) return;
        const ids = D.universe.map((u) => u.id);
        const i = ids.indexOf(g.getAttribute("data-node"));
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onActivate(g.getAttribute("data-node"));
        } else if (e.key === "ArrowRight" || e.key === "ArrowDown") {
          e.preventDefault();
          setActive(ids[(i + 1) % ids.length], { animateDetail: true, focusNode: true });
        } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
          e.preventDefault();
          setActive(ids[(i - 1 + ids.length) % ids.length], { animateDetail: true, focusNode: true });
        }
      });
    }

    mapHost.innerHTML = buildSVG();
    bind();
    setActive(selected, { animateDetail: false });
    return { setActive, getSelected: () => selected };
  }

  function universeBlock(compact) {
    return `
      <div class="uni-panel${compact ? "" : " is-page"}">
        <div class="uni-map-host" data-uni-map></div>
        <div data-uni-detail></div>
      </div>`;
  }

  function wireUniverse(root, opts) {
    const map = root.querySelector("[data-uni-map]");
    const detail = root.querySelector("[data-uni-detail]");
    if (!map || !detail) return null;
    return UniverseController(map, detail, opts);
  }

  function renderHome() {
    const p = D.profile;
    const mq = D.mainQuest;
    const values = cluster("values");
    const note = D.meta?.presentation_note
      ? `<p class="pres-note">${esc(D.meta.presentation_note)}</p>`
      : "";
    stage.innerHTML = `
      <div class="home">
        ${note}
        <section class="intro">
          <h2 class="intro-name">${esc(p.name)}</h2>
          <p class="intro-role">${esc(p.role)}</p>
          <p class="intro-stage">${esc(p.stage)}</p>
          <div class="focus-block">
            <p class="focus-label">Фокус</p>
            <p class="focus-text">${esc(p.focus)}</p>
          </div>
          <button type="button" class="intro-link" data-go="self">Открыть личность →</button>
        </section>

        <section>
          <p class="section-label">Главная цель</p>
          <div class="quest-block">
            <h3 class="quest-title">${esc(mq.title)}</h3>
            <p class="quest-detail">${esc(mq.detail)}</p>
            <p class="quest-cp">Контрольная точка · ${esc(mq.checkpoint)}</p>
          </div>
        </section>

        <section>
          <p class="section-label">Моя вселенная</p>
          ${universeBlock(true)}
          <p class="uni-hint">Выбери область — справа срез из базы или UI-формулировка. Полный экран: «Моя вселенная».</p>
        </section>

        <section class="home-split">
          <div>
            <p class="section-label">Актуальные действия</p>
            <ul class="action-list">
              ${(D.sideQuests || [])
                .map(
                  (q) => `<li><span class="action-t">${esc(q.title)}</span><span class="action-m">${esc(q.meta)}</span></li>`
                )
                .join("")}
            </ul>
          </div>
          <div>
            <p class="section-label">Рекомендация</p>
            <blockquote class="pull">
              <p class="pull-type">${esc(D.razvivator.type)}</p>
              <p class="pull-text">${esc(D.razvivator.text)}</p>
              ${
                D.razvivator.demo
                  ? '<p class="pull-demo">демо</p>'
                  : `<p class="pull-demo">${esc(D.razvivator.mode === "interpreted" ? "интерпретация Harvester" : "из базы")}</p>`
              }
            </blockquote>
          </div>
        </section>

        <details class="more">
          <summary>Ещё: волны, прогресс, активность</summary>
          <div class="more-body">
            <div>
              <p class="section-label">Волны</p>
              <ul class="soft-list">${(D.waves || []).map((w) => `<li><span>${esc(w)}</span><span></span></li>`).join("")}</ul>
            </div>
            <div>
              <p class="section-label">Прогресс</p>
              <ul class="soft-list">
                ${(D.progress?.achievements || [])
                  .map((a) => `<li><span>${esc(a.title)}</span><span>${esc(a.when)}</span></li>`)
                  .join("")}
                ${(D.progress?.measurable || [])
                  .map((m) => `<li><span>${esc(m.label)}</span><span>${esc(m.value)}</span></li>`)
                  .join("")}
              </ul>
            </div>
            <div>
              <p class="section-label">Активность Harvest</p>
              <ul class="soft-list">
                ${(D.recent || []).map((r) => `<li><span>${esc(r.what)}</span><span>${esc(r.kind)}</span></li>`).join("")}
              </ul>
            </div>
            ${
              values
                ? `<div><p class="section-label">Ценности (кратко)</p><ul class="soft-list">${values.items
                    .map((it) => `<li><span>${esc(it.text)}</span><span>${esc(epLabel[it.ep] || it.ep)}</span></li>`)
                    .join("")}</ul></div>`
                : ""
            }
          </div>
        </details>
      </div>`;

    wireUniverse(stage, { initialId: D.universe[0].id });
    stage.querySelector("[data-go]")?.addEventListener("click", () => go("self"));
  }

  function renderUniverse() {
    stage.innerHTML = `
      <p class="uni-page-lead">Жизненные области вокруг ядра. Срезы подтягиваются из harvest/ (literal) или overlay (interpreted). Не граф доказанных связей и не шкала личности.</p>
      ${universeBlock(false)}
      <p class="uni-hint">Клавиатура: Tab → узел · Enter · стрелки между областями.</p>`;
    wireUniverse(stage, { page: true, initialId: D.universe[0].id });
  }

  function renderSelf() {
    const core = D.portrait.core;
    const values = cluster("values");
    const mind = cluster("mind");
    const drive = cluster("drive");
    const create = cluster("create");
    const edge = cluster("edge");
    const grow = cluster("grow");
    const craft = cluster("craft");
    const spark = cluster("spark");
    const tension = cluster("tension");
    const future = cluster("future");

    stage.innerHTML = `
      <div class="persona">
        <section class="persona-hero">
          <p class="persona-kicker">${esc(core.title)}</p>
          <h2 class="persona-name">${esc(D.profile.name)}</h2>
          <p class="persona-lead">${esc(core.lead)}</p>
          <p class="persona-motto">«${esc(D.profile.motto)}»</p>
        </section>

        <div class="ep-legend" aria-label="Эпистемическая легенда">
          <span><i class="f"></i>факт</span>
          <span><i class="i"></i>намерение</span>
          <span><i class="h"></i>гипотеза</span>
          <span><i class="o"></i>открытый вопрос</span>
        </div>

        ${
          values
            ? `<section>
          <p class="section-label">${esc(values.title)}</p>
          <div class="values">
            ${values.items
              .map(
                (it) => `<div class="value-row" data-ep="${esc(it.ep)}"><span class="mark" aria-hidden="true"></span><p>${esc(it.text)}</p></div>`
              )
              .join("")}
          </div>
        </section>`
            : ""
        }

        <section class="two-col">
          ${mind ? `<div class="block"><h2>${esc(mind.title)}</h2><ul>${itemsHtml(mind.items)}</ul></div>` : ""}
          ${drive ? `<div class="block"><h2>${esc(drive.title)}</h2><ul>${itemsHtml(drive.items)}</ul></div>` : ""}
        </section>

        ${
          create
            ? `<section>
          <p class="section-label">${esc(create.title)}${create.mode === "literal" ? " · из базы" : ""}</p>
          <div class="block"><ul>${itemsHtml(create.items)}</ul></div>
        </section>`
            : ""
        }

        <section class="two-col">
          ${edge ? `<div class="block"><h2>${esc(edge.title)}</h2><ul>${itemsHtml(edge.items)}</ul></div>` : ""}
          ${grow ? `<div class="block"><h2>${esc(grow.title)}</h2><ul>${itemsHtml(grow.items)}</ul></div>` : ""}
        </section>

        <details class="more">
          <summary>Компетенции, интересы, напряжения, желаемый образ</summary>
          <div class="more-body two-col" style="padding-top:16px">
            ${craft ? `<div class="block"><h2>${esc(craft.title)}</h2><ul>${itemsHtml(craft.items)}</ul></div>` : ""}
            ${spark ? `<div class="block"><h2>${esc(spark.title)}</h2><ul>${itemsHtml(spark.items)}</ul></div>` : ""}
            ${tension ? `<div class="block"><h2>${esc(tension.title)}</h2><ul>${itemsHtml(tension.items)}</ul></div>` : ""}
            ${future ? `<div class="block"><h2>${esc(future.title)}</h2><ul>${itemsHtml(future.items)}</ul></div>` : ""}
          </div>
        </details>

        <section>
          <p class="section-label">История изменений</p>
          <ol class="timeline">
            ${(D.portrait.history || [])
              .map((h) => `<li><time datetime="${esc(h.when)}">${esc(h.when)}</time><span>${esc(h.text)}</span></li>`)
              .join("")}
          </ol>
        </section>
      </div>`;
  }

  function go(route, { skipHash = false } = {}) {
    const r = titles[route] ? route : "home";
    const meta = titles[r];
    kicker.textContent = meta[0];
    titleEl.textContent = meta[1];
    document.querySelectorAll(".nav-btn[data-route]").forEach((b) => {
      b.classList.toggle("is-active", b.getAttribute("data-route") === r);
    });
    if (r === "home") renderHome();
    else if (r === "self") renderSelf();
    else if (r === "universe") renderUniverse();
    if (!skipHash && location.hash.slice(1) !== r) location.hash = r;
  }

  document.querySelectorAll(".nav-btn[data-route]").forEach((b) => {
    b.addEventListener("click", () => go(b.getAttribute("data-route")));
  });
  window.addEventListener("hashchange", () => go(currentRoute(), { skipHash: true }));
  btnRefresh?.addEventListener("click", () => reloadData({ silent: false }));

  // Live poll: if Harvester regenerated snapshot, screens refresh without hard reload
  setInterval(async () => {
    try {
      const res = await fetch(`./snapshot.json?t=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) return;
      const next = await res.json();
      const gen = next.meta?.generated_at || next.meta?.asOf;
      if (gen && lastGenerated && gen !== lastGenerated) {
        D = next;
        window.LH_DATA = next;
        updateChrome();
        go(currentRoute(), { skipHash: true });
      } else if (!lastGenerated) {
        lastGenerated = gen;
      }
    } catch (_) {
      /* offline / file protocol */
    }
  }, 12000);

  // Boot: prefer fresh snapshot over embedded data.js
  reloadData({ silent: true }).then((ok) => {
    if (!ok) {
      updateChrome();
      go(currentRoute(), { skipHash: true });
    }
  });
})();
