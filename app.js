const SPREADSHEET_ID = "1PbFEMGn3XR3cnZXan04C65FdXPJbIVFAO_G51U9RGPU";
const API_KEY = "AIzaSyD4sLQaZ2Wld01E2wUzoPKfSVd39nOL_vA";

const CHARTS = [
  { containerId: "section-top-15-artists", anchorId: "top-15-artists", title: "Top 15 Artists", tabName: "Top 15 Artists" },
  { containerId: "section-all-time-tracks", anchorId: "all-time-tracks", title: "All-Time Most Heard", tabName: "All-Time Tracks" },
  { containerId: "section-weekly-top-10", anchorId: "weekly-top-10", title: "Weekly Top 10", tabName: "Weekly Top 10" },
  { containerId: "section-monthly-top-100", anchorId: "monthly-top-100", title: "Monthly Top 100", tabName: "Monthly Top 100" },
  { containerId: "section-three-month-top-100", anchorId: "three-month-top-100", title: "3-Month Top 100", tabName: "3-Month Top 100" },
  { containerId: "section-yearly-top-100", anchorId: "yearly-top-100", title: "Yearly Top 100", tabName: "Yearly Top 100" }
];

// Tabs whose "Score Growth" column reflects a real trend (the All-Time tab
// always writes "+0", so it's left out of this list on purpose).
const GROWTH_TABS = new Set(["Weekly Top 10", "Monthly Top 100", "3-Month Top 100", "Yearly Top 100"]);

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initBackToTop();
  loadAllLeaderboards();
});

function initTheme() {
  const toggleBtn = document.getElementById("theme-toggle");
  if (!toggleBtn) return;

  const savedTheme = localStorage.getItem("theme");
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const currentTheme = savedTheme || (prefersDark ? "dark" : "light");

  document.documentElement.setAttribute("data-theme", currentTheme);
  updateToggleText(toggleBtn, currentTheme);

  toggleBtn.addEventListener("click", () => {
    const activeTheme = document.documentElement.getAttribute("data-theme");
    const newTheme = activeTheme === "dark" ? "light" : "dark";

    document.documentElement.setAttribute("data-theme", newTheme);
    localStorage.setItem("theme", newTheme);
    updateToggleText(toggleBtn, newTheme);
  });
}

function updateToggleText(button, theme) {
  button.textContent = theme === "dark" ? "Light mode" : "Dark mode";
}

async function loadAllLeaderboards() {
  CHARTS.forEach(chart => {
    const wrapper = document.getElementById(chart.containerId);
    if (wrapper) {
      wrapper.innerHTML = `
        <section id="${chart.anchorId}" class="ranking-section">
          <h2 class="section-title">${escapeHtml(chart.title)}</h2>
          <p class="empty-state">Loading chart…</p>
        </section>
      `;
    }
  });

  try {
    const fetchPromises = CHARTS.map(chart => {
      const url = `https://sheets.googleapis.com/v4/spreadsheets/${SPREADSHEET_ID}/values/'${encodeURIComponent(chart.tabName)}'!A1:G101?key=${API_KEY}`;
      return fetch(url)
        .then(res => res.ok ? res.json() : null)
        .catch(() => null);
    });

    const results = await Promise.all(fetchPromises);

    CHARTS.forEach((chart, index) => {
      const wrapper = document.getElementById(chart.containerId);
      if (!wrapper) return;

      const data = results[index];
      const rows = data ? data.values : null;

      let sectionContent = `<h2 class="section-title">${escapeHtml(chart.title)}</h2>`;

      if (rows && rows.length > 1) {
        const isArtistTable = chart.tabName === "Top 15 Artists";
        sectionContent += isArtistTable
          ? generateArtistGridHtml(rows)
          : generateTrackTableHtml(rows, chart.tabName);
      } else {
        sectionContent += `<p class="empty-state">No data currently available.</p>`;
      }

      wrapper.innerHTML = `
        <section id="${chart.anchorId}" class="ranking-section">
          ${sectionContent}
        </section>
      `;
    });
  } catch (error) {
    console.error("Fetch error:", error);
  }
}

const FALLBACK_IMG = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 24 24' fill='%23888'%3E%3Cpath d='M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z'/%3E%3C/svg%3E";

