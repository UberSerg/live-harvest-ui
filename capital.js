(() => {
  const API = "http://127.0.0.1:8777";
  const HDR = { "Content-Type": "application/json", "X-LH-Capital": "local" };
  const TABS = [
    ["overview", "Обзор"],
    ["ops", "Операции"],
    ["accounts", "Счета и активы"],
    ["budget", "Бюджет"],
    ["debt", "Обязательства"],
    ["forecast", "Прогноз"],
    ["goals", "Цели / FI"],
  ];

  let state = {
    tab: (() => {
      try {
        return sessionStorage.getItem("lh-cap-tab") || "overview";
      } catch {
        return "overview";
      }
    })(),
    from: "",
    to: "",
    summary: null,
    toastTimer: null,
    periodPreset: "this_month",
    filters: { q: "", type: "", status: "", account: "", category: "" },
    drawer: null,
  };

  function isoLocal(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function monthBounds(offset = 0) {
    const now = new Date();
    const from = new Date(now.getFullYear(), now.getMonth() + offset, 1);
    const to = new Date(now.getFullYear(), now.getMonth() + offset + 1, 0);
    return { from: isoLocal(from), to: isoLocal(to) };
  }

  function setTab(tab, opts = {}) {
    state.tab = tab;
    try {
      sessionStorage.setItem("lh-cap-tab", tab);
    } catch {
      /* ignore */
    }
    if (opts.filters) Object.assign(state.filters, opts.filters);
    renderTabs();
    paintBody();
    requestAnimationFrame(() => {
      const body = document.getElementById("capBody");
      body?.scrollIntoView({ behavior: "smooth", block: "start" });
      document.querySelector(".cap-tab.is-active")?.scrollIntoView({
        behavior: "smooth",
        inline: "nearest",
        block: "nearest",
      });
    });
  }

  const esc = (s) =>
    String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");

  function fmt(minor, currency = "RUB") {
    if (minor == null || Number.isNaN(Number(minor))) return "—";
    const n = Number(minor) / 100;
    return (
      n.toLocaleString("ru-RU", { minimumFractionDigits: 0, maximumFractionDigits: 2 }) +
      " " +
      currency
    );
  }

  function toast(msg, kind = "info") {
    let el = document.getElementById("capToast");
    if (!el) return;
    el.textContent = msg;
    el.className = "cap-toast is-on is-" + kind;
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => el.classList.remove("is-on"), 3200);
  }

  function dialog(opts) {
    return new Promise((resolve) => {
      const root = document.getElementById("capDialog");
      if (!root) {
        resolve(null);
        return;
      }
      root.innerHTML = `
        <div class="cap-dialog-card" role="dialog" aria-modal="true">
          <h3>${esc(opts.title || "Подтверждение")}</h3>
          <p>${esc(opts.body || "")}</p>
          <div class="cap-dialog-actions">
            <button type="button" class="btn-ghost" data-a="cancel">${esc(opts.cancel || "Отмена")}</button>
            <button type="button" class="btn-primary" data-a="ok">${esc(opts.ok || "OK")}</button>
          </div>
        </div>`;
      root.classList.add("is-open");
      const close = (v) => {
        root.classList.remove("is-open");
        root.innerHTML = "";
        resolve(v);
      };
      root.querySelector('[data-a="cancel"]').onclick = () => close(false);
      root.querySelector('[data-a="ok"]').onclick = () => close(true);
      root.onclick = (e) => {
        if (e.target === root) close(false);
      };
    });
  }

  async function api(path, opts = {}) {
    const res = await fetch(API + path, {
      ...opts,
      headers: { ...HDR, ...(opts.headers || {}) },
    });
    const data = await res.json().catch(() => ({ ok: false, error: "bad json" }));
    if (!res.ok || !data.ok) {
      const err = new Error(data.error || res.statusText);
      err.payload = data;
      throw err;
    }
    return data.data !== undefined ? data.data : data;
  }

  let charts = [];
  function killCharts() {
    charts.forEach((c) => c.destroy());
    charts = [];
  }

  function periodDefaults() {
    return monthBounds(0);
  }

  function chartOpts() {
    return {
      responsive: true,
      maintainAspectRatio: true,
      animation: { duration: 280 },
      plugins: { legend: { labels: { color: "#9a9aa3" } } },
      scales: {
        x: { ticks: { color: "#6f737c" }, grid: { color: "#1e222b" } },
        y: { ticks: { color: "#6f737c" }, grid: { color: "#1e222b" } },
      },
    };
  }

  window.LH_CAPITAL = {
    async render(stage) {
      killCharts();
      const p = periodDefaults();
      state.from = p.from;
      state.to = p.to;
      stage.innerHTML = `
        <div class="cap" id="capRoot">
          <header class="cap-chrome">
            <div class="cap-toolbar">
              <div>
                <p class="section-label">Период</p>
                <div class="cap-period">
                  <input type="date" id="capFrom" value="${p.from}" />
                  <span>—</span>
                  <input type="date" id="capTo" value="${p.to}" />
                  <button type="button" class="btn-refresh" id="capReload">Обновить</button>
                </div>
                <div class="cap-presets" id="capPresets"></div>
              </div>
              <div class="cap-mode">
                <button type="button" class="btn-primary" id="capImportBtn">Импорт выписки</button>
                <span class="cap-api" id="capApi">API…</span>
              </div>
            </div>
            <nav class="cap-tabs" id="capTabs" role="tablist" aria-label="Разделы капитала"></nav>
          </header>
          <p class="cap-banner" id="capBanner">Загрузка…</p>
          <div id="capImportReport" class="cap-import-report is-hidden"></div>
          <div id="capBody"></div>
          <aside class="cap-drawer" id="capDrawer" hidden></aside>
          <div class="cap-drawer-backdrop" id="capDrawerBackdrop" hidden></div>
          <div class="cap-toast" id="capToast" role="status"></div>
          <div class="cap-dialog" id="capDialog"></div>
          <div class="cap-dialog" id="capImportModal"></div>
        </div>`;
      renderTabs();
      renderPresets();
      document.getElementById("capReload").onclick = () => reload();
      document.getElementById("capFrom").onchange = () => {
        state.periodPreset = "custom";
        renderPresets();
        reload();
      };
      document.getElementById("capTo").onchange = () => {
        state.periodPreset = "custom";
        renderPresets();
        reload();
      };
      document.getElementById("capImportBtn").onclick = () => openImportModal();
      document.getElementById("capDrawerBackdrop").onclick = () => closeDrawer();
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && state.drawer) closeDrawer();
      });
      await reload();
    },
  };

  function renderPresets() {
    const host = document.getElementById("capPresets");
    if (!host) return;
    const items = [
      ["this_month", "Этот месяц"],
      ["last_month", "Прошлый месяц"],
      ["m3", "3 мес"],
      ["m6", "6 мес"],
      ["year", "Год"],
      ["all", "Весь период"],
    ];
    host.innerHTML = items
      .map(
        ([id, label]) =>
          `<button type="button" class="cap-preset${
            state.periodPreset === id ? " is-active" : ""
          }" data-p="${id}" aria-pressed="${state.periodPreset === id}">${label}</button>`
      )
      .join("");
    host.querySelectorAll("[data-p]").forEach((btn) => {
      btn.onclick = () => {
        const now = new Date();
        const id = btn.getAttribute("data-p");
        let from;
        let to;
        if (id === "this_month") {
          ({ from, to } = monthBounds(0));
        } else if (id === "last_month") {
          ({ from, to } = monthBounds(-1));
        } else if (id === "m3") {
          from = isoLocal(new Date(now.getFullYear(), now.getMonth() - 2, 1));
          to = monthBounds(0).to;
        } else if (id === "m6") {
          from = isoLocal(new Date(now.getFullYear(), now.getMonth() - 5, 1));
          to = monthBounds(0).to;
        } else if (id === "year") {
          from = isoLocal(new Date(now.getFullYear(), 0, 1));
          to = monthBounds(0).to;
        } else {
          from = "2020-01-01";
          to = monthBounds(0).to;
        }
        state.periodPreset = id;
        document.getElementById("capFrom").value = from;
        document.getElementById("capTo").value = to;
        renderPresets();
        reload();
      };
    });
  }

  function openImportModal() {
    const root = document.getElementById("capImportModal");
    const accounts = (state.summary && state.summary.accounts) || [];
    const accOpts = accounts
      .map((a) => `<option value="${esc(a.id)}">${esc(a.name)} · ${esc(a.currency || "RUB")}</option>`)
      .join("");
    root.innerHTML = `
      <div class="cap-dialog-card cap-import-card" role="dialog" aria-modal="true">
        <h3>Импорт банковской выписки</h3>
        <p class="cap-sub">Текст обрабатывается только на localhost. Исходник не пишется в Git и localStorage.</p>
        <label class="cap-sub">Счёт</label>
        <div class="cap-form" style="margin:0">
          <select id="impAcc">${accOpts || '<option value="">нет счетов</option>'}</select>
          <button type="button" class="btn-ghost" id="impNewAcc">Новый счёт</button>
        </div>
        <div id="impNewAccBox" class="is-hidden cap-form">
          <input id="impNewName" placeholder="Название счёта" />
          <select id="impNewCur"><option>RUB</option><option>USD</option><option>EUR</option></select>
          <button type="button" class="btn-primary" id="impCreateAcc">Создать</button>
        </div>
        <label class="cap-sub">Вставь текст выписки (Ctrl+V)</label>
        <textarea id="impText" class="cap-import-ta" placeholder="ДАТА ОПЕРАЦИИ (МСК)…" spellcheck="false"></textarea>
        <label class="cap-sub">или файл TXT / PDF (текстовый слой)</label>
        <input type="file" id="impFile" accept=".txt,.pdf,text/plain,application/pdf" />
        <div class="cap-dialog-actions">
          <button type="button" class="btn-ghost" id="impCancel">Отмена</button>
          <button type="button" class="btn-primary" id="impGo">Импортировать</button>
        </div>
        <p class="cap-sub" id="impStatus"></p>
      </div>`;
    root.classList.add("is-open");
    const close = () => {
      root.classList.remove("is-open");
      root.innerHTML = "";
    };
    root.querySelector("#impCancel").onclick = close;
    root.onclick = (e) => {
      if (e.target === root) close();
    };
    root.querySelector("#impNewAcc").onclick = () => {
      root.querySelector("#impNewAccBox").classList.toggle("is-hidden");
    };
    root.querySelector("#impCreateAcc").onclick = async () => {
      const name = root.querySelector("#impNewName").value.trim();
      if (!name) return toast("Укажи название", "err");
      try {
        const saved = await api("/api/accounts", {
          method: "POST",
          body: JSON.stringify({
            name,
            currency: root.querySelector("#impNewCur").value,
            balance_known: false,
            opening_balance_minor: null,
            account_kind: "checking",
          }),
        });
        const sel = root.querySelector("#impAcc");
        const opt = document.createElement("option");
        opt.value = saved.id;
        opt.textContent = saved.name;
        opt.selected = true;
        sel.appendChild(opt);
        toast("Счёт создан", "ok");
        root.querySelector("#impNewAccBox").classList.add("is-hidden");
      } catch (e) {
        toast(e.message, "err");
      }
    };
    root.querySelector("#impGo").onclick = async () => {
      const status = root.querySelector("#impStatus");
      const account_id = root.querySelector("#impAcc").value;
      if (!account_id) {
        toast("Выбери счёт", "err");
        return;
      }
      status.textContent = "Обработка…";
      const file = root.querySelector("#impFile").files[0];
      let payload = { account_id };
      try {
        if (file) {
          const buf = await file.arrayBuffer();
          const bytes = new Uint8Array(buf);
          let binary = "";
          const chunk = 0x8000;
          for (let i = 0; i < bytes.length; i += chunk) {
            binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
          }
          payload.file_base64 = btoa(binary);
          payload.filename = file.name;
        } else {
          payload.text = root.querySelector("#impText").value;
          if (!payload.text.trim()) {
            toast("Вставь текст или выбери файл", "err");
            status.textContent = "";
            return;
          }
        }
        const data = await api("/api/import/statement", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        // clear sensitive fields from DOM
        root.querySelector("#impText").value = "";
        root.querySelector("#impFile").value = "";
        close();
        showImportReport(data);
        toast(`Импорт: ${data.imported} операций`, "ok");
        await reload();
      } catch (e) {
        status.textContent = "Ошибка: " + e.message;
        toast(e.message, "err");
      }
    };
  }

  function showImportReport(data) {
    const el = document.getElementById("capImportReport");
    if (!el) return;
    el.classList.remove("is-hidden");
    el.innerHTML = `
      <p class="section-label">Отчёт импорта</p>
      <div class="cap-pos">
        <div class="cap-kpi is-positive"><p class="section-label">Импортировано</p><p class="cap-num">${esc(data.imported)}</p></div>
        <div class="cap-kpi"><p class="section-label">Дубликаты</p><p class="cap-num">${esc(data.duplicates_skipped)}</p></div>
        <div class="cap-kpi"><p class="section-label">Категории</p><p class="cap-num">${esc(data.categories_created)}</p></div>
        <div class="cap-kpi"><p class="section-label">Уточнить</p><p class="cap-num">${esc(data.needs_review)}</p></div>
      </div>
      <p class="cap-sub">Период ${esc(data.date_from || "—")} — ${esc(data.date_to || "—")} · batch ${esc(data.batch_id || "")}
        ${data.unrecognized_lines ? " · нераспознанных строк: " + esc(data.unrecognized_lines) : ""}
        ${
          data.batch_id
            ? ` · <button type="button" class="linkish" id="capVoidBatch">отменить пакет</button>`
            : ""
        }
      </p>`;
    const voidBtn = document.getElementById("capVoidBatch");
    if (voidBtn) {
      voidBtn.onclick = async () => {
        if (!(await dialog({ title: "Отменить импорт?", body: "Все операции пакета станут void." }))) return;
        try {
          await api("/api/import/void", {
            method: "POST",
            body: JSON.stringify({ batch_id: data.batch_id }),
          });
          toast("Пакет отменён", "ok");
          el.classList.add("is-hidden");
          await reload();
        } catch (e) {
          toast(e.message, "err");
        }
      };
    }
  }

  function renderTabs() {
    const nav = document.getElementById("capTabs");
    if (!nav) return;
    nav.innerHTML = TABS.map(
      ([id, label]) =>
        `<button type="button" role="tab" class="cap-tab${
          state.tab === id ? " is-active" : ""
        }" data-tab="${id}" aria-selected="${state.tab === id}" id="cap-tab-${id}">${esc(label)}</button>`
    ).join("");
    nav.querySelectorAll("[data-tab]").forEach((btn) => {
      btn.onclick = () => setTab(btn.getAttribute("data-tab"));
    });
  }

  function closeDrawer() {
    state.drawer = null;
    const drawer = document.getElementById("capDrawer");
    const backdrop = document.getElementById("capDrawerBackdrop");
    if (drawer) {
      drawer.hidden = true;
      drawer.innerHTML = "";
      drawer.classList.remove("is-open");
    }
    if (backdrop) backdrop.hidden = true;
  }

  function openOpDrawer({ title, subtitle, ops, openFilters }) {
    const drawer = document.getElementById("capDrawer");
    const backdrop = document.getElementById("capDrawerBackdrop");
    if (!drawer || !backdrop) return;
    const list = ops || [];
    state.drawer = { title, ops: list };
    drawer.hidden = false;
    backdrop.hidden = false;
    drawer.classList.add("is-open");
    drawer.innerHTML = `
      <div class="cap-drawer-head">
        <div>
          <p class="section-label">Операции</p>
          <h3>${esc(title)}</h3>
          ${subtitle ? `<p class="cap-sub">${esc(subtitle)}</p>` : ""}
        </div>
        <button type="button" class="btn-ghost" id="capDrawerClose" aria-label="Закрыть">Закрыть</button>
      </div>
      <div class="cap-drawer-meta">
        <span>${list.length} шт.</span>
        <input type="search" id="capDrawerQ" placeholder="Фильтр в списке…" />
      </div>
      <ul class="cap-op-list" id="capDrawerList">
        ${
          list
            .map((o) => {
              const q = `${o.date || ""} ${o.merchant || ""} ${o.comment || ""} ${o.economic_kind || ""} ${o.type || ""}`;
              return `<li data-q="${esc(q)}">
                <div>
                  <p class="cap-op-date">${esc(o.date || "—")}</p>
                  <p class="cap-op-title">${esc(o.merchant || o.comment || o.economic_kind || o.type || "Операция")}</p>
                  <p class="cap-op-sub">${esc(o.comment || o.bank_category || "")}</p>
                </div>
                <p class="cap-op-amt">${esc(fmt(o.amount_minor, o.currency))}</p>
              </li>`;
            })
            .join("") || `<li class="is-empty"><span>Пусто</span></li>`
        }
      </ul>
      <div class="cap-drawer-foot">
        ${
          openFilters
            ? `<button type="button" class="btn-primary" id="capDrawerToOps">Открыть во вкладке Операции</button>`
            : ""
        }
      </div>`;
    drawer.querySelector("#capDrawerClose").onclick = () => closeDrawer();
    drawer.querySelector("#capDrawerQ").oninput = (e) => {
      const q = e.target.value.trim().toLowerCase();
      drawer.querySelectorAll("#capDrawerList li[data-q]").forEach((li) => {
        li.hidden = q && !(li.getAttribute("data-q") || "").toLowerCase().includes(q);
      });
    };
    const toOps = drawer.querySelector("#capDrawerToOps");
    if (toOps && openFilters) {
      toOps.onclick = () => {
        closeDrawer();
        setTab("ops", { filters: openFilters });
      };
    }
  }

  async function reload() {
    state.from = document.getElementById("capFrom").value;
    state.to = document.getElementById("capTo").value;
    const banner = document.getElementById("capBanner");
    const apiEl = document.getElementById("capApi");
    document.getElementById("stage")?.classList.add("is-wide");
    try {
      await api("/api/health");
      apiEl.textContent = "API · localhost · v0.3";
      apiEl.classList.add("ok");
    } catch {
      apiEl.textContent = "API офлайн";
      apiEl.classList.remove("ok");
      banner.textContent =
        "Локальный Capital API не запущен: python tools/capital_api.py";
      document.getElementById("capBody").innerHTML =
        `<p class="uni-page-lead">Запусти API на localhost, затем обнови.</p>`;
      return;
    }
    try {
      state.summary = await api(
        `/api/summary?from=${encodeURIComponent(state.from)}&to=${encodeURIComponent(state.to)}`
      );
      const fromLabel = state.from;
      const toLabel = state.to;
      banner.innerHTML = `Период ${esc(fromLabel)} → ${esc(toLabel)} · срез ${esc(
        state.summary.as_of
      )} · ${esc(state.summary.base_currency)}`;
      paintBody();
    } catch (e) {
      banner.textContent = "Ошибка API: " + e.message;
    }
  }

  function paintBody() {
    killCharts();
    const body = document.getElementById("capBody");
    if (!state.summary || !body) return;
    const s = state.summary;
    if (state.tab === "overview") body.innerHTML = viewOverview(s);
    else if (state.tab === "ops") body.innerHTML = viewOps(s);
    else if (state.tab === "accounts") body.innerHTML = viewAccounts(s);
    else if (state.tab === "budget") body.innerHTML = viewBudget(s);
    else if (state.tab === "debt") body.innerHTML = viewDebt(s);
    else if (state.tab === "forecast") body.innerHTML = viewForecast(s);
    else if (state.tab === "goals") body.innerHTML = viewGoals(s);
    bindView(state.tab, s);
  }

  function viewOverview(s) {
    const nw = s.net_worth || {};
    const flows = s.flows || {};
    const bank = s.bank_turnover || {};
    const economic = s.economic || {};
    const recon = s.reconciliation || {};
    const monthlyPlan = s.recurring_monthly || {};
    const periodPlan = s.planned_combined || {};
    const budget = s.budget || {};
    const fi = s.fi || {};
    const incomplete = [];
    if (!nw.liquid_complete) incomplete.push("есть счета с неизвестным остатком");
    if (nw.missing_fx?.length) incomplete.push("нет курса: " + nw.missing_fx.join(", "));
    if (budget.unfilled_budget_lines?.length)
      incomplete.push("не заполнены: " + budget.unfilled_budget_lines.join(", "));
    const debtIcon = `<span class="cap-debt-ico" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M12 3l8 4v5c0 5-3.5 8.5-8 9-4.5-.5-8-4-8-9V7l8-4z"/><path d="M9.5 12.5l1.8 1.8 3.7-3.8"/></svg></span>`;
    const reconClass =
      recon.status === "matched" ? "is-ok" : recon.status === "mismatch" ? "is-err" : "is-warn";
    const buckets = economic.buckets || [];
    const planNet = monthlyPlan.net_cashflow_minor || 0;
    const planTone = planNet >= 0 ? "is-positive" : "";
    const liquidTone = "is-positive";
    const monthName = new Date(state.from + "T12:00:00").toLocaleDateString("ru-RU", {
      month: "long",
      year: "numeric",
    });
    return `
      <section class="cap-hero">
        <div>
          <p class="cap-hero-kicker">Курс на независимость · ${esc(monthName)}</p>
          <h2 class="cap-hero-title">Деньги работают на свободу</h2>
          <p class="cap-hero-lead">Смотри ликвидность, план и куда уходит месяц. Долг и чистый капитал — внизу, по запросу.</p>
        </div>
        <div class="cap-hero-stats">
          <div class="cap-hero-stat ${liquidTone}">
            <p class="section-label">Ликвидность</p>
            <p class="cap-num">${esc(fmt(nw.liquid_minor))}</p>
            <p class="cap-sub">${nw.liquid_complete ? "известные счета" : "есть пробелы"}</p>
          </div>
          <div class="cap-hero-stat ${planTone}">
            <p class="section-label">План / мес</p>
            <p class="cap-num">${esc(fmt(planNet))}</p>
            <p class="cap-sub">шаблоны recurring</p>
          </div>
        </div>
      </section>
      ${
        recon.status && recon.status !== "missing" && recon.message
          ? `<p class="cap-recon ${reconClass}" id="capRecon">${esc(recon.message)}</p>`
          : ""
      }
      <section>
        <div class="cap-sec-head">
          <p class="section-label">Движение месяца</p>
          <button type="button" class="linkish" data-goto="ops">Все операции →</button>
        </div>
        <section class="cap-pos cap-pos-4">
          <div class="cap-kpi is-positive cap-click" data-drill="bank_in" tabindex="0">
            <p class="section-label">Поступления</p>
            <p class="cap-num">${esc(fmt(bank.inflow_minor))}</p>
            <p class="cap-sub">${esc(bank.count_in || 0)} · открыть список</p>
          </div>
          <div class="cap-kpi cap-click" data-drill="bank_out" tabindex="0">
            <p class="section-label">Списания</p>
            <p class="cap-num">${esc(fmt(bank.outflow_minor))}</p>
            <p class="cap-sub">${esc(bank.count_out || 0)} · открыть список</p>
          </div>
          <div class="cap-kpi is-positive">
            <p class="section-label">Факт-доходы</p>
            <p class="cap-num">${esc(fmt(flows.income_minor))}</p>
            <p class="cap-sub">экономические</p>
          </div>
          <div class="cap-kpi">
            <p class="section-label">Факт-расходы</p>
            <p class="cap-num">${esc(fmt(flows.expense_minor))}</p>
            <p class="cap-sub">без переводов</p>
          </div>
        </section>
      </section>
      <section class="cap-spend">
        <div class="cap-doughnut-wrap">
          <p class="section-label">Куда уходят деньги</p>
          <div class="cap-doughnut-stage">
            <canvas id="chartExp" height="220"></canvas>
            <div class="cap-doughnut-center" id="capExpCenter">
              <p class="cap-sub">расходы</p>
              <p class="cap-num" id="capExpTotal">—</p>
            </div>
          </div>
        </div>
        <div>
          <p class="section-label">Категории · нажми, чтобы провалиться</p>
          <ul class="cap-legend" id="capExpLegend"></ul>
          <details class="cap-inline-details">
            <summary>Вне графика и классификация</summary>
            <ul class="soft-list" id="capExpExcluded"></ul>
            <ul class="cap-econ-list" id="capEconList">
              ${
                buckets
                  .map(
                    (b) =>
                      `<li class="cap-click" data-econ="${esc(b.id)}"><span>${esc(b.label)} · ${esc(
                        b.count
                      )}</span><span>${esc(fmt(b.amount_minor))}</span></li>`
                  )
                  .join("") || "<li><span>Нет движений за период</span><span></span></li>"
              }
            </ul>
            <p class="cap-sub">Сверка типов ${
              economic.matches_bank_in && economic.matches_bank_out
                ? "ок"
                : "δ in " + fmt(economic.delta_in_minor) + " / out " + fmt(economic.delta_out_minor)
            }</p>
          </details>
        </div>
      </section>
      <section class="cap-charts">
        <div class="cap-chart-box">
          <p class="section-label">Доходы и расходы по месяцам</p>
          <canvas id="chartFlow" height="140"></canvas>
        </div>
        <div class="cap-chart-box">
          <p class="section-label">План против факта</p>
          <canvas id="chartPf" height="140"></canvas>
        </div>
      </section>
      <section class="cap-wide">
        <div>
          <p class="section-label">Требуют уточнения</p>
          <ul class="soft-list" id="capReviewList"></ul>
          <div id="capHarvestQ"></div>
        </div>
        <div>
          <p class="section-label">Финансовая свобода</p>
          ${
            fi.ready
              ? `<p class="cap-num is-life">${esc(((fi.progress_ratio || 0) * 100).toFixed(1))}%</p>
                 <p class="cap-sub">${esc(fmt(fi.current_fi_capital_minor))} из ${esc(
                   fmt(fi.target_capital_minor)
                 )}${
                   fi.months_to_fi_estimate != null ? " · ~" + fi.months_to_fi_estimate + " мес" : ""
                 }</p>
                 <button type="button" class="linkish" data-goto="goals">Цели / FI →</button>`
              : `<p class="cap-sub">Задай цель — вкладка «Цели / FI».</p>
                 <button type="button" class="linkish" data-goto="goals">Настроить →</button>`
          }
          <p class="section-label" style="margin-top:18px">Импорты</p>
          <ul class="soft-list" id="capBatches"></ul>
        </div>
      </section>
      ${
        incomplete.length
          ? `<p class="cap-gaps">Пробелы модели: ${esc(incomplete.join(" · "))}</p>`
          : ""
      }
      <details class="cap-debt">
        <summary>${debtIcon}<span>Обязательства и чистый капитал · без акцента на дашборде</span></summary>
        <div class="cap-debt-body">
          <div class="cap-pos" style="margin-bottom:12px">
            <div class="cap-kpi">
              <p class="section-label">Чистый капитал</p>
              <p class="cap-num">${esc(fmt(nw.net_worth_minor))}</p>
              <p class="cap-sub">ликвидность − обязательства${nw.complete ? "" : " · неполный срез"}</p>
            </div>
            <div class="cap-kpi">
              <p class="section-label">Обязательства</p>
              <p class="cap-num">${esc(fmt(nw.liabilities_minor))}</p>
            </div>
            <div class="cap-kpi">
              <p class="section-label">Экон. поток периода</p>
              <p class="cap-num">${esc(fmt(flows.net_cashflow_minor))}</p>
              <p class="cap-sub">план периода ${esc(fmt(periodPlan.net_cashflow_minor))}</p>
            </div>
          </div>
          <ul class="soft-list">${
            (s.liabilities || [])
              .map(
                (l) =>
                  `<li><span>${esc(l.name)}</span><span>${esc(
                    fmt(l.computed_principal_minor ?? l.principal_remaining_minor)
                  )}</span></li>`
              )
              .join("") || "<li><span>Нет обязательств</span><span></span></li>"
          }</ul>
          <button type="button" class="linkish" data-goto="debt">Раздел обязательств →</button>
        </div>
      </details>`;
  }

  function viewOps(s) {
    const accMap = Object.fromEntries((s.accounts || []).map((a) => [a.id, a]));
    const catMap = Object.fromEntries((s.categories || []).map((c) => [c.id, c]));
    const accOpts = (s.accounts || [])
      .map(
        (a) =>
          `<option value="${esc(a.id)}" ${state.filters.account === a.id ? "selected" : ""}>${esc(
            a.name
          )}</option>`
      )
      .join("");
    const catOpts = (s.categories || [])
      .map(
        (c) =>
          `<option value="${esc(c.id)}" ${state.filters.category === c.id ? "selected" : ""}>${esc(
            c.name
          )}</option>`
      )
      .join("");
    const liaOpts = (s.liabilities || [])
      .map((l) => `<option value="${esc(l.id)}">${esc(l.name)}</option>`)
      .join("");
    const today = isoLocal(new Date());
    const f = state.filters;
    return `
      <section>
        <div class="cap-sec-head">
          <div>
            <p class="section-label">Операции периода</p>
            <h3 class="cap-inline-title">${esc(state.from)} → ${esc(state.to)}</h3>
          </div>
          <button type="button" class="btn-ghost" id="capMat">Материализовать recurring</button>
        </div>
        <div class="cap-ops-tools">
          <input type="search" id="capSearch" placeholder="Поиск…" value="${esc(f.q)}" />
          <select id="fltType">
            <option value="">тип</option>
            ${["income", "expense", "transfer", "debt_principal", "debt_interest"]
              .map((t) => `<option value="${t}" ${f.type === t ? "selected" : ""}>${t}</option>`)
              .join("")}
          </select>
          <select id="fltStatus">
            <option value="">статус</option>
            ${["actual", "planned", "void"]
              .map((t) => `<option value="${t}" ${f.status === t ? "selected" : ""}>${t}</option>`)
              .join("")}
          </select>
          <select id="fltAcc"><option value="">счёт</option>${accOpts}</select>
          <select id="fltCat"><option value="">категория</option>${catOpts}</select>
          ${
            f.q || f.type || f.status || f.account || f.category
              ? `<button type="button" class="btn-ghost" id="capFltClear">Сбросить</button>`
              : ""
          }
        </div>
        <div class="cap-table-wrap">
          <table class="cap-table" id="capTable">
            <thead><tr><th>Дата</th><th>Тип</th><th>Сумма</th><th>Счёт</th><th>Категория</th><th>Статус</th><th>Комментарий</th><th></th></tr></thead>
            <tbody>${(s.transactions || [])
              .map((t) => {
                const acc = accMap[t.account_id]?.name || t.account_id || "—";
                const cat = catMap[t.category_id]?.name || "";
                const q =
                  (t.comment || "") +
                  " " +
                  (t.merchant || "") +
                  " " +
                  t.type +
                  " " +
                  acc +
                  " " +
                  cat;
                return `<tr data-type="${esc(t.type)}" data-status="${esc(t.status)}" data-acc="${esc(
                  t.account_id || ""
                )}" data-cat="${esc(t.category_id || "")}" data-q="${esc(q)}">
                  <td>${esc(t.date)}</td><td>${esc(t.type)}</td>
                  <td>${esc(fmt(t.amount_minor, t.currency))}</td>
                  <td>${esc(acc)}</td><td>${esc(cat || "—")}</td><td>${esc(t.status)}</td>
                  <td>${esc(t.comment || t.merchant || "")}</td>
                  <td class="cap-row-actions">
                    ${t.status === "planned" ? `<button type="button" data-confirm="${esc(t.id)}" class="linkish">факт</button>` : ""}
                    ${t.status !== "void" ? `<button type="button" data-edit="${esc(t.id)}" class="linkish">правка</button>` : ""}
                    ${t.status !== "void" ? `<button type="button" data-dup="${esc(t.id)}" class="linkish">копия</button>` : ""}
                    ${t.status !== "void" ? `<button type="button" data-void="${esc(t.id)}" class="linkish">отмена</button>` : ""}
                  </td></tr>`;
              })
              .join("")}</tbody>
          </table>
        </div>
      </section>
      <details class="cap-inline-details">
        <summary>Добавить операцию вручную</summary>
        <form id="formTx" class="cap-form" style="margin-top:12px">
          <input type="date" name="date" required value="${today}" />
          <select name="type">
            <option value="income">доход</option>
            <option value="expense" selected>расход</option>
            <option value="transfer">перевод</option>
            <option value="debt_principal">тело долга</option>
            <option value="debt_interest">%% по долгу</option>
          </select>
          <select name="status">
            <option value="actual" selected>факт</option>
            <option value="planned">план</option>
          </select>
          <input name="amount" required placeholder="Сумма" />
          <select name="currency"><option>RUB</option><option>USD</option><option>EUR</option></select>
          <select name="account_id" required><option value="">счёт…</option>${(s.accounts || [])
            .map((a) => `<option value="${esc(a.id)}">${esc(a.name)}</option>`)
            .join("")}</select>
          <select name="counterparty_account_id"><option value="">контрагент</option>${(s.accounts || [])
            .map((a) => `<option value="${esc(a.id)}">${esc(a.name)}</option>`)
            .join("")}</select>
          <select name="category_id"><option value="">категория</option>${(s.categories || [])
            .map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`)
            .join("")}</select>
          <select name="liability_id"><option value="">обязательство</option>${liaOpts}</select>
          <input name="comment" placeholder="Комментарий" class="cap-grow" />
          <button type="submit" class="btn-primary">Добавить</button>
        </form>
      </details>
      <details class="cap-inline-details">
        <summary>История исправлений</summary>
        <ul class="soft-list">${
          (s.journal || [])
            .slice(0, 12)
            .map(
              (j) =>
                `<li><span>${esc(j.event)} · ${esc(j.target_id)}</span><span>${esc(j.at || "")}</span></li>`
            )
            .join("") || "<li><span>Пусто</span><span></span></li>"
        }</ul>
      </details>`;
  }

  function viewAccounts(s) {
    const bals = s.balances || {};
    const meta = s.balances_meta || {};
    const today = isoLocal(new Date());
    const accounts = (s.accounts || []).filter((a) => !a.archived);
    const kindLabel = {
      checking: "Кошелёк",
      savings: "Вклады",
      deposit: "Вклады",
      cash: "Наличные",
      broker: "Брокер",
      other: "Другое",
    };
    const groups = [
      ["checking", "Кошелёк"],
      ["savings", "Вклады и накопления"],
      ["cash", "Наличные"],
      ["broker", "Брокерские счета"],
      ["other", "Прочее"],
    ];
    const byKind = {};
    accounts.forEach((a) => {
      let k = a.account_kind || "other";
      if (k === "deposit") k = "savings";
      if (!byKind[k]) byKind[k] = [];
      byKind[k].push(a);
    });
    const knownTotal = accounts.reduce((sum, a) => {
      const m = meta[a.id] || {};
      const bal = bals[a.id];
      if (m.known === false || bal == null) return sum;
      return sum + Number(bal);
    }, 0);
    const assetTotal = (s.assets || []).reduce((sum, a) => sum + (a.value_minor || 0), 0);

    function accountRow(a) {
      const m = meta[a.id] || {};
      const bal = bals[a.id];
      const known = !(m.known === false || bal == null);
      const share = known && knownTotal > 0 ? Math.round((Number(bal) / knownTotal) * 100) : 0;
      const rate =
        a.rate_apr_percent != null ? ` · ${esc(a.rate_apr_percent)}%` : "";
      return `<button type="button" class="cap-asset-row" data-acc-drill="${esc(a.id)}">
        <div class="cap-asset-main">
          <p class="cap-asset-name">${esc(a.name)}</p>
          <p class="cap-asset-meta">${esc(kindLabel[a.account_kind] || a.account_kind)} · ${esc(
            a.currency || "RUB"
          )}${rate}</p>
          <div class="cap-asset-bar" aria-hidden="true"><span style="width:${share}%"></span></div>
        </div>
        <div class="cap-asset-side">
          <p class="cap-num ${known ? "is-life" : ""}">${esc(
            known ? fmt(bal, a.currency) : "неизвестен"
          )}</p>
          <p class="cap-sub">${known ? share + "% ликвидности" : "задай сверку"}</p>
        </div>
      </button>`;
    }

    return `
      <section class="cap-hero cap-hero-compact">
        <div>
          <p class="cap-hero-kicker">Баланс</p>
          <h2 class="cap-hero-title">Счета и активы</h2>
          <p class="cap-hero-lead">Нажми на счёт — список операций за период. Формы спрятаны ниже.</p>
        </div>
        <div class="cap-hero-stats">
          <div class="cap-hero-stat is-positive">
            <p class="section-label">Известная ликвидность</p>
            <p class="cap-num">${esc(fmt(knownTotal))}</p>
          </div>
          <div class="cap-hero-stat">
            <p class="section-label">Активы</p>
            <p class="cap-num">${esc(fmt(assetTotal))}</p>
          </div>
        </div>
      </section>
      <section class="cap-asset-board">
        ${groups
          .map(([k, title]) => {
            const rows = (byKind[k] || []).slice().sort((a, b) => {
              const ba = bals[a.id] == null ? -1 : Number(bals[a.id]);
              const bb = bals[b.id] == null ? -1 : Number(bals[b.id]);
              return bb - ba;
            });
            if (!rows.length) return "";
            const sub = rows.reduce((sum, a) => {
              const bal = bals[a.id];
              const m = meta[a.id] || {};
              if (m.known === false || bal == null) return sum;
              return sum + Number(bal);
            }, 0);
            return `<div class="cap-asset-group">
              <div class="cap-sec-head">
                <p class="section-label">${esc(title)}</p>
                <p class="cap-sub">${esc(fmt(sub))}</p>
              </div>
              <div class="cap-asset-list">${rows.map(accountRow).join("")}</div>
            </div>`;
          })
          .join("")}
        <div class="cap-asset-group">
          <div class="cap-sec-head">
            <p class="section-label">Инвестиции и активы</p>
            <p class="cap-sub">${esc(fmt(assetTotal))}</p>
          </div>
          <div class="cap-asset-list">
            ${
              (s.assets || [])
                .map((a) => {
                  const kindRu =
                    {
                      real_estate: "Недвижимость",
                      broker_portfolio: "Портфель",
                      other: "Другое",
                    }[a.asset_kind] || a.asset_kind;
                  const stRu = a.status === "actual" ? "факт" : a.status === "estimated" ? "оценка" : a.status;
                  return `<div class="cap-asset-row is-static">
                    <div class="cap-asset-main">
                      <p class="cap-asset-name">${esc(a.name)}</p>
                      <p class="cap-asset-meta">${esc(kindRu)} · ${esc(stRu)}</p>
                    </div>
                    <div class="cap-asset-side">
                      <p class="cap-num is-life">${esc(fmt(a.value_minor, a.currency))}</p>
                    </div>
                  </div>`;
                })
                .join("") ||
              `<p class="cap-sub">Пока нет активов в ledger</p>`
            }
          </div>
        </div>
      </section>
      <section class="cap-charts">
        <div class="cap-chart-box">
          <p class="section-label">Структура известных остатков</p>
          <canvas id="chartAssets" height="160"></canvas>
        </div>
      </section>
      <details class="cap-inline-details">
        <summary>Добавить счёт / сверка / актив / курс</summary>
        <div class="cap-wide" style="margin-top:14px">
          <div>
            <form id="formAcc" class="cap-form">
              <input name="name" required placeholder="Новый счёт" />
              <select name="account_kind">
                <option value="checking">расчётный</option>
                <option value="savings">накопительный</option>
                <option value="deposit">депозит</option>
                <option value="cash">наличные</option>
                <option value="broker">брокер</option>
                <option value="other">другое</option>
              </select>
              <select name="currency"><option>RUB</option><option>USD</option><option>EUR</option></select>
              <input name="amount" placeholder="Остаток (пусто = неизвестен)" />
              <button type="submit" class="btn-primary">Создать</button>
            </form>
            <p class="section-label" style="margin-top:16px">Сверка с банком</p>
            <form id="formStmt" class="cap-form">
              <select name="account_id" required><option value="">счёт…</option>${accounts
                .map((a) => `<option value="${esc(a.id)}">${esc(a.name)}</option>`)
                .join("")}</select>
              <input type="date" name="date" value="${today}" />
              <input name="amount" required placeholder="Факт. остаток" />
              <button type="submit" class="btn-primary">Записать сверку</button>
            </form>
          </div>
          <div>
            <form id="formAst" class="cap-form">
              <input name="name" required placeholder="Актив" />
              <select name="asset_kind">
                <option value="real_estate">недвижимость</option>
                <option value="broker_portfolio">брокерский портфель</option>
                <option value="other">другое</option>
              </select>
              <input name="value_minor_major" placeholder="Оценка 0.00" />
              <select name="status"><option value="estimated">оценка</option><option value="actual">факт</option></select>
              <button type="submit" class="btn-primary">Сохранить актив</button>
            </form>
            <p class="section-label" style="margin-top:16px">Курс валюты</p>
            <form id="formFx" class="cap-form">
              <select name="from_currency"><option>USD</option><option>EUR</option></select>
              <span>→ RUB</span>
              <input name="rate" required placeholder="курс" />
              <input type="date" name="date" value="${today}" />
              <button type="submit" class="btn-primary">Сохранить курс</button>
            </form>
            <ul class="soft-list" style="margin-top:10px">${
              (s.fx_rates || [])
                .map(
                  (r) =>
                    `<li><span>${esc(r.from_currency)}/${esc(r.to_currency)} · ${esc(
                      r.date
                    )}</span><span>${esc(r.rate)}</span></li>`
                )
                .join("") ||
              "<li><span>Курсов нет — мультивалюта не суммируется</span><span></span></li>"
            }</ul>
          </div>
        </div>
      </details>`;
  }

  function viewBudget(s) {
    const b = s.budget || {};
    const buckets = b.buckets || {};
    const rows = Object.entries(buckets)
      .map(([k, v]) => {
        const label = {
          income_regular: "Регулярные доходы",
          income_extra: "Доп. доходы",
          expense_fixed: "Постоянные расходы",
          expense_variable: "Переменные расходы",
          expense_irregular: "Нерегулярные",
          savings: "Накопления",
          investments: "Инвестиции",
        }[k] || k;
        return `<tr><td>${esc(label)}</td><td>${esc(fmt(v.plan))}</td><td>${esc(fmt(v.fact))}</td><td>${esc(
          fmt((v.fact || 0) - (v.plan || 0))
        )}</td></tr>`;
      })
      .join("");
    return `
      <section class="cap-pos">
        <div class="cap-kpi"><p class="section-label">Доход план</p><p class="cap-num">${esc(fmt(b.income_plan_minor))}</p></div>
        <div class="cap-kpi"><p class="section-label">Доход факт</p><p class="cap-num">${esc(fmt(b.income_fact_minor))}</p></div>
        <div class="cap-kpi"><p class="section-label">Расход план</p><p class="cap-num">${esc(fmt(b.expense_plan_minor))}</p></div>
        <div class="cap-kpi"><p class="section-label">Расход факт</p><p class="cap-num">${esc(fmt(b.expense_fact_minor))}</p></div>
      </section>
      <p class="cap-gaps">${
        b.free_cash_complete
          ? "Бюджетные статьи заполнены — свободный остаток можно читать как полный."
          : esc(
              "После известных постоянных: " +
                fmt(b.free_after_known_fixed_minor) +
                ". Это не полный free cashflow. Не заполнены: " +
                (b.unfilled_budget_lines || []).join(", ")
            )
      }</p>
      <div class="cap-table-wrap">
        <table class="cap-table">
          <thead><tr><th>Статья</th><th>План</th><th>Факт</th><th>Δ</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <section class="cap-charts">
        <div class="cap-chart-box">
          <p class="section-label">План vs факт по месяцам</p>
          <canvas id="chartBudget" height="150"></canvas>
        </div>
      </section>
      <section>
        <p class="section-label">Регулярные шаблоны</p>
        <ul class="soft-list">${(s.recurring || [])
          .map(
            (r) =>
              `<li><span>${esc(r.name)} · ${esc(r.type)}</span><span>${esc(fmt(r.amount_minor, r.currency))}/мес</span></li>`
          )
          .join("")}</ul>
        <form id="formRec" class="cap-form" style="margin-top:12px">
          <input name="name" required placeholder="Шаблон" />
          <select name="type"><option value="income">доход</option><option value="expense">расход</option></select>
          <input name="amount" required placeholder="Сумма/мес" />
          <select name="account_id"><option value="">счёт…</option>${(s.accounts || [])
            .map((a) => `<option value="${esc(a.id)}">${esc(a.name)}</option>`)
            .join("")}</select>
          <button type="submit" class="btn-primary">Добавить шаблон</button>
        </form>
      </section>`;
  }

  function viewDebt(s) {
    const today = new Date().toISOString().slice(0, 10);
    return `
      <section class="cap-pos">
        <div class="cap-kpi">
          <p class="section-label">Остаток обязательств</p>
          <p class="cap-num">${esc(fmt(s.net_worth?.liabilities_minor))}</p>
        </div>
      </section>
      <ul class="soft-list">${(s.liabilities || [])
        .map(
          (l) =>
            `<li><span>${esc(l.name)} · ${esc(l.status)} · as of ${esc(
              l.principal_as_of || "—"
            )}</span><span>${esc(fmt(l.computed_principal_minor ?? l.principal_remaining_minor))}</span></li>`
        )
        .join("")}</ul>
      <form id="formLiaPrin" class="cap-form">
        <select name="id" required><option value="">обязательство…</option>${(s.liabilities || [])
          .map((l) => `<option value="${esc(l.id)}">${esc(l.name)}</option>`)
          .join("")}</select>
        <input type="date" name="as_of" value="${today}" />
        <input name="amount" required placeholder="Остаток по банку" />
        <button type="submit" class="btn-primary">Обновить остаток (банк)</button>
      </form>
      <p class="cap-sub">Если разбивка ипотечного платежа неизвестна — не выдумываем тело/%%; фиксируем остаток задолженности по выписке.</p>
      <section class="cap-charts">
        <div class="cap-chart-box">
          <p class="section-label">Динамика задолженности (по платежам тела)</p>
          <canvas id="chartDebt" height="140"></canvas>
        </div>
      </section>`;
  }

  function viewForecast(s) {
    const scn = (s.scenarios || [])[0] || {};
    const a = scn.assumptions || {};
    const income = a.monthly_income_minor != null ? a.monthly_income_minor / 100 : (s.recurring_monthly?.income_minor || 0) / 100;
    const expense = a.monthly_expense_minor != null ? a.monthly_expense_minor / 100 : (s.recurring_monthly?.expense_minor || 0) / 100;
    const start = a.starting_capital_minor != null ? a.starting_capital_minor / 100 : (s.net_worth?.liquid_minor || 0) / 100;
    return `
      <section class="cap-panel">
        <h3>Сценарий (не пишет в ledger)</h3>
        <p class="cap-sub">Доходность и инфляция — только если заданы явно. Пустое поле = не применяется.</p>
        <form id="formScn" class="cap-form cap-form-grid">
          <label>Доход / мес<input name="income" value="${esc(income)}" /></label>
          <label>Расход / мес<input name="expense" value="${esc(expense)}" /></label>
          <label>Старт капитала<input name="start" value="${esc(start)}" /></label>
          <label>Доходность % год<input name="yield" placeholder="не задана" value="${esc(a.annual_yield_percent ?? "")}" /></label>
          <label>Инфляция % год<input name="inflation" placeholder="не задана" value="${esc(a.annual_inflation_percent ?? "")}" /></label>
          <label>Цель FI<input name="fi" placeholder="напр. 50000000" value="${esc(
            a.fi_target_minor != null ? a.fi_target_minor / 100 : ""
          )}" /></label>
          <label>Горизонт, мес<input name="months" value="60" /></label>
          <label>Имя сценария<input name="name" value="Пользовательский" /></label>
          <button type="submit" class="btn-primary">Рассчитать</button>
        </form>
      </section>
      <div id="scnOut" class="cap-panel"></div>
      <section class="cap-charts">
        <div class="cap-chart-box"><p class="section-label">Прогноз капитала</p><canvas id="chartScn" height="160"></canvas></div>
      </section>`;
  }

  function viewGoals(s) {
    const fi = s.fi || {};
    const fp = s.fi_params || {};
    return `
      <section class="cap-hero">
        <div>
          <p class="cap-hero-kicker">Финансовая независимость</p>
          <h2 class="cap-hero-title">Цель, а не оценка квартиры</h2>
          <p class="cap-hero-lead">Собственное жильё не входит в FI-капитал, пока ты явно не включишь его. Параметры подтверждаешь ты.</p>
        </div>
        <div class="cap-hero-stat">
          <p class="section-label">Прогресс</p>
          <p class="cap-num">${fi.ready ? esc(((fi.progress_ratio || 0) * 100).toFixed(1) + "%") : "—"}</p>
        </div>
      </section>
      <form id="formFi" class="cap-form cap-form-grid">
        <label>Целевой капитал, ₽<input name="target" value="${esc(
          fp.target_capital_minor != null ? fp.target_capital_minor / 100 : "50000000"
        )}" /></label>
        <label>FI-капитал сейчас (если знаешь)<input name="current" placeholder="пусто = ликвидность" value="${esc(
          fp.fi_capital_minor != null ? fp.fi_capital_minor / 100 : ""
        )}" /></label>
        <label>Накопления / мес<input name="savings" value="${esc(
          fp.monthly_savings_minor != null ? fp.monthly_savings_minor / 100 : ""
        )}" /></label>
        <label>Safe withdrawal % / год<input name="swr" placeholder="напр. 4" value="${esc(fp.safe_withdrawal_percent ?? "")}" /></label>
        <label>Доходность % / год<input name="yield" placeholder="не задана" value="${esc(fp.annual_yield_percent ?? "")}" /></label>
        <label class="cap-check"><input type="checkbox" name="home" ${fp.include_home_in_fi ? "checked" : ""}/> включать жильё в FI</label>
        <button type="submit" class="btn-primary">Сохранить параметры FI</button>
      </form>
      ${
        fi.ready
          ? `<section class="cap-pos">
              <div class="cap-kpi"><p class="section-label">Цель</p><p class="cap-num">${esc(fmt(fi.target_capital_minor))}</p></div>
              <div class="cap-kpi is-positive"><p class="section-label">FI-капитал</p><p class="cap-num">${esc(fmt(fi.current_fi_capital_minor))}</p></div>
              <div class="cap-kpi"><p class="section-label">Пассив / мес</p><p class="cap-num">${esc(fmt(fi.potential_passive_monthly_minor))}</p><p class="cap-sub">если задан SWR</p></div>
              <div class="cap-kpi"><p class="section-label">Срок</p><p class="cap-num">${
                fi.months_to_fi_estimate != null ? esc(fi.months_to_fi_estimate + " мес") : "—"
              }</p></div>
            </section>`
          : `<p class="cap-gaps">${esc(fi.reason || "задай параметры")}</p>`
      }
      <section>
        <p class="section-label">Финансовые цели</p>
        <ul class="soft-list">${(s.goals || [])
          .map(
            (g) =>
              `<li><span>${esc(g.name)}${g.harvest_link ? " · " + esc(g.harvest_link) : ""}</span><span>${esc(
                fmt(g.target_minor, g.currency)
              )}</span></li>`
          )
          .join("") || "<li><span>Пока нет отдельных goal-записей в ledger</span><span></span></li>"}</ul>
        <form id="formGoal" class="cap-form">
          <input name="name" required placeholder="Цель" />
          <input name="target" placeholder="Сумма" />
          <input name="harvest_link" placeholder="[[ссылка Harvest]]" />
          <button type="submit" class="btn-primary">Добавить цель</button>
        </form>
      </section>`;
  }

  function bindView(tab, s) {
    if (tab === "overview") {
      renderOverviewCharts(s);
      bindOverviewExtras(s);
      return;
    }
    if (tab === "ops") {
      bindOps(s);
      return;
    }
    if (tab === "accounts") {
      bindAccounts(s);
      renderAssetChart(s);
      return;
    }
    if (tab === "budget") {
      bindBudget(s);
      renderBudgetChart(s);
      return;
    }
    if (tab === "debt") {
      bindDebt(s);
      renderDebtChart(s);
      return;
    }
    if (tab === "forecast") {
      bindForecast(s);
      return;
    }
    if (tab === "goals") {
      bindGoals(s);
    }
  }

  function applyFilters() {
    const q = (document.getElementById("capSearch")?.value || "").trim().toLowerCase();
    const type = document.getElementById("fltType")?.value || "";
    const status = document.getElementById("fltStatus")?.value || "";
    const acc = document.getElementById("fltAcc")?.value || "";
    const cat = document.getElementById("fltCat")?.value || "";
    state.filters = { q, type, status, account: acc, category: cat };
    document.querySelectorAll("#capTable tbody tr").forEach((tr) => {
      const ok =
        (!q || (tr.getAttribute("data-q") || "").toLowerCase().includes(q)) &&
        (!type || tr.getAttribute("data-type") === type) &&
        (!status || tr.getAttribute("data-status") === status) &&
        (!acc || tr.getAttribute("data-acc") === acc) &&
        (!cat || tr.getAttribute("data-cat") === cat);
      tr.style.display = ok ? "" : "none";
    });
  }

  function bindOps(s) {
    ["capSearch", "fltType", "fltStatus", "fltAcc", "fltCat"].forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.oninput = applyFilters;
      el.onchange = applyFilters;
    });
    document.getElementById("capFltClear")?.addEventListener("click", () => {
      state.filters = { q: "", type: "", status: "", account: "", category: "" };
      paintBody();
    });
    applyFilters();
    const form = document.getElementById("formTx");
    if (form) {
      form.onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(form);
        const type = fd.get("type");
        const payload = {
          type,
          date: fd.get("date"),
          amount: fd.get("amount"),
          currency: fd.get("currency") || "RUB",
          account_id: fd.get("account_id"),
          category_id: fd.get("category_id") || null,
          liability_id: fd.get("liability_id") || null,
          comment: fd.get("comment") || "",
          status: fd.get("status") || "actual",
        };
        if (type === "transfer") {
          payload.counterparty_account_id = fd.get("counterparty_account_id");
          if (!payload.counterparty_account_id) {
            toast("Для перевода укажи счёт-получатель", "err");
            return;
          }
        }
        try {
          await api("/api/transactions", { method: "POST", body: JSON.stringify(payload) });
          toast("Операция сохранена", "ok");
          await reload();
        } catch (err) {
          toast(
            "Ошибка: " + err.message + (err.payload?.duplicate_id ? " (дубль " + err.payload.duplicate_id + ")" : ""),
            "err"
          );
        }
      };
    }
    document.getElementById("capMat")?.addEventListener("click", async () => {
      const ym = state.to.slice(0, 7);
      try {
        const data = await api("/api/recurring/materialize", {
          method: "POST",
          body: JSON.stringify({ month: ym }),
        });
        toast("Создано плановых: " + (data.count ?? data.length ?? 0), "ok");
        await reload();
      } catch (e) {
        toast(e.message, "err");
      }
    });
    ["capSearch", "fltType", "fltStatus", "fltAcc"].forEach((id) => {
      document.getElementById(id)?.addEventListener("input", applyFilters);
      document.getElementById(id)?.addEventListener("change", applyFilters);
    });
    document.querySelectorAll("[data-void]").forEach((btn) => {
      btn.onclick = async () => {
        if (!(await dialog({ title: "Отменить операцию?", body: "Статус станет void, история сохранится." }))) return;
        try {
          await api("/api/transactions/void", {
            method: "POST",
            body: JSON.stringify({ id: btn.getAttribute("data-void"), reason: "ui void" }),
          });
          toast("Отменено", "ok");
          await reload();
        } catch (e) {
          toast(e.message, "err");
        }
      };
    });
    document.querySelectorAll("[data-confirm]").forEach((btn) => {
      btn.onclick = async () => {
        if (!(await dialog({ title: "Подтвердить как факт?", body: "Плановая операция станет actual." }))) return;
        try {
          await api("/api/transactions/confirm", {
            method: "POST",
            body: JSON.stringify({ id: btn.getAttribute("data-confirm") }),
          });
          toast("Подтверждено", "ok");
          await reload();
        } catch (e) {
          toast(e.message, "err");
        }
      };
    });
    document.querySelectorAll("[data-dup]").forEach((btn) => {
      btn.onclick = async () => {
        try {
          await api("/api/transactions/duplicate", {
            method: "POST",
            body: JSON.stringify({ id: btn.getAttribute("data-dup") }),
          });
          toast("Копия создана", "ok");
          await reload();
        } catch (e) {
          toast(e.message, "err");
        }
      };
    });
    document.querySelectorAll("[data-edit]").forEach((btn) => {
      btn.onclick = async () => {
        const id = btn.getAttribute("data-edit");
        const tx = (s.transactions || []).find((t) => t.id === id);
        if (!tx) return;
        const patch = await editDialog(tx);
        if (!patch) return;
        try {
          await api("/api/transactions/correct", {
            method: "POST",
            body: JSON.stringify({ id, reason: patch.reason, patch: { amount_minor: patch.amount_minor, comment: patch.comment } }),
          });
          toast("Исправлено", "ok");
          await reload();
        } catch (e) {
          toast(e.message, "err");
        }
      };
    });
  }

  function editDialog(tx) {
    return new Promise((resolve) => {
      const root = document.getElementById("capDialog");
      if (!root) {
        resolve(null);
        return;
      }
      root.innerHTML = `
        <div class="cap-dialog-card" role="dialog" aria-modal="true">
          <h3>Исправить операцию</h3>
          <p>${esc(tx.type)} · ${esc(tx.date)}</p>
          <label class="cap-sub">Сумма</label>
          <input id="capEditAmt" value="${esc(String((tx.amount_minor || 0) / 100))}" />
          <label class="cap-sub">Комментарий</label>
          <input id="capEditComment" value="${esc(tx.comment || "")}" />
          <label class="cap-sub">Причина</label>
          <input id="capEditReason" value="правка UI" />
          <div class="cap-dialog-actions">
            <button type="button" class="btn-ghost" data-a="cancel">Отмена</button>
            <button type="button" class="btn-primary" data-a="ok">Сохранить</button>
          </div>
        </div>`;
      root.classList.add("is-open");
      const close = (v) => {
        root.classList.remove("is-open");
        root.innerHTML = "";
        resolve(v);
      };
      root.querySelector('[data-a="cancel"]').onclick = () => close(null);
      root.querySelector('[data-a="ok"]').onclick = () => {
        const amount = Number(String(document.getElementById("capEditAmt").value || "").replace(",", "."));
        if (Number.isNaN(amount)) {
          toast("Некорректная сумма", "err");
          return;
        }
        close({
          amount_minor: Math.round(amount * 100),
          comment: document.getElementById("capEditComment").value,
          reason: document.getElementById("capEditReason").value || "правка UI",
        });
      };
      root.onclick = (e) => {
        if (e.target === root) close(null);
      };
    });
  }

  function bindAccounts(s) {
    document.querySelectorAll("[data-acc-drill]").forEach((btn) => {
      btn.onclick = () => {
        const id = btn.getAttribute("data-acc-drill");
        const acc = (s.accounts || []).find((a) => a.id === id);
        const ops = (s.transactions || []).filter(
          (t) => t.account_id === id && t.status !== "void"
        );
        openOpDrawer({
          title: acc?.name || "Счёт",
          subtitle: `${state.from} → ${state.to}`,
          ops,
          openFilters: { account: id, status: "actual" },
        });
      };
    });
    const formAcc = document.getElementById("formAcc");
    if (formAcc) {
      formAcc.onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(formAcc);
        const amount = String(fd.get("amount") || "").trim();
        const payload = {
          name: fd.get("name"),
          account_kind: fd.get("account_kind"),
          currency: fd.get("currency") || "RUB",
          status: "actual",
        };
        if (amount === "") {
          payload.balance_known = false;
          payload.opening_balance_minor = null;
        } else {
          payload.amount = amount;
          payload.balance_known = true;
        }
        try {
          await api("/api/accounts", { method: "POST", body: JSON.stringify(payload) });
          toast("Счёт создан", "ok");
          await reload();
        } catch (err) {
          toast(err.message, "err");
        }
      };
    }
    document.getElementById("formStmt")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      try {
        await api("/api/accounts/statement", {
          method: "POST",
          body: JSON.stringify({
            account_id: fd.get("account_id"),
            date: fd.get("date"),
            amount: fd.get("amount"),
          }),
        });
        toast("Сверка записана", "ok");
        await reload();
      } catch (err) {
        toast(err.message, "err");
      }
    });
    document.getElementById("formAst")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const major = Number(String(fd.get("value_minor_major") || "0").replace(",", "."));
      try {
        await api("/api/assets", {
          method: "POST",
          body: JSON.stringify({
            name: fd.get("name"),
            asset_kind: fd.get("asset_kind"),
            value_minor: Math.round(major * 100),
            status: fd.get("status"),
          }),
        });
        toast("Актив сохранён", "ok");
        await reload();
      } catch (err) {
        toast(err.message, "err");
      }
    });
    document.getElementById("formFx")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      try {
        await api("/api/fx", {
          method: "POST",
          body: JSON.stringify({
            from_currency: fd.get("from_currency"),
            to_currency: "RUB",
            rate: fd.get("rate"),
            date: fd.get("date"),
          }),
        });
        toast("Курс сохранён", "ok");
        await reload();
      } catch (err) {
        toast(err.message, "err");
      }
    });
  }

  function bindBudget() {
    document.getElementById("formRec")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      try {
        await api("/api/recurring", {
          method: "POST",
          body: JSON.stringify({
            name: fd.get("name"),
            type: fd.get("type"),
            amount: fd.get("amount"),
            account_id: fd.get("account_id") || null,
            status: "planned",
            cadence: "monthly",
          }),
        });
        toast("Шаблон сохранён", "ok");
        await reload();
      } catch (err) {
        toast(err.message, "err");
      }
    });
  }

  function bindDebt() {
    document.getElementById("formLiaPrin")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const major = Number(String(fd.get("amount")).replace(",", "."));
      try {
        await api("/api/liabilities/principal", {
          method: "POST",
          body: JSON.stringify({
            id: fd.get("id"),
            as_of: fd.get("as_of"),
            principal_remaining_minor: Math.round(major * 100),
            note: "UI bank update",
          }),
        });
        toast("Остаток обновлён", "ok");
        await reload();
      } catch (err) {
        toast(err.message, "err");
      }
    });
  }

  function bindForecast() {
    document.getElementById("formScn")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const toMinor = (v) => Math.round(Number(String(v || "0").replace(",", ".")) * 100);
      const assumptions = {
        monthly_income_minor: toMinor(fd.get("income")),
        monthly_expense_minor: toMinor(fd.get("expense")),
        starting_capital_minor: toMinor(fd.get("start")),
      };
      const y = String(fd.get("yield") || "").trim();
      const inf = String(fd.get("inflation") || "").trim();
      const fi = String(fd.get("fi") || "").trim();
      if (y !== "") assumptions.annual_yield_percent = Number(y.replace(",", "."));
      if (inf !== "") assumptions.annual_inflation_percent = Number(inf.replace(",", "."));
      if (fi !== "") assumptions.fi_target_minor = toMinor(fi);
      try {
        await api("/api/scenarios", {
          method: "POST",
          body: JSON.stringify({
            name: fd.get("name") || "Пользовательский",
            assumptions,
            horizon_months: Number(fd.get("months") || 60),
          }),
        });
        const proj = await api("/api/scenarios/project", {
          method: "POST",
          body: JSON.stringify({ assumptions, horizon_months: Number(fd.get("months") || 60) }),
        });
        const out = document.getElementById("scnOut");
        if (!proj.ok) {
          out.innerHTML = `<p class="cap-gaps">${esc(proj.error)}</p>`;
          return;
        }
        out.innerHTML = `<p class="cap-num">${esc(fmt(proj.ending_capital_minor))}</p>
          <p class="cap-sub">к концу горизонта · до FI: ${
            proj.months_to_fi != null ? esc(proj.months_to_fi + " мес") : "—"
          } · yield ${proj.assumptions.yield_applied ? "включён" : "не задан"}</p>`;
        killCharts();
        const ctx = document.getElementById("chartScn");
        if (ctx && typeof Chart !== "undefined") {
          const series = proj.series || [];
          charts.push(
            new Chart(ctx, {
              type: "line",
              data: {
                labels: series.map((r) => r.month_index),
                datasets: [
                  {
                    label: "Капитал",
                    data: series.map((r) => r.capital_minor / 100),
                    borderColor: "#5cb88a",
                    tension: 0.2,
                  },
                ],
              },
              options: chartOpts(),
            })
          );
        }
        toast("Прогноз готов", "ok");
      } catch (err) {
        toast(err.message, "err");
      }
    });
  }

  function bindGoals() {
    document.getElementById("formFi")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const toMinor = (v) => {
        const s = String(v || "").trim();
        if (!s) return null;
        return Math.round(Number(s.replace(",", ".")) * 100);
      };
      const payload = {
        target_capital_minor: toMinor(fd.get("target")),
        fi_capital_minor: toMinor(fd.get("current")),
        monthly_savings_minor: toMinor(fd.get("savings")),
        include_home_in_fi: !!fd.get("home"),
        harvest_link: "[[Финансовая независимость и капитал]]",
      };
      const swr = String(fd.get("swr") || "").trim();
      const y = String(fd.get("yield") || "").trim();
      if (swr) payload.safe_withdrawal_percent = Number(swr.replace(",", "."));
      if (y) payload.annual_yield_percent = Number(y.replace(",", "."));
      try {
        await api("/api/fi", { method: "POST", body: JSON.stringify(payload) });
        toast("Параметры FI сохранены", "ok");
        await reload();
      } catch (err) {
        toast(err.message, "err");
      }
    });
    document.getElementById("formGoal")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const t = String(fd.get("target") || "").trim();
      try {
        await api("/api/goals", {
          method: "POST",
          body: JSON.stringify({
            name: fd.get("name"),
            target_minor: t ? Math.round(Number(t.replace(",", ".")) * 100) : null,
            harvest_link: fd.get("harvest_link") || null,
          }),
        });
        toast("Цель добавлена", "ok");
        await reload();
      } catch (err) {
        toast(err.message, "err");
      }
    });
  }

  const DONUT_COLORS = ["#c9a27a", "#5cb88a", "#7eb6d9", "#d48a78", "#9a9aa3", "#cbb46a", "#8a7ec8", "#6aa8a1", "#c47a9a", "#a3b56e"];

  function bindOverviewExtras(s) {
    const bank = s.bank_turnover || {};
    const economic = s.economic || {};
    document.querySelectorAll("[data-goto]").forEach((el) => {
      el.onclick = () => setTab(el.getAttribute("data-goto"));
    });
    document.querySelectorAll("[data-drill]").forEach((el) => {
      const open = () => {
        const kind = el.getAttribute("data-drill");
        const ops = kind === "bank_in" ? bank.operations_in : bank.operations_out;
        openOpDrawer({
          title: kind === "bank_in" ? "Поступления" : "Списания",
          subtitle: `${state.from} → ${state.to}`,
          ops,
          openFilters: { type: kind === "bank_in" ? "income" : "expense", status: "actual" },
        });
      };
      el.onclick = open;
      el.onkeydown = (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      };
    });
    document.querySelectorAll("[data-econ]").forEach((el) => {
      el.onclick = () => {
        const id = el.getAttribute("data-econ");
        const b = (economic.buckets || []).find((x) => x.id === id);
        if (b)
          openOpDrawer({
            title: b.label,
            subtitle: "экономическая классификация",
            ops: b.operations,
          });
      };
    });
    const review = s.needs_review || [];
    const ul = document.getElementById("capReviewList");
    if (ul) {
      if (!review.length) ul.innerHTML = "<li><span>Нет неоднозначных операций</span><span></span></li>";
      else
        ul.innerHTML = review
          .slice(0, 8)
          .map(
            (t) =>
              `<li><span>${esc(t.date)} · ${esc(t.merchant || t.bank_category || t.type)}</span><span>${esc(
                fmt(t.amount_minor, t.currency)
              )}</span></li>`
          )
          .join("");
    }
    const batches = s.import_batches || [];
    const bu = document.getElementById("capBatches");
    if (bu) {
      bu.innerHTML = batches.length
        ? batches
            .slice(0, 5)
            .map(
              (b) =>
                `<li><span>${esc(b.imported_at || "")} · ${esc(b.imported_count)} ops</span><span>${esc(
                  b.batch_id
                )}</span></li>`
            )
            .join("")
        : "<li><span>Импортов пока нет</span><span></span></li>";
    }
    // one harvester question from latest batch
    const qHost = document.getElementById("capHarvestQ");
    const q =
      (batches[0] && batches[0].harvester_queue && batches[0].harvester_queue[0]) || null;
    if (qHost && q) {
      qHost.innerHTML = `
        <p class="section-label" style="margin-top:16px">Financial Harvester</p>
        <p class="cap-gaps">${esc(q.question)}</p>
        <form id="capHqForm" class="cap-form">
          <select name="kind">
            <option value="purchase|expense">покупка / расход</option>
            <option value="salary|income">зарплата</option>
            <option value="other_income|income">прочий доход</option>
            <option value="transfer_internal|expense">перевод себе</option>
            <option value="transfer_other|expense">перевод людям</option>
            <option value="cashback|income">кешбэк</option>
          </select>
          <input name="cat" placeholder="Категория Harvest" value="${esc(q.bank_category || "Прочее")}" />
          <label class="cap-check"><input type="checkbox" name="remember" checked /> запомнить правило</label>
          <button type="submit" class="btn-primary">Применить ко всем (${esc(q.count)})</button>
        </form>`;
      qHost.querySelector("#capHqForm").onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const [economic_kind, ledger_type] = String(fd.get("kind")).split("|");
        const remember = fd.get("remember")
          ? {
              match: "merchant",
              pattern: (q.merchant || q.bank_category || "").toLowerCase(),
              category_name: fd.get("cat"),
              economic_kind,
              ledger_type,
            }
          : null;
        try {
          await api("/api/import/classify", {
            method: "POST",
            body: JSON.stringify({
              fingerprints: q.fingerprints || [],
              category_name: fd.get("cat"),
              economic_kind,
              ledger_type,
              remember,
            }),
          });
          toast("Классификация обновлена", "ok");
          await reload();
        } catch (err) {
          toast(err.message, "err");
        }
      };
    }
  }

  function renderOverviewCharts(s) {
    if (typeof Chart === "undefined") return;
    const monthly = s.monthly || [];
    const planned = s.monthly_planned || [];
    const ctx1 = document.getElementById("chartFlow");
    if (ctx1) {
      charts.push(
        new Chart(ctx1, {
          type: "bar",
          data: {
            labels: monthly.map((m) => m.month),
            datasets: [
              { label: "Доход", data: monthly.map((m) => m.income_minor / 100), backgroundColor: "rgba(92,184,138,.55)" },
              { label: "Расход", data: monthly.map((m) => m.expense_minor / 100), backgroundColor: "rgba(212,138,120,.55)" },
            ],
          },
          options: chartOpts(),
        })
      );
    }
    const ctxPf = document.getElementById("chartPf");
    if (ctxPf) {
      const labels = monthly.map((m) => m.month);
      const planMap = Object.fromEntries(planned.map((m) => [m.month, m]));
      charts.push(
        new Chart(ctxPf, {
          type: "line",
          data: {
            labels,
            datasets: [
              {
                label: "Факт net",
                data: monthly.map((m) => m.net_cashflow_minor / 100),
                borderColor: "#5cb88a",
                tension: 0.2,
              },
              {
                label: "План net",
                data: labels.map((m) => (planMap[m]?.net_cashflow_minor || 0) / 100),
                borderColor: "#7eb6d9",
                borderDash: [4, 4],
                tension: 0.2,
              },
            ],
          },
          options: chartOpts(),
        })
      );
    }
    renderExpenseDoughnut(s.expense_analytics || {});
  }

  function renderExpenseDoughnut(ea) {
    const ctx2 = document.getElementById("chartExp");
    const legend = document.getElementById("capExpLegend");
    const totalEl = document.getElementById("capExpTotal");
    if (!ctx2) return;
    const segments = ea.segments || [];
    if (totalEl) totalEl.textContent = fmt(ea.total_expense_minor || 0);
    const excl = document.getElementById("capExpExcluded");
    if (excl) {
      const rows = ea.excluded || [];
      excl.innerHTML = rows.length
        ? rows
            .map(
              (r) =>
                `<li><span>${esc(r.label)} · ${esc(r.count)}</span><span>${esc(fmt(r.amount_minor))}</span></li>`
            )
            .join("") +
          `<li><span>Банковские списания всего</span><span>${esc(fmt(ea.bank_outflow_minor))}</span></li>`
        : `<li><span>Все списания в графике</span><span>${esc(fmt(ea.bank_outflow_minor))}</span></li>`;
    }
    if (!segments.length) {
      if (legend) legend.innerHTML = "<li>Нет подтверждённых расходов за период</li>";
      return;
    }
    if (legend) {
      legend.innerHTML = segments
        .map(
          (seg, i) =>
            `<li data-seg="${i}"><span class="cap-swatch" style="background:${DONUT_COLORS[i % DONUT_COLORS.length]}"></span>
              <span>${esc(seg.name)}</span>
              <span>${esc(fmt(seg.amount_minor))} · ${esc(((seg.share || 0) * 100).toFixed(1))}%</span></li>`
        )
        .join("");
      legend.querySelectorAll("[data-seg]").forEach((li) => {
        li.onclick = () => showDrill(segments[Number(li.getAttribute("data-seg"))]);
      });
    }
    const chart = new Chart(ctx2, {
      type: "doughnut",
      data: {
        labels: segments.map((s) => s.name),
        datasets: [
          {
            data: segments.map((s) => s.amount_minor / 100),
            backgroundColor: segments.map((_, i) => DONUT_COLORS[i % DONUT_COLORS.length]),
            borderWidth: 0,
          },
        ],
      },
      options: {
        cutout: "68%",
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const seg = segments[ctx.dataIndex];
                return `${seg.name}: ${fmt(seg.amount_minor)} (${((seg.share || 0) * 100).toFixed(1)}%)`;
              },
            },
          },
        },
        onClick: (_e, els) => {
          if (!els.length) return;
          showDrill(segments[els[0].index]);
        },
      },
    });
    charts.push(chart);
  }

  function showDrill(seg) {
    if (!seg) return;
    openOpDrawer({
      title: seg.name,
      subtitle: `${fmt(seg.amount_minor)} · ${(((seg.share || 0) * 100).toFixed(1))}% расходов`,
      ops: seg.operations || [],
      openFilters: {
        category: seg.category_id && seg.category_id !== "uncategorized" ? seg.category_id : "",
        type: "expense",
        status: "actual",
      },
    });
  }

  function showOpDrill(ops, title) {
    openOpDrawer({ title, ops: ops || [] });
  }

  function renderAssetChart(s) {
    if (typeof Chart === "undefined") return;
    const ctx = document.getElementById("chartAssets");
    if (!ctx) return;
    const meta = s.balances_meta || {};
    const labels = [];
    const data = [];
    Object.values(meta).forEach((m) => {
      if (!m.known || m.balance_minor == null) return;
      labels.push(m.name || "счёт");
      data.push(m.balance_minor / 100);
    });
    (s.assets || []).forEach((a) => {
      if (a.value_minor == null) return;
      labels.push(a.name);
      data.push(a.value_minor / 100);
    });
    if (!labels.length) return;
    charts.push(
      new Chart(ctx, {
        type: "doughnut",
        data: {
          labels,
          datasets: [{ data, backgroundColor: ["#c9a27a", "#5cb88a", "#7eb6d9", "#d48a78", "#9a9aa3", "#cbb46a", "#8a7ec8"] }],
        },
        options: { plugins: { legend: { labels: { color: "#9a9aa3" } } } },
      })
    );
  }

  function renderBudgetChart(s) {
    if (typeof Chart === "undefined") return;
    const ctx = document.getElementById("chartBudget");
    if (!ctx) return;
    const monthly = s.monthly || [];
    const planned = s.monthly_planned || [];
    const planMap = Object.fromEntries(planned.map((m) => [m.month, m]));
    charts.push(
      new Chart(ctx, {
        type: "bar",
        data: {
          labels: monthly.map((m) => m.month),
          datasets: [
            { label: "Факт расход", data: monthly.map((m) => m.expense_minor / 100), backgroundColor: "rgba(212,138,120,.55)" },
            {
              label: "План расход",
              data: monthly.map((m) => (planMap[m.month]?.expense_minor || 0) / 100),
              backgroundColor: "rgba(126,182,217,.45)",
            },
          ],
        },
        options: chartOpts(),
      })
    );
  }

  function renderDebtChart(s) {
    if (typeof Chart === "undefined") return;
    const ctx = document.getElementById("chartDebt");
    if (!ctx) return;
    const lia = (s.liabilities || [])[0];
    if (!lia) return;
    const base = lia.principal_remaining_minor;
    const asOf = lia.principal_as_of || "2026-01-01";
    const pays = (s.transactions || [])
      .filter((t) => t.type === "debt_principal" && t.status === "actual" && t.liability_id === lia.id && t.date > asOf)
      .sort((a, b) => (a.date > b.date ? 1 : -1));
    let rem = base;
    const labels = [asOf];
    const data = [base / 100];
    pays.forEach((p) => {
      rem -= p.principal_portion_minor != null ? p.principal_portion_minor : p.amount_minor;
      labels.push(p.date);
      data.push(Math.max(0, rem) / 100);
    });
    if (labels.length < 2) {
      // no history — don't fake a series
      return;
    }
    charts.push(
      new Chart(ctx, {
        type: "line",
        data: { labels, datasets: [{ label: lia.name, data, borderColor: "#d48a78", tension: 0.15 }] },
        options: chartOpts(),
      })
    );
  }
})();
