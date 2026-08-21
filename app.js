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
  const headers = rows[0]; // First row contains headers
  const dataRows = rows.slice(1); // Remaining rows contain track records

  let tableHtml = `
    <table class="leaderboard-table">
      <thead>
        <tr>
  `;

  // Build table headers
  headers.forEach((header) => {
    tableHtml += `<th>${escapeHtml(header)}</th>`;
  });

  tableHtml += `
        </tr>
      </thead>
      <tbody>
  `;

  // Build data rows
  dataRows.forEach((row) => {
    tableHtml += `<tr>`;
    
    headers.forEach((_, colIndex) => {
      const cellValue = row[colIndex] || "";
      
      // Formatting for Rank badge column
      if (colIndex === 0) {
        tableHtml += `<td><span class="rank-badge rank-${cellValue}">${escapeHtml(cellValue)}</span></td>`;
      } 
      // Formatting for Growth indicator (+X / -X)
      else if (headers[colIndex] === "Score Growth") {
        const isPositive = cellValue.startsWith("+");
        const badgeClass = isPositive ? "growth-up" : "growth-neutral";
        tableHtml += `<td><span class="${badgeClass}">${escapeHtml(cellValue)}</span></td>`;
      } 
      // Standard text column
      else {
        tableHtml += `<td>${escapeHtml(cellValue)}</td>`;
      }
    });

    tableHtml += `</tr>`;
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
