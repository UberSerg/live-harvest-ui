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
    home: ["Первый кадр", "Сегодня"],
    universe: ["Исследование", "Моя вселенная"],
    capital: ["Курс на свободу", "Капитал"],
  };

  const LENSES = {
    self: { kicker: "Личность", hint: "портрет" },
    reflect: { kicker: "Рефлексия", hint: "вопрос и история" },
    research: { kicker: "Исследования", hint: "гипотезы и вопросы" },
    grow: { kicker: "Развитие", hint: "зоны из снимка" },
  };

  const COMMANDS = [
    { id: "home", label: "Сегодня", hint: "первый кадр" },
    { id: "brain:self", label: "Мозг · Личность", hint: "портрет" },
    { id: "brain:reflect", label: "Мозг · Рефлексия", hint: "вопрос и история" },
    { id: "brain:research", label: "Мозг · Исследования", hint: "гипотезы и вопросы" },
    { id: "brain:grow", label: "Мозг · Развитие", hint: "зоны из снимка" },
    { id: "universe", label: "Вселенная", hint: "области" },
    { id: "capital", label: "Капитал", hint: "инструмент" },
  ];

  const esc = (s) =>
    String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");

  const epLabel = { fact: "факт", intent: "намерение", hypo: "гипотеза", open: "открытый вопрос" };

  function parseHash(input) {
    const raw = String(input == null ? location.hash || "#home" : input).replace(/^#/, "") || "home";
    if (raw === "self") return { route: "brain", lens: "self" };
    if (raw === "brain" || raw.startsWith("brain:")) {
      const lens = raw.slice("brain:".length);
      return { route: "brain", lens: LENSES[lens] ? lens : "self" };
    }
    if (titles[raw]) return { route: raw, lens: null };
    return { route: "home", lens: null };
  }

  function specHash(spec) {
    if (spec.route === "brain") return `brain:${spec.lens || "self"}`;
    return spec.route;
  }

  function attentionSentence() {
    const nodes = D.universe || [];
    const watch = nodes.filter((u) => u.status === "watch");
    const empty = nodes.filter((u) => u.status === "empty");
    if (!nodes.length) return "В снимке нет областей.";
    if (watch.length === 1) return `${watch[0].label} — область требует внимания.`;
    if (watch.length > 1) return `${watch.map((u) => u.label).join(", ")} — области требуют внимания.`;
    if (empty.length === nodes.length) return "Срезов по областям пока нет.";
    if (empty.length) return `Ни одна область не в статусе внимания. Без среза: ${empty.map((u) => u.label).join(", ")}.`;
    return "Ни одна область не в статусе внимания.";
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
      const demo = D.meta?.demo ? " · демо" : "";
      snapMeta.textContent = `снимок ${short}${note}${demo}`;
    }
    if (btnRefresh) {
      btnRefresh.title = D.meta?.demo ? "Перечитать демо-снимок" : "Перечитать snapshot.json";
    }
    lastGenerated = gen;
  }

  function snapshotFile() {
    const demo = new URLSearchParams(location.search).get("demo") === "1";
    return demo ? "./demo/snapshot.demo.json" : "./snapshot.json";
  }

  async function fetchSnapshot() {
    const res = await fetch(`${snapshotFile()}?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`snapshot ${res.status}`);
    return res.json();
  }

  async function reloadData({ silent = false } = {}) {
    try {
      const next = await fetchSnapshot();
      D = next;
      window.LH_DATA = next;
      updateChrome();
      go(parseHash(), { skipHash: true });
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
    if (!D.universe?.length) {
      mapHost.innerHTML = "";
      detailHost.className = page ? "uni-detail is-page" : "uni-detail";
      detailHost.innerHTML = `<p class="d-blurb">В снимке нет областей.</p>`;
      return { setActive() {}, getSelected: () => null };
    }
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

  function bindGo(root) {
    root.querySelectorAll("[data-go]").forEach((b) => {
      b.addEventListener("click", () => go(b.getAttribute("data-go")));
    });
  }

  function renderHome() {
    const p = D.profile || {};
    const mq = D.mainQuest || {};
    const values = cluster("values");
    const step = (D.sideQuests || [])[0];
    const question = D.razvivator?.text;
    const note = D.meta?.presentation_note
      ? `<p class="pres-note">${esc(D.meta.presentation_note)}</p>`
      : "";
    const stepLine = step
      ? `${esc(step.title)}${step.meta ? ` · ${esc(step.meta)}` : ""}`
      : "В снимке нет актуального шага.";
    const questionLine = question
      ? `${esc(question)}${D.razvivator.demo ? " · демо" : ""}`
      : "В снимке нет вопроса.";
    stage.innerHTML = `
      <div class="home">
        <section class="morning" aria-label="Первый кадр">
          <p class="morning-who">${esc(p.name || "Без имени")}${p.role ? ` · ${esc(p.role)}` : ""}</p>
          <p class="morning-focus">${esc(p.focus || "Фокус в снимке не задан.")}</p>
          ${p.stage ? `<p class="morning-stage">${esc(p.stage)}</p>` : ""}
          <ul class="morning-lines">
            <li><span>Точка</span><p>${esc(mq.checkpoint || "Контрольная точка не задана.")}</p></li>
            <li><span>Внимание</span><p>${esc(attentionSentence())}</p></li>
            <li><span>Шаг</span><p>${stepLine}</p></li>
            <li><span>Вопрос</span><p>${questionLine}</p></li>
          </ul>
          <div class="morning-jumps">
            <button type="button" class="intro-link" data-go="universe">Вселенная</button>
            <button type="button" class="intro-link" data-go="brain:reflect">Вопрос в мозге</button>
            <button type="button" class="intro-link" data-go="brain:self">Личность</button>
            <button type="button" class="intro-link" data-go="capital">Капитал</button>
          </div>
        </section>
        ${note}

        <section>
          <p class="section-label">Главная цель</p>
          <div class="quest-block">
            <h3 class="quest-title">${esc(mq.title)}</h3>
            <p class="quest-detail">${esc(mq.detail)}</p>
          </div>
        </section>

        <section>
          <p class="section-label">Моя вселенная</p>
          ${universeBlock(true)}
          <p class="uni-hint">Выбери область — справа срез из базы или UI-формулировка. Полный экран: «Моя вселенная».</p>
        </section>

        <section>
          <p class="section-label">Актуальные действия</p>
          <ul class="action-list">
            ${(D.sideQuests || [])
              .map(
                (q) => `<li><span class="action-t">${esc(q.title)}</span><span class="action-m">${esc(q.meta)}</span></li>`
              )
              .join("")}
          </ul>
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

    wireUniverse(stage, { initialId: D.universe?.[0]?.id });
    bindGo(stage);
  }

  function renderUniverse() {
    stage.innerHTML = `
      <p class="uni-page-lead">Жизненные области вокруг ядра. Срезы подтягиваются из harvest/ (literal) или overlay (interpreted). Не граф доказанных связей и не шкала личности.</p>
      ${universeBlock(false)}
      <p class="uni-hint">Клавиатура: Tab → узел · Enter · стрелки между областями.</p>`;
    wireUniverse(stage, { page: true, initialId: D.universe?.[0]?.id });
  }

  function personaHtml() {
    const core = D.portrait?.core;
    if (!core) return `<p class="uni-page-lead">Портрета в снимке нет.</p>`;
    const name = D.profile?.name || "";
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

    const motto = D.profile?.motto
      ? `<p class="persona-motto">«${esc(D.profile.motto)}»</p>`
      : "";
    return `
      <div class="persona">
        <section class="persona-hero">
          <p class="persona-kicker">${esc(core.title)}</p>
          <h2 class="persona-name">${esc(name)}</h2>
          <p class="persona-lead">${esc(core.lead)}</p>
          ${motto}
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

  function clusterBlock(c) {
    if (!c) return "";
    return `<div class="block"><h2>${esc(c.title)}</h2><ul>${itemsHtml(c.items)}</ul></div>`;
  }

  function itemsByEp(eps) {
    const out = [];
    (D.portrait?.clusters || []).forEach((c) => {
      (c.items || []).forEach((it) => {
        if (eps.includes(it.ep)) out.push({ cluster: c.title, ep: it.ep, text: it.text });
      });
    });
    return out;
  }

  function lensBar(active) {
    const buttons = Object.entries(LENSES)
      .map(
        ([id, meta]) =>
          `<button type="button" class="lens-btn${id === active ? " is-active" : ""}" data-go="brain:${id}" aria-pressed="${
            id === active
          }">${esc(meta.kicker)}</button>`
      )
      .join("");
    return `<div class="lens" role="group" aria-label="Срезы мозга">${buttons}</div>
      <p class="lens-note">Срезы одного снимка. Ответ и новые карточки отсюда не пишутся.</p>`;
  }

  function historyHtml(history) {
    if (!history?.length) return `<p class="lens-note">Истории в снимке нет.</p>`;
    return `<section>
      <p class="section-label">История изменений</p>
      <ol class="timeline">
        ${history
          .map((h) => `<li><time datetime="${esc(h.when)}">${esc(h.when)}</time><span>${esc(h.text)}</span></li>`)
          .join("")}
      </ol>
    </section>`;
  }

  function buildReflectClarifyPrompt() {
    const q = D.razvivator || {};
    const opens = itemsByEp(["open"]).slice(0, 8);
    const openBlock = opens.length
      ? opens.map((row) => `- [${row.cluster}] ${row.text}`).join("\n")
      : "- (открытых пунктов в снимке нет)";
    const question = q.text || "(вопроса в снимке нет — предложи следующий из пробелов harvest/)";
    const source = q.source || "—";
    const mode = q.mode || "—";
    const qtype = q.type || "вопрос";
    return `# LH-UI-REFLECT

Источник: harvest-ui · Мозг · Рефлексия
Маркер: это уточнение из UI Live Harvest. Обработать как ответ на вопрос снимка, не как новый свободный чат.

## Текущий вопрос снимка
Тип: ${qtype}
Текст: ${question}
Источник: ${source}
mode: ${mode}

## Открытые пункты портрета (контекст)
${openBlock}

## Задачи агенту после моего ответа
1. Записать подтверждённые факты в \`harvest/\` (Harvester / STANDARD). Не выдумывать.
2. Обновить \`harvest-ui/overlay.json\`:
   - \`razvivator\` → следующий осмысленный вопрос (или закрыть, если уместно);
   - убрать/перевести устаревшие \`open\` в \`portrait_clusters_extra\`;
   - добавить строку в \`portrait_history\` (when + text).
3. Выполнить: \`python tools/lh_ui_snapshot.py\`
4. В ответе чата **сначала** блок:

\`\`\`
LH-UI-REFLECT-APPLIED
updated: <файлы / сущности>
next: <следующий вопрос или «закрыто»>
snapshot: rebuilt
ui: нажми «Обновить снимок» или дождись poll
\`\`\`

5. Не отправлять данные наружу. Секреты не писать.

## Мой ответ
`;
  }

  function bindReflect(root) {
    const btn = root.querySelector("#copyReflectClarify");
    if (!btn) return;
    btn.addEventListener("click", async () => {
      const status = root.querySelector("#reflectCopyStatus");
      const fallback = root.querySelector("#reflectFallback");
      const setStatus = (text) => {
        if (status) status.textContent = text;
      };
      const text = buildReflectClarifyPrompt();
      try {
        await navigator.clipboard.writeText(text);
        if (fallback) fallback.hidden = true;
        setStatus("Промпт в буфере. Вставь в Cursor, допиши ответ, отправь. UI сам базу не пишет.");
      } catch {
        if (fallback) {
          fallback.hidden = false;
          fallback.value = text;
          fallback.focus();
          fallback.select();
        }
        setStatus("Буфер недоступен. Текст ниже — скопируй вручную. Отправки из UI нет.");
      }
    });
  }

  function reflectHtml() {
    const q = D.razvivator;
    const tension = cluster("tension");
    const quote = q?.text
      ? `<blockquote class="pull">
          <p class="pull-type">${esc(q.type || "вопрос")}${q.demo ? " · демо" : ""}</p>
          <p class="pull-text">${esc(q.text)}</p>
          <p class="pull-demo">${
            q.demo ? "демо" : esc(q.mode === "interpreted" ? "интерпретация Harvester" : "из базы")
          }</p>
        </blockquote>`
      : `<p class="uni-page-lead">Вопроса в снимке нет.</p>`;
    return `${quote}
      <section class="research-path" aria-label="Уточнение рефлексии">
        <p class="section-label">Уточнить в Cursor</p>
        <p class="lens-note">Кнопка копирует промпт с маркером <code>LH-UI-REFLECT</code> и текущим вопросом. Вставь в чат Cursor, допиши ответ. Агент обновит harvest + overlay + snapshot. Этот экран сам ничего не пишет.</p>
        <div class="research-actions">
          <button type="button" class="btn-ghost" id="copyReflectClarify">Уточнить рефлексию</button>
          <span class="research-status" id="reflectCopyStatus" role="status"></span>
        </div>
        <textarea class="research-fallback" id="reflectFallback" hidden readonly aria-label="Промпт уточнения рефлексии"></textarea>
      </section>
      ${tension ? `<section>${clusterBlock(tension)}</section>` : ""}
      ${historyHtml(D.portrait?.history)}`;
  }

  function ingestHintHtml() {
    return `<p class="section-label">Приёмка ответа</p>
      <p class="lens-note">Ответ внешнего ИИ сохранить файлом и проверить локально. Импорт пишет очередь и предложение. Карточки, ledger и портрет не меняет.</p>
      <pre class="research-cmd">python tools/lh_ingest.py validate ФАЙЛ
python tools/lh_ingest.py import ФАЙЛ --apply --inbox harvest/Мозг/_inbox/research</pre>
      <p class="lens-note">Предложение: <code>harvest/Мозг/_inbox/research/proposals/proposal-&lt;имя файла&gt;.md</code></p>`;
  }

  function researchPathHtml() {
    const slice = D.research;
    const demo = !!(slice && slice.provenance === "synthetic-demo" && slice.synthetic === true);
    const packets = Array.isArray(slice?.packets) ? slice.packets : [];
    const real = !!(
      slice &&
      !demo &&
      slice.provenance &&
      slice.provenance !== "empty" &&
      packets.length
    );
    if (real) {
      const lines = packets
        .map((item) => {
          const path = typeof item === "string" ? item : item?.path || "";
          const note = item && typeof item === "object" && item.note ? item.note : "";
          return `<li><code>${esc(path)}</code>${note ? `<span>${esc(note)}</span>` : ""}</li>`;
        })
        .join("");
      return `<section class="research-path" aria-label="Пакет исследования">
        <p class="section-label">Пакет в снимке</p>
        <p class="uni-page-lead">Пути записаны в снимке. Этот экран их не отправляет и портрет не обновляет.</p>
        <ul class="soft-list">${lines}</ul>
        ${ingestHintHtml()}
      </section>`;
    }
    const includes =
      demo && Array.isArray(slice.includes) && slice.includes.length
        ? slice.includes
        : ["цель гипотезы", "известный пункт", "гипотеза и открытый вопрос", "правила интервью"];
    const excludes =
      demo && Array.isArray(slice.excludes) && slice.excludes.length
        ? slice.excludes
        : ["секреты", "суммы", "тела связанных карточек", "ledger", "портрет"];
    const lead = demo
      ? "Демо-снимок указывает на синтетический пакет. Это не портрет и не его обновление."
      : "Среза пакета в снимке нет. Ниже команда и синтетический пример, не данные этого снимка.";
    const file = demo && slice.packet_prompt ? slice.packet_prompt : "demo/research-packet.prompt.txt";
    return `<section class="research-path" aria-label="Путь к исследованию">
      <p class="section-label">Пакет исследования</p>
      <p class="uni-page-lead">${esc(lead)}</p>
      <p class="lens-note">Собрать пакет локально. Карточка «DEMO — синтетическая гипотеза» пакет не даёт: в ней нет маркированных гипотез, код <code>no_hypothesis</code>. Рабочий синтетический источник — фикстура.</p>
      <pre class="research-cmd">python tools/lh_research_packet.py tools/fixtures/lh_research/hypothesis_card.md</pre>
      <p class="lens-note">Кнопка копирует <code>${esc(file)}</code>. В тексте: ${esc(includes.join(", "))}. Нет: ${esc(
        excludes.join(", ")
      )}. Буфер только на этом компьютере. Отправки нет.</p>
      <div class="research-actions">
        <button type="button" class="btn-ghost" id="copyResearchPacket">Скопировать синтетический пакет</button>
        <span class="research-status" id="researchCopyStatus" role="status"></span>
      </div>
      <textarea class="research-fallback" id="researchFallback" hidden readonly aria-label="Текст синтетического пакета"></textarea>
      ${ingestHintHtml()}
    </section>`;
  }

  function bindResearch(root) {
    const btn = root.querySelector("#copyResearchPacket");
    if (!btn) return;
    btn.addEventListener("click", async () => {
      const status = root.querySelector("#researchCopyStatus");
      const fallback = root.querySelector("#researchFallback");
      const setStatus = (text) => {
        if (status) status.textContent = text;
      };
      try {
        const res = await fetch("./demo/research-packet.prompt.txt", { cache: "no-store" });
        if (!res.ok) throw new Error("missing");
        const text = (await res.text()).replace(/^\uFEFF/, "");
        if (!text.trim()) throw new Error("empty");
        if (/password\s*[:=]/i.test(text) || /hunter2/i.test(text)) {
          setStatus("Пакет не скопирован: в демо-файле неожиданный секрет. Отправки нет.");
          return;
        }
        try {
          await navigator.clipboard.writeText(text);
          if (fallback) fallback.hidden = true;
          setStatus("В буфере синтетический пакет. Никуда не отправлен. Портрет не менялся.");
        } catch {
          if (fallback) {
            fallback.hidden = false;
            fallback.value = text;
            fallback.focus();
            fallback.select();
          }
          setStatus("Буфер недоступен. Текст ниже — скопируйте вручную. Отправки нет. Портрет не менялся.");
        }
      } catch {
        setStatus("Файл demo/research-packet.prompt.txt не открылся. Отправки нет. Портрет не менялся.");
      }
    });
  }

  function researchHtml() {
    const rows = itemsByEp(["hypo", "open"]);
    const list = !rows.length
      ? `<p class="uni-page-lead">Гипотез и открытых вопросов в снимке нет.</p>`
      : (() => {
          const groups = [];
          rows.forEach((row) => {
            let g = groups.find((x) => x.title === row.cluster);
            if (!g) {
              g = { title: row.cluster, items: [] };
              groups.push(g);
            }
            g.items.push(row);
          });
          return `<p class="lens-note">Элементы снимка с метками «гипотеза» и «открытый вопрос». Экран из них пакет не собирает и портрет не обновляет.</p>${groups
            .map((g) => `<div class="block"><h2>${esc(g.title)}</h2><ul>${itemsHtml(g.items)}</ul></div>`)
            .join("")}`;
        })();
    return `${list}${researchPathHtml()}`;
  }

  function growHtml() {
    const grow = cluster("grow");
    const future = cluster("future");
    const waves = D.waves || [];
    if (!grow && !future && !waves.length) return `<p class="uni-page-lead">Среза развития в снимке нет.</p>`;
    return `<p class="lens-note">Срез развития, не план и не очки.</p>
      ${grow ? `<section>${clusterBlock(grow)}</section>` : ""}
      ${future ? `<section>${clusterBlock(future)}</section>` : ""}
      ${
        waves.length
          ? `<section><p class="section-label">Волны</p><ul class="soft-list">${waves
              .map((w) => `<li><span>${esc(w)}</span><span></span></li>`)
              .join("")}</ul></section>`
          : ""
      }`;
  }

  function renderBrain(lens) {
    const id = LENSES[lens] ? lens : "self";
    const body =
      id === "reflect" ? reflectHtml() : id === "research" ? researchHtml() : id === "grow" ? growHtml() : personaHtml();
    stage.innerHTML = `<div class="brain">${lensBar(id)}${body}</div>`;
    bindGo(stage);
    if (id === "research") bindResearch(stage);
    if (id === "reflect") bindReflect(stage);
  }

  function paint(spec) {
    const r = spec.route;
    if (r === "brain") {
      const lens = LENSES[spec.lens] ? spec.lens : "self";
      kicker.textContent = LENSES[lens].kicker;
      titleEl.textContent = "Мозг";
    } else {
      const meta = titles[r] || titles.home;
      kicker.textContent = meta[0];
      titleEl.textContent = meta[1];
    }
    document.querySelectorAll(".nav-btn[data-route]").forEach((b) => {
      const on = b.getAttribute("data-route") === r;
      b.classList.toggle("is-active", on);
      if (on) b.setAttribute("aria-current", "page");
      else b.removeAttribute("aria-current");
    });
    stage.classList.toggle("is-wide", r === "capital");
    document.querySelector(".top")?.classList.toggle("is-wide", r === "capital");
    if (r === "home") renderHome();
    else if (r === "brain") renderBrain(spec.lens);
    else if (r === "universe") renderUniverse();
    else if (r === "capital") {
      if (window.LH_CAPITAL) window.LH_CAPITAL.render(stage);
      else stage.innerHTML = "<p class='uni-page-lead'>Модуль Капитал не загружен.</p>";
    }
  }

  function go(input, { skipHash = false } = {}) {
    const spec = input && typeof input === "object" && input.route ? input : parseHash(input);
    const hash = specHash(spec);
    if (!skipHash && location.hash.replace(/^#/, "") !== hash) {
      location.hash = hash;
      return;
    }
    paint(spec);
  }

  const palette = document.getElementById("palette");
  const paletteQ = document.getElementById("paletteQ");
  const paletteList = document.getElementById("paletteList");
  const btnPalette = document.getElementById("btnPalette");
  let paletteIndex = 0;
  let paletteFocus = null;

  function filteredCommands() {
    const q = (paletteQ?.value || "").trim().toLowerCase();
    return COMMANDS.filter(
      (c) => !q || c.label.toLowerCase().includes(q) || c.hint.toLowerCase().includes(q) || c.id.includes(q)
    );
  }

  function paintPalette() {
    const rows = filteredCommands();
    if (paletteIndex >= rows.length) paletteIndex = 0;
    if (!paletteList) return;
    if (!rows.length) {
      paletteList.innerHTML = `<li class="palette-empty">Нет такого перехода</li>`;
      return;
    }
    paletteList.innerHTML = rows
      .map(
        (c, i) =>
          `<li><button type="button" role="option" class="palette-item${i === paletteIndex ? " is-active" : ""}" data-cmd="${esc(
            c.id
          )}" aria-selected="${i === paletteIndex}"><span>${esc(c.label)}</span><span class="hint">${esc(c.hint)}</span></button></li>`
      )
      .join("");
  }

  function openPalette() {
    if (!palette) return;
    paletteFocus = document.activeElement;
    palette.hidden = false;
    if (paletteQ) paletteQ.value = "";
    paletteIndex = 0;
    paintPalette();
    paletteQ?.focus();
  }

  function closePalette() {
    if (!palette || palette.hidden) return;
    palette.hidden = true;
    if (paletteList) paletteList.innerHTML = "";
    if (paletteFocus && typeof paletteFocus.focus === "function") paletteFocus.focus();
  }

  function runPalette() {
    const cmd = filteredCommands()[paletteIndex];
    if (!cmd) return;
    closePalette();
    go(cmd.id);
  }

  paletteQ?.addEventListener("input", () => {
    paletteIndex = 0;
    paintPalette();
  });
  paletteList?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-cmd]");
    if (!btn) return;
    closePalette();
    go(btn.getAttribute("data-cmd"));
  });
  palette?.addEventListener("click", (e) => {
    if (e.target === palette) closePalette();
  });
  btnPalette?.addEventListener("click", () => (palette.hidden ? openPalette() : closePalette()));

  document.querySelectorAll(".nav-btn[data-route]").forEach((b) => {
    b.addEventListener("click", () => go(b.getAttribute("data-route")));
  });
  window.addEventListener("hashchange", () => go(parseHash(), { skipHash: true }));
  window.addEventListener("keydown", (e) => {
    const paletteOpen = palette && !palette.hidden;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      if (paletteOpen) closePalette();
      else openPalette();
      return;
    }
    if (!paletteOpen) return;
    const n = filteredCommands().length;
    if (e.key === "Escape") {
      e.preventDefault();
      closePalette();
    } else if (e.key === "ArrowDown" && n) {
      e.preventDefault();
      paletteIndex = (paletteIndex + 1) % n;
      paintPalette();
    } else if (e.key === "ArrowUp" && n) {
      e.preventDefault();
      paletteIndex = (paletteIndex - 1 + n) % n;
      paintPalette();
    } else if (e.key === "Enter") {
      e.preventDefault();
      runPalette();
    }
  });
  btnRefresh?.addEventListener("click", () => reloadData({ silent: false }));

  // Live poll: if Harvester regenerated snapshot, screens refresh without hard reload
  setInterval(async () => {
    try {
      const res = await fetch(`${snapshotFile()}?t=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) return;
      const next = await res.json();
      const gen = next.meta?.generated_at || next.meta?.asOf;
      if (gen && lastGenerated && gen !== lastGenerated) {
        D = next;
        window.LH_DATA = next;
        updateChrome();
        go(parseHash(), { skipHash: true });
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
      go(parseHash(), { skipHash: true });
    }
  });
})();
