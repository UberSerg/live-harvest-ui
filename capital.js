(() => {
  const API = "http://127.0.0.1:8777";
  const HDR = { "Content-Type": "application/json", "X-LH-Capital": "local" };

  const esc = (s) =>
    String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");

  function fmt(minor, currency = "RUB") {
    if (minor == null || Number.isNaN(minor)) return "—";
    const n = Number(minor) / 100;
    return (
      n.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) +
      " " +
      currency
    );
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
    return data.data;
  }

  let charts = [];
  function killCharts() {
    charts.forEach((c) => c.destroy());
    charts = [];
  }

  function periodDefaults() {
    const to = new Date();
    const from = new Date(to.getFullYear(), to.getMonth() - 5, 1);
    const iso = (d) => d.toISOString().slice(0, 10);
    return { from: iso(from), to: iso(to) };
  }

  window.LH_CAPITAL = {
    async render(stage) {
      killCharts();
      const p = periodDefaults();
      stage.innerHTML = `
        <div class="cap" id="capRoot">
          <div class="cap-toolbar">
            <div>
              <p class="section-label">Период</p>
              <div class="cap-period">
                <input type="date" id="capFrom" value="${p.from}" />
                <span>—</span>
                <input type="date" id="capTo" value="${p.to}" />
                <button type="button" class="btn-refresh" id="capReload">Обновить</button>
              </div>
            </div>
            <div class="cap-mode">
              <label><input type="checkbox" id="capEdit" /> режим редактирования</label>
              <span class="cap-api" id="capApi">API…</span>
            </div>
          </div>
          <p class="cap-banner" id="capBanner">Загрузка…</p>
          <div id="capBody"></div>
        </div>`;

      const reload = async () => {
        const from = document.getElementById("capFrom").value;
        const to = document.getElementById("capTo").value;
        const edit = document.getElementById("capEdit").checked;
        await paint(from, to, edit);
      };
      document.getElementById("capReload").onclick = reload;
      document.getElementById("capEdit").onchange = reload;
      document.getElementById("capFrom").onchange = reload;
      document.getElementById("capTo").onchange = reload;
      await reload();
    },
  };

  async function paint(from, to, edit) {
    const banner = document.getElementById("capBanner");
    const body = document.getElementById("capBody");
    const apiEl = document.getElementById("capApi");
    killCharts();
    try {
      await api("/api/health");
      apiEl.textContent = "API · 127.0.0.1:8777";
      apiEl.classList.add("ok");
    } catch {
      apiEl.textContent = "API офлайн";
      apiEl.classList.remove("ok");
      banner.textContent =
        "Локальный Capital API не запущен. В терминале: python tools/capital_api.py (только 127.0.0.1:8777). Ledger пуст до подтверждённых данных — цифры не выдуманы.";
      body.innerHTML = emptyShell(edit);
      if (edit) bindForms(body, from, to, () => paint(from, to, true));
      return;
    }

    let summary;
    try {
      summary = await api(`/api/summary?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`);
    } catch (e) {
      banner.textContent = "Ошибка API: " + e.message;
      return;
    }

    const nw = summary.net_worth || {};
    const flows = summary.flows || {};
    const hasTx = (summary.transactions || []).some((t) => t.status === "actual");
    banner.innerHTML = hasTx
      ? `Данные actual · актуальность среза <strong>${esc(summary.as_of)}</strong>${
          nw.has_estimates ? " · в капитале есть <em>оценки</em>" : ""
        }`
      : `Ledger пуст (actual операций нет). Известные срезы дохода/кеша/ипотеки — в карточках Harvest как датированные сообщения, не как текущий баланс. Срез API: ${esc(
          summary.as_of
        )}`;

    body.innerHTML = `
      <section class="cap-kpis">
        <div class="cap-kpi">
          <p class="section-label">Чистый капитал</p>
          <p class="cap-num">${esc(fmt(nw.net_worth_minor))}</p>
          <p class="cap-sub">${nw.has_estimates ? "включая оценки активов" : "по книгам счетов"}</p>
        </div>
        <div class="cap-kpi">
          <p class="section-label">Ликвидность</p>
          <p class="cap-num">${esc(fmt(nw.liquid_minor))}</p>
          <p class="cap-sub">остатки счетов (actual)</p>
        </div>
        <div class="cap-kpi">
          <p class="section-label">Доход периода</p>
          <p class="cap-num">${esc(fmt(flows.income_minor))}</p>
        </div>
        <div class="cap-kpi">
          <p class="section-label">Расход периода</p>
          <p class="cap-num">${esc(fmt(flows.expense_minor))}</p>
        </div>
        <div class="cap-kpi">
          <p class="section-label">Чистый поток</p>
          <p class="cap-num">${esc(fmt(flows.net_cashflow_minor))}</p>
          <p class="cap-sub">без переводов</p>
        </div>
        <div class="cap-kpi">
          <p class="section-label">Долг</p>
          <p class="cap-num">${esc(fmt(nw.liabilities_minor))}</p>
        </div>
      </section>

      <section class="cap-charts">
        <div class="cap-chart-box">
          <p class="section-label">Доходы / расходы по месяцам</p>
          <canvas id="chartFlow" height="140"></canvas>
        </div>
        <div class="cap-chart-box">
          <p class="section-label">Структура расходов</p>
          <canvas id="chartExp" height="140"></canvas>
        </div>
      </section>

      <section class="home-split">
        <div>
          <p class="section-label">Счета</p>
          <ul class="soft-list" id="capAccounts"></ul>
        </div>
        <div>
          <p class="section-label">Цели</p>
          <ul class="soft-list" id="capGoals"></ul>
          <p class="section-label" style="margin-top:18px">Связь с Harvest</p>
          <ul class="soft-list">
            <li><span>Доход — текущий</span><span>карточка</span></li>
            <li><span>Кеш — текущий</span><span>карточка</span></li>
            <li><span>Ипотека и жильё</span><span>карточка</span></li>
            <li><span>Капитал/AUDIT</span><span>аудит</span></li>
          </ul>
        </div>
      </section>

      <section>
        <p class="section-label">Операции</p>
        <div class="cap-ops-tools">
          <input type="search" id="capSearch" placeholder="Поиск…" />
        </div>
        <div class="cap-table-wrap">
          <table class="cap-table" id="capTable">
            <thead>
              <tr><th>Дата</th><th>Тип</th><th>Сумма</th><th>Счёт</th><th>Статус</th><th>Комментарий</th><th></th></tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </section>

      <div id="capForms" class="${edit ? "" : "is-hidden"}"></div>
    `;

    // accounts list
    const accMap = Object.fromEntries((summary.accounts || []).map((a) => [a.id, a]));
    const bals = summary.balances || {};
    const accUl = body.querySelector("#capAccounts");
    if (!(summary.accounts || []).length) {
      accUl.innerHTML = "<li><span>Счетов пока нет</span><span></span></li>";
    } else {
      accUl.innerHTML = summary.accounts
        .map(
          (a) =>
            `<li><span>${esc(a.name)} · ${esc(a.account_kind)}</span><span>${esc(
              fmt(bals[a.id] || 0, a.currency || "RUB")
            )}</span></li>`
        )
        .join("");
    }
    const goalsUl = body.querySelector("#capGoals");
    if (!(summary.goals || []).length) {
      goalsUl.innerHTML = "<li><span>Цели ledger пусты — см. карточки FI</span><span></span></li>";
    } else {
      goalsUl.innerHTML = summary.goals
        .map((g) => `<li><span>${esc(g.name)}</span><span>${esc(g.status)}</span></li>`)
        .join("");
    }

    renderCharts(summary);
    renderTable(summary, accMap, () => paint(from, to, edit));
    body.querySelector("#capSearch").oninput = (e) => filterTable(e.target.value);

    if (edit) {
      const forms = body.querySelector("#capForms");
      forms.innerHTML = formHtml(summary);
      bindForms(forms, from, to, () => paint(from, to, true));
    }
  }

  function emptyShell(edit) {
    return `
      <section class="cap-kpis">
        <div class="cap-kpi"><p class="section-label">Чистый капитал</p><p class="cap-num">—</p></div>
        <div class="cap-kpi"><p class="section-label">Ликвидность</p><p class="cap-num">—</p></div>
      </section>
      <div id="capForms" class="${edit ? "" : "is-hidden"}">${edit ? formHtml({ accounts: [], categories: [] }) : ""}</div>`;
  }

  function formHtml(summary) {
    const accOpts = (summary.accounts || [])
      .map((a) => `<option value="${esc(a.id)}">${esc(a.name)}</option>`)
      .join("");
    const catOpts = (summary.categories || [])
      .map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`)
      .join("");
    const today = new Date().toISOString().slice(0, 10);
    return `
      <section class="cap-forms">
        <p class="section-label">Добавить счёт</p>
        <form id="formAcc" class="cap-form">
          <input name="name" required placeholder="Название" />
          <select name="account_kind">
            <option value="checking">расчётный</option>
            <option value="savings">накопительный</option>
            <option value="cash">наличные</option>
            <option value="broker">брокер</option>
            <option value="other">другое</option>
          </select>
          <input name="amount" placeholder="Начальный остаток (0.00)" value="0" />
          <button type="submit">Создать счёт</button>
        </form>

        <p class="section-label">Добавить операцию</p>
        <form id="formTx" class="cap-form">
          <input type="date" name="date" required value="${today}" />
          <select name="type">
            <option value="income">доход</option>
            <option value="expense">расход</option>
            <option value="transfer">перевод</option>
            <option value="debt_interest">%% по долгу</option>
            <option value="debt_principal">тело долга</option>
          </select>
          <input name="amount" required placeholder="Сумма 0.00" />
          <select name="account_id" required><option value="">счёт…</option>${accOpts}</select>
          <select name="counterparty_account_id"><option value="">контрагент (перевод)</option>${accOpts}</select>
          <select name="category_id"><option value="">категория</option>${catOpts}</select>
          <input name="comment" placeholder="Комментарий" />
          <button type="submit">Сохранить операцию</button>
        </form>
        <p class="cap-sub">Перевод не доход/расход. Сохранение только через локальный API → YAML в harvest/Финансы/Капитал/.</p>
      </section>`;
  }

  function bindForms(root, from, to, after) {
    const formAcc = root.querySelector("#formAcc");
    const formTx = root.querySelector("#formTx");
    if (formAcc) {
      formAcc.onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(formAcc);
        try {
          await api("/api/accounts", {
            method: "POST",
            body: JSON.stringify({
              name: fd.get("name"),
              account_kind: fd.get("account_kind"),
              amount: fd.get("amount") || "0",
              currency: "RUB",
              status: "actual",
            }),
          });
          await after();
        } catch (err) {
          alert("Счёт: " + err.message);
        }
      };
    }
    if (formTx) {
      formTx.onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(formTx);
        const type = fd.get("type");
        const payload = {
          type,
          date: fd.get("date"),
          amount: fd.get("amount"),
          currency: "RUB",
          account_id: fd.get("account_id"),
          category_id: fd.get("category_id") || null,
          comment: fd.get("comment") || "",
          status: "actual",
        };
        if (type === "transfer") {
          payload.counterparty_account_id = fd.get("counterparty_account_id");
          if (!payload.counterparty_account_id) {
            alert("Для перевода укажи счёт-получатель");
            return;
          }
        }
        try {
          await api("/api/transactions", { method: "POST", body: JSON.stringify(payload) });
          await after();
        } catch (err) {
          alert("Операция: " + err.message + (err.payload?.duplicate_id ? " (дубль " + err.payload.duplicate_id + ")" : ""));
        }
      };
    }
  }

  function renderTable(summary, accMap, refresh) {
    const tbody = document.querySelector("#capTable tbody");
    if (!tbody) return;
    const rows = summary.transactions || [];
    tbody.innerHTML = rows
      .map((t) => {
        const acc = accMap[t.account_id]?.name || t.account_id || "—";
        const voidBtn =
          t.status === "actual"
            ? `<button type="button" data-void="${esc(t.id)}" class="linkish">отменить</button>`
            : "";
        return `<tr data-q="${esc((t.comment || "") + " " + t.type + " " + acc)}">
          <td>${esc(t.date)}</td>
          <td>${esc(t.type)}</td>
          <td>${esc(fmt(t.amount_minor, t.currency))}</td>
          <td>${esc(acc)}</td>
          <td>${esc(t.status)}</td>
          <td>${esc(t.comment || "")}</td>
          <td>${voidBtn}</td>
        </tr>`;
      })
      .join("");
    tbody.querySelectorAll("[data-void]").forEach((btn) => {
      btn.onclick = async () => {
        if (!confirm("Отменить операцию? Запись станет void, история сохранится.")) return;
        try {
          await api("/api/transactions/void", {
            method: "POST",
            body: JSON.stringify({ id: btn.getAttribute("data-void"), reason: "ui void" }),
          });
          refresh();
        } catch (e) {
          alert(e.message);
        }
      };
    });
  }

  function filterTable(q) {
    const qq = q.trim().toLowerCase();
    document.querySelectorAll("#capTable tbody tr").forEach((tr) => {
      tr.style.display = !qq || (tr.getAttribute("data-q") || "").toLowerCase().includes(qq) ? "" : "none";
    });
  }

  function renderCharts(summary) {
    if (typeof Chart === "undefined") return;
    const monthly = summary.monthly || [];
    const ctx1 = document.getElementById("chartFlow");
    if (ctx1) {
      charts.push(
        new Chart(ctx1, {
          type: "bar",
          data: {
            labels: monthly.map((m) => m.month),
            datasets: [
              {
                label: "Доход",
                data: monthly.map((m) => m.income_minor / 100),
                backgroundColor: "rgba(92,184,138,.55)",
              },
              {
                label: "Расход",
                data: monthly.map((m) => m.expense_minor / 100),
                backgroundColor: "rgba(212,138,120,.55)",
              },
            ],
          },
          options: {
            responsive: true,
            plugins: { legend: { labels: { color: "#9a9aa3" } } },
            scales: {
              x: { ticks: { color: "#6f737c" }, grid: { color: "#1e222b" } },
              y: { ticks: { color: "#6f737c" }, grid: { color: "#1e222b" } },
            },
          },
        })
      );
    }
    const byCat = summary.expense_by_category || {};
    const cats = summary.categories || [];
    const catName = Object.fromEntries(cats.map((c) => [c.id, c.name]));
    const labels = Object.keys(byCat);
    const ctx2 = document.getElementById("chartExp");
    if (ctx2) {
      charts.push(
        new Chart(ctx2, {
          type: "doughnut",
          data: {
            labels: labels.map((id) => catName[id] || id),
            datasets: [
              {
                data: labels.map((id) => byCat[id] / 100),
                backgroundColor: ["#c9a27a", "#5cb88a", "#7eb6d9", "#d48a78", "#9a9aa3", "#cbb46a"],
              },
            ],
          },
          options: {
            plugins: { legend: { labels: { color: "#9a9aa3" } } },
          },
        })
      );
    }
  }
})();
