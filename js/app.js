/**
 * Morning Dashboard – Frontend
 * Lädt data.json und rendert alle Sektionen mit Fallback-Verhalten.
 */

const DATA_URL = "data.json";

const DE_LOCALE = "de-DE";
const BERLIN_TZ = "Europe/Berlin";

/** DOM-Hilfsfunktionen */
const $ = (id) => document.getElementById(id);

/**
 * Formatiert ISO-Zeitstempel für Anzeige in deutscher Zeitzone.
 */
function formatTimestamp(isoString) {
  if (!isoString) return "—";
  try {
    const date = new Date(isoString);
    return new Intl.DateTimeFormat(DE_LOCALE, {
      timeZone: BERLIN_TZ,
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  } catch {
    return isoString;
  }
}

/**
 * Formatiert Zahlen für Finanzanzeige.
 */
function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return new Intl.NumberFormat(DE_LOCALE, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/**
 * Rendert Prozentänderung mit Vorzeichen und CSS-Klasse.
 */
function renderChange(changePct) {
  if (changePct === null || changePct === undefined) {
    return `<p class="metric-change neutral">—</p>`;
  }
  const sign = changePct > 0 ? "+" : "";
  const cssClass = changePct > 0 ? "positive" : changePct < 0 ? "negative" : "neutral";
  return `<p class="metric-change ${cssClass}">${sign}${formatNumber(changePct)}%</p>`;
}

function showSectionError(elementId, message) {
  const el = $(elementId);
  if (!el || !message) return;
  el.textContent = message;
  el.classList.remove("hidden");
}

function renderIndices(section) {
  const container = $("indices-grid");
  if (!section?.data?.length) {
    showSectionError("markets-error", section?.error || "Indexdaten vorübergehend nicht verfügbar");
    return;
  }

  container.innerHTML = section.data.map((item) => `
    <article class="metric-card">
      <p class="metric-name">${escapeHtml(item.name)}</p>
      <p class="metric-price">${formatNumber(item.price, item.price > 1000 ? 0 : 2)}</p>
      ${renderChange(item.change_pct)}
    </article>
  `).join("");

  if (section.error) {
    showSectionError("markets-error", section.error);
  }
}

function renderCrypto(section) {
  const container = $("crypto-grid");
  if (!section?.data?.length) {
    showSectionError("markets-error", section?.error || "Kryptodaten vorübergehend nicht verfügbar");
    return;
  }

  container.innerHTML = section.data.map((item) => `
    <article class="metric-card">
      <p class="metric-name">${escapeHtml(item.name)}</p>
      <p class="metric-price">${formatNumber(item.eur, 0)} €</p>
      <p class="metric-sub">${formatNumber(item.usd, 0)} $</p>
      ${renderChange(item.change_24h_pct)}
    </article>
  `).join("");
}

function renderForex(section) {
  const container = $("forex-grid");
  if (!section?.data?.length) {
    return;
  }

  container.innerHTML = section.data.map((item) => {
    const suffix = item.unit === "%" ? "%" : "";
    const decimals = item.unit === "%" ? 2 : 4;
    return `
      <article class="metric-card">
        <p class="metric-name">${escapeHtml(item.name)}</p>
        <p class="metric-price">${formatNumber(item.price, decimals)}${suffix}</p>
        ${item.unit !== "%" ? renderChange(item.change_pct) : ""}
      </article>
    `;
  }).join("");
}

function renderFinanceNews(section) {
  const container = $("finance-news");
  if (!section?.data?.length) {
    container.innerHTML = `<p class="empty-state">Finanznachrichten vorübergehend nicht verfügbar.</p>`;
    showSectionError("finance-error", section?.error || "");
    return;
  }

  container.innerHTML = section.data.map((article) => `
    <a class="news-item" href="${escapeAttr(article.link)}" target="_blank" rel="noopener noreferrer">
      <div class="news-item-header">
        <span class="news-source">${escapeHtml(article.source)}</span>
      </div>
      <h3 class="news-title">${escapeHtml(article.title)}</h3>
      ${article.summary ? `<p class="news-summary">${escapeHtml(article.summary)}</p>` : ""}
      <p class="news-link-hint">Zur Originalquelle →</p>
    </a>
  `).join("");

  if (section.error) {
    showSectionError("finance-error", section.error);
  }
}

function renderNicheNews(section) {
  const container = $("niche-news");
  if (!section?.data?.length) {
    container.innerHTML = `<p class="empty-state">Nischen-News vorübergehend nicht verfügbar.</p>`;
    showSectionError("niche-error", section?.error || "");
    return;
  }

  container.innerHTML = section.data.map((article) => `
    <a class="niche-card" href="${escapeAttr(article.link)}" target="_blank" rel="noopener noreferrer">
      <div class="niche-card-top">
        ${article.category ? `<span class="niche-category">${escapeHtml(article.category)}</span>` : "<span></span>"}
        <span class="niche-source">${escapeHtml(article.source)}</span>
      </div>
      <div class="niche-body">
        <h3 class="niche-title">${escapeHtml(article.title)}</h3>
        ${article.summary ? `<p class="niche-summary">${escapeHtml(article.summary)}</p>` : ""}
      </div>
      <div class="niche-footer">Weiterlesen bei der Quelle →</div>
    </a>
  `).join("");

  if (section.error) {
    showSectionError("niche-error", section.error);
  }
}

/** XSS-sichere Textausgabe */
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

function escapeAttr(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/**
 * Übersetzt englisches Wochentags-Datum ins Deutsche (Fallback).
 */
function localizeDateLabel(label) {
  if (!label) return new Intl.DateTimeFormat(DE_LOCALE, {
    timeZone: BERLIN_TZ,
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date());

  const days = {
    Monday: "Montag", Tuesday: "Dienstag", Wednesday: "Mittwoch",
    Thursday: "Donnerstag", Friday: "Freitag", Saturday: "Samstag", Sunday: "Sonntag",
  };
  const months = {
    January: "Januar", February: "Februar", March: "März", April: "April",
    May: "Mai", June: "Juni", July: "Juli", August: "August",
    September: "September", October: "Oktober", November: "November", December: "Dezember",
  };

  let result = label;
  for (const [en, de] of Object.entries(days)) {
    result = result.replace(en, de);
  }
  for (const [en, de] of Object.entries(months)) {
    result = result.replace(en, de);
  }
  return result;
}

function renderDashboard(data) {
  $("date-label").textContent = localizeDateLabel(data.date_label);
  $("updated-at").textContent = formatTimestamp(data.generated_at);

  renderIndices(data.indices);
  renderCrypto(data.crypto);
  renderForex(data.markets);
  renderFinanceNews(data.finance_news);
  renderNicheNews(data.niche_news);
}

function renderError(message) {
  $("date-label").textContent = "—";
  $("updated-at").textContent = "—";
  showSectionError("markets-error", message);
  $("finance-news").innerHTML = `<p class="empty-state">${escapeHtml(message)}</p>`;
  $("niche-news").innerHTML = `<p class="empty-state">${escapeHtml(message)}</p>`;
}

async function init() {
  try {
    const response = await fetch(`${DATA_URL}?t=${Date.now()}`);
    if (!response.ok) {
      throw new Error(`data.json konnte nicht geladen werden (${response.status})`);
    }
    const data = await response.json();
    renderDashboard(data);
  } catch (err) {
    console.error(err);
    renderError("Dashboard-Daten konnten nicht geladen werden. Bitte später erneut versuchen.");
  }
}

document.addEventListener("DOMContentLoaded", init);