// Top 15 Artists: rank, cover(=artist's own Spotify profile photo), artist, bio
function generateArtistGridHtml(rows) {
  const dataRows = rows.slice(1);

  let html = `<div class="artist-grid">`;

  dataRows.forEach(row => {
    const rank = row[0] || "";
    const photoUrl = row[1] || "";
    const name = row[2] || "";
    const bio = row[3] || "";
    const imgSrc = photoUrl ? escapeHtml(photoUrl) : FALLBACK_IMG;

    html += `
      <div class="artist-card">
        <span class="artist-rank">${escapeHtml(rank)}</span>
        <img src="${imgSrc}"
             onerror="this.onerror=null;this.src='${FALLBACK_IMG}';"
             alt="${escapeHtml(name)}"
             class="artist-avatar"
             loading="lazy" />
        <div class="artist-info">
          <div class="artist-name" title="${escapeHtml(name)}">${escapeHtml(name)}</div>
          <div class="artist-bio" title="${escapeHtml(bio)}">${escapeHtml(bio)}</div>
        </div>
      </div>
    `;
  });

  html += `</div>`;
  return html;
}

function growthBadgeHtml(growthStr) {
  if (!growthStr) return "";
  const value = parseInt(growthStr, 10);
  if (isNaN(value) || value === 0) {
    return `<span class="growth-badge growth-flat">–</span>`;
  }
  const cls = value > 0 ? "growth-up" : "growth-down";
  const symbol = value > 0 ? "▲" : "▼";
  return `<span class="growth-badge ${cls}">${symbol} ${Math.abs(value)}</span>`;
}

// Track leaderboards: rank, cover, artist, track name, track id, popularity, growth, date
function generateTrackTableHtml(rows, tabName) {
  const dataRows = rows.slice(1);
  const showGrowth = GROWTH_TABS.has(tabName);

  let tableHtml = `
    <div class="table-container">
      <table class="leaderboard-table">
        <thead>
          <tr>
            <th>#</th>
            <th></th>
            <th>Title</th>
            <th>Artist</th>
            ${showGrowth ? `<th>Trend</th>` : ``}
          </tr>
        </thead>
        <tbody>
  `;

  dataRows.forEach(row => {
    const rank = row[0] || "";
    const coverUrl = row[1] || "";
    const artist = row[2] || "";
    const title = row[3] || "";
    const trackId = row[4] || "";
    const growth = row[6] || "";

    const spotifyUrl = trackId ? `https://open.spotify.com/track/${escapeHtml(trackId)}` : "#";
    const imgSrc = coverUrl ? escapeHtml(coverUrl) : FALLBACK_IMG;
    const rankClass = rank === "1" ? "rank-1" : rank === "2" ? "rank-2" : rank === "3" ? "rank-3" : "";

    tableHtml += `
      <tr class="clickable-row" onclick="window.open('${spotifyUrl}', '_blank')" title="Listen on Spotify">
        <td><span class="rank-num ${rankClass}">${escapeHtml(rank)}</span></td>
        <td>
          <img src="${imgSrc}"
               onerror="this.onerror=null;this.src='${FALLBACK_IMG}';"
               alt="Track cover"
               class="track-cover"
               loading="lazy" />
        </td>
        <td class="track-title-cell">
          <a href="${spotifyUrl}" target="_blank" rel="noopener noreferrer" class="track-link" onclick="event.stopPropagation()">
            <span class="spotify-dot"></span>${escapeHtml(title)}
          </a>
        </td>
        <td class="track-artist">${escapeHtml(artist)}</td>
        ${showGrowth ? `<td>${growthBadgeHtml(growth)}</td>` : ``}
      </tr>
    `;
  });

  tableHtml += `</tbody></table></div>`;
  return tableHtml;
}

function initBackToTop() {
  const backToTopBtn = document.getElementById("back-to-top");
  if (!backToTopBtn) return;

  window.addEventListener("scroll", () => {
    if (window.scrollY > 300) {
      backToTopBtn.classList.add("show");
    } else {
      backToTopBtn.classList.remove("show");
    }
  });

  backToTopBtn.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
