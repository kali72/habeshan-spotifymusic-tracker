const SPREADSHEET_ID = "1PbFEMGn3XR3cnZXan04C65FdXPJbIVFAO_G51U9RGPU";
const API_KEY = "AIzaSyD4sLQaZ2Wld01E2wUzoPKfSVd39nOL_vA";
// Default active tab
let currentTab = "1 Week";
// ============================================================================
// INITIALIZATION
// ============================================================================
document.addEventListener("DOMContentLoaded", () => {
  setupTabListeners();
  loadLeaderboard(currentTab);
});
// ============================================================================
// TAB SWITCHING LOGIC
// ============================================================================
function setupTabListeners() {
  const tabButtons = document.querySelectorAll("[data-tab]");
  
  tabButtons.forEach((button) => {
    button.addEventListener("click", (e) => {
      // Update active button state
      tabButtons.forEach((btn) => btn.classList.remove("active"));
      e.target.classList.add("active");

      // Fetch and render data for selected tab
      currentTab = e.target.getAttribute("data-tab");
      loadLeaderboard(currentTab);
    });
  });
}

// ============================================================================
// API FETCH & PARSING
// ============================================================================
async function loadLeaderboard(tabName) {
  const container = document.getElementById("leaderboard-container");
  showLoading(container);

  // Sheet range A1:G101 covers headers + top 100 rows
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${SPREADSHEET_ID}/values/'${encodeURIComponent(tabName)}'!A1:G101?key=${API_KEY}`;

  try {
    const response = await fetch(url);
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error?.message || `HTTP ${response.status}`);
    }

    const data = await response.json();
    const rows = data.values;

    if (!rows || rows.length <= 1) {
      container.innerHTML = `<p class="status-msg">No track data available for ${tabName}.</p>`;
      return;
    }

    renderTable(container, rows);
  } catch (error) {
    console.error("Leaderboard fetch error:", error);
    showError(container, error.message);
  }
}

// ============================================================================
// HTML TABLE RENDERER
// ============================================================================
function renderTable(container, rows) {
  const headers = rows[0];
  const dataRows = rows.slice(1);

  // Map header names to column indices dynamically
  const rankIdx = headers.indexOf("Rank");
  const coverIdx = headers.indexOf("Cover");
  const artistIdx = headers.indexOf("Artist");
  const trackNameIdx = headers.indexOf("Track Name");
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
    const fallbackImg = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='40' viewBox='0 0 24 24' fill='%23888'%3E%3Cpath d='M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z'/%3E%3C/svg%3E";
    const imgSrc = coverUrl ? escapeHtml(coverUrl) : fallbackImg;

    tableHtml += `
      <tr class="clickable-row" onclick="window.open('${spotifyUrl}', '_blank')" title="Listen on Spotify">
        <td><span class="rank-badge rank-${escapeHtml(rank)}">${escapeHtml(rank)}</span></td>
        <td><img src="${imgSrc}" alt="Album Cover" class="track-cover" loading="lazy" /></td>
        <td class="track-title-cell">
          <a href="${spotifyUrl}" target="_blank" rel="noopener noreferrer" class="track-link" onclick="event.stopPropagation()">
            ${escapeHtml(trackName)}
          </a>
        </td>
        <td class="track-artist">${escapeHtml(artist)}</td>
      </tr>
    `;
  });

  tableHtml += `
      </tbody>
    </table>
  `;

  container.innerHTML = tableHtml;
}
// ============================================================================
// UI STATE HELPERS & UTILITIES
// ============================================================================
function showLoading(container) {
  container.innerHTML = `
    <div class="loading-spinner">
      <div class="spinner"></div>
      <p>Loading ${currentTab} leaderboard...</p>
    </div>
  `;
}

function showError(container, message) {
  container.innerHTML = `
    <div class="error-box">
      <p><strong>Failed to load data</strong></p>
      <p>${escapeHtml(message)}</p>
      <p><small>Check if your Google Sheet is shared publicly and API restrictions permit this origin.</small></p>
    </div>
  `;
}
// ============================================================================
// THEME SWITCHER
// ============================================================================
function initTheme() {
  const toggleBtn = document.getElementById("theme-toggle");
  if (!toggleBtn) return;

  // Check stored theme or default to dark
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

// Update your DOMContentLoaded listener at the top of app.js:
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  setupTabListeners();
  loadLeaderboard(currentTab);
});
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
// ============================================================================
// BACK TO TOP LOGIC
// ============================================================================
function initBackToTop() {
  const backToTopBtn = document.getElementById("back-to-top");
  if (!backToTopBtn) return;

  // Toggle button visibility based on scroll distance (300px threshold)
  window.addEventListener("scroll", () => {
    if (window.scrollY > 300) {
      backToTopBtn.classList.add("show");
    } else {
      backToTopBtn.classList.remove("show");
    }
  });

  // Smooth scroll back to top
  backToTopBtn.addEventListener("click", () => {
    window.scrollTo({
      top: 0,
      behavior: "smooth"
    });
  });
}

// Update your main DOMContentLoaded initialization at the top of app.js:
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initBackToTop();
  setupTabListeners();
  loadLeaderboard(currentTab);
});
