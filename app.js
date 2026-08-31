const SPREADSHEET_ID = "1PbFEMGn3XR3cnZXan04C65FdXPJbIVFAO_G51U9RGPU";
const API_KEY = "AIzaSyD4sLQaZ2Wld01E2wUzoPKfSVd39nOL_vA";

const CHARTS = [
  { id: "top-15-artists", title: "Top 15 Artists", tabName: "Top 15 Artists" },
  { id: "all-time-tracks", title: "All-Time Tracks", tabName: "All-Time Tracks" },
  { id: "weekly-top-10", title: "Weekly Top 10", tabName: "Weekly Top 10" },
  { id: "monthly-top-100", title: "Monthly Top 100", tabName: "Monthly Top 100" },
  { id: "three-month-top-100", title: "3-Month Top 100", tabName: "3-Month Top 100" },
  { id: "yearly-top-100", title: "Yearly Top 100", tabName: "Yearly Top 100" }
];

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initBackToTop();
  loadAllLeaderboards();
});

async function loadAllLeaderboards() {
  const container = document.getElementById("leaderboard-container");
  container.innerHTML = `
    <div class="loading-spinner">
      <div class="spinner"></div>
      <p>Loading all Ethiopian music rankings...</p>
    </div>
  `;

  try {
    const fetchPromises = CHARTS.map(chart => {
      const url = `https://sheets.googleapis.com/v4/spreadsheets/${SPREADSHEET_ID}/values/'${encodeURIComponent(chart.tabName)}'!A1:G101?key=${API_KEY}`;
      return fetch(url)
        .then(res => res.ok ? res.json() : null)
        .catch(() => null);
    });

    const results = await Promise.all(fetchPromises);
    container.innerHTML = ""; // Clear spinner

    CHARTS.forEach((chart, index) => {
      const data = results[index];
      const rows = data ? data.values : null;

      const sectionEl = document.createElement("section");
      sectionEl.id = chart.id;
      sectionEl.className = "ranking-section";

      let sectionContent = `<h2 class="section-title">${escapeHtml(chart.title)}</h2>`;

      if (rows && rows.length > 1) {
        sectionContent += generateTableHtml(rows);
      } else {
        sectionContent += `<p class="status-msg">No data available for ${escapeHtml(chart.title)}.</p>`;
      }

      sectionEl.innerHTML = sectionContent;
      container.appendChild(sectionEl);
    });
  } catch (error) {
    console.error("Fetch error:", error);
    showError(container, error.message);
  }
}

function generateTableHtml(rows) {
  const headers = rows[0];
  const dataRows = rows.slice(1);

  const rankIdx = headers.indexOf("Rank");
  const coverIdx = headers.indexOf("Cover");
  const artistIdx = headers.indexOf("Artist");
  const trackNameIdx = headers.indexOf("Track Name") !== -1 ? headers.indexOf("Track Name") : headers.indexOf("Title");
  const trackIdIdx = headers.indexOf("Track ID");

  let tableHtml = `
    <table class="leaderboard-table">
      <thead>
        <tr>
          <th>Rank</th>
          <th>Cover</th>
          <th>Title</th>
          <th>Artist</th>
        </tr>
      </thead>
      <tbody>
  `;

  dataRows.forEach((row) => {
    const rank = row[rankIdx] || "";
    const coverUrl = row[coverIdx] || "";
    const artist = row[artistIdx] || "";
    const trackName = row[trackNameIdx] || "";
    const trackId = row[trackIdIdx] || "";

    const spotifyUrl = trackId ? `https://open.spotify.com/track/${escapeHtml(trackId)}` : "#";
    const fallbackImg = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 24 24' fill='%23888'%3E%3Cpath d='M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z'/%3E%3C/svg%3E";
    const imgSrc = coverUrl ? escapeHtml(coverUrl) : fallbackImg;

    tableHtml += `
      <tr class="clickable-row" onclick="window.open('${spotifyUrl}', '_blank')" title="Listen on Spotify">
        <td><span class="rank-badge rank-${escapeHtml(rank)}">${escapeHtml(rank)}</span></td>
        <td><img src="${imgSrc}" alt="Cover" class="track-cover" loading="lazy" /></td>
        <td class="track-title-cell">
          <a href="${spotifyUrl}" target="_blank" rel="noopener noreferrer" class="track-link" onclick="event.stopPropagation()">
            ${escapeHtml(trackName)}
          </a>
        </td>
        <td class="track-artist">${escapeHtml(artist)}</td>
      </tr>
    `;
  });

  tableHtml += `</tbody></table>`;
  return tableHtml;
}

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
  button.innerHTML = theme === "dark" ? "☀️ Light Mode" : "🌙 Dark Mode";
}

function initBackToTop() {
  const backToTopBtn = document.getElementById("back-to-top");
  if (!backToTopBtn) return;

  window.addEventListener("scroll", () => {
    const scrollTop = window.scrollY || document.documentElement.scrollTop;
    if (scrollTop > 300) {
      backToTopBtn.classList.add("show");
    } else {
      backToTopBtn.classList.remove("show");
    }
  });

  backToTopBtn.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

function showError(container, message) {
  container.innerHTML = `
    <div class="error-box">
      <p><strong>Failed to load data</strong></p>
      <p>${escapeHtml(message)}</p>
    </div>
  `;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
