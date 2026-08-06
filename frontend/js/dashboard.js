// /dashboard sahifasi: "Guruhlar" va "Oxirgi tekshiruvlar" bo'limlari.
// group_check_logs / student_issues_log (SQLite) ma'lumotlariga asoslangan.

const groupsDashboardEl = document.getElementById('groups-dashboard');
const recentChecksEl = document.getElementById('recent-checks');

const dashboardLoadingHTML = `
  <div class="loading-state">
    <div class="spinner"></div>
    <span>Yuklanmoqda...</span>
  </div>
`;

function dashboardErrorHTML(message) {
  return `
    <div class="error-state">
      <div class="error-icon">⚠️</div>
      <p>${message}</p>
    </div>
  `;
}

function dashboardEmptyHTML(message) {
  return `
    <div class="empty-state">
      <div class="empty-icon">📭</div>
      <p>${message}</p>
    </div>
  `;
}

// -------------------- GURUHLAR BO'LIMI --------------------

function formatDateTime(isoString) {
  if (!isoString) return '—';
  try {
    const d = new Date(isoString.includes('Z') || isoString.includes('+') ? isoString : isoString + 'Z');
    return d.toLocaleString('uz-UZ', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch (e) {
    return isoString;
  }
}

function statusBadgeClass(status) {
  if (!status) return 'status-unknown';
  if (status === 'success' || status === 'no_problems') return 'status-success';
  if (status.startsWith('error') || status.includes('flood')) return 'status-error';
  return 'status-unknown';
}

function statusBadgeLabel(status) {
  if (!status) return "Noma'lum";
  if (status === 'success') return 'Muvaffaqiyatli';
  if (status === 'no_problems') return 'Muammo topilmadi';
  if (status.startsWith('error')) return 'Xatolik';
  return status;
}

function getGroupCard(group) {
  const resolveRate = group.resolve_rate_pct;
  const resolveRateClass = resolveRate >= 70 ? 'rate-good' : resolveRate >= 40 ? 'rate-mid' : 'rate-low';

  return `
    <div class="group-card">
      <div class="group-card-header">
        <h3>${group.group_name}</h3>
        <span class="group-id-badge">#${group.group_id}</span>
      </div>
      <p class="group-card-assistant">Assistant: <b>${group.assistant_full_name}</b></p>

      <div class="group-card-stats">
        <div class="stat-box">
          <span class="stat-value">${group.checks_count}</span>
          <span class="stat-label">Tekshiruvlar (7 kun)</span>
        </div>
        <div class="stat-box">
          <span class="stat-value">${group.flagged_students_total}</span>
          <span class="stat-label">Muammoli studentlar</span>
        </div>
        <div class="stat-box">
          <span class="stat-value ${resolveRateClass}">${resolveRate}%</span>
          <span class="stat-label">Hal qilingan</span>
        </div>
      </div>

      <div class="group-card-issues">
        <span class="issue-chip resolved-chip">✓ Hal qilingan: ${group.resolved_count}</span>
        <span class="issue-chip open-chip">● Ochiq: ${group.open_count}</span>
      </div>

      <div class="group-card-footer">
        <span class="last-check-status ${statusBadgeClass(group.last_check_status)}">
          ${statusBadgeLabel(group.last_check_status)}
        </span>
        <span class="last-check-time">${formatDateTime(group.last_checked_at)}</span>
      </div>
    </div>
  `;
}

async function loadGroupsDashboard() {
  groupsDashboardEl.innerHTML = dashboardLoadingHTML;
  try {
    const response = await fetch('/api/dashboard/groups');
    if (!response.ok) throw new Error(`HTTP xato: ${response.status}`);
    const data = await response.json();

    if (data.status !== 'success') {
      groupsDashboardEl.innerHTML = dashboardErrorHTML('API xatosi: ' + (data.message || "Noma'lum xatolik"));
      return;
    }

    if (!data.groups || data.groups.length === 0) {
      groupsDashboardEl.innerHTML = dashboardEmptyHTML('Hozircha faol guruhlar topilmadi.');
      return;
    }

    groupsDashboardEl.innerHTML = `
      <div class="groups-grid">
        ${data.groups.map(getGroupCard).join('')}
      </div>
    `;
  } catch (error) {
    console.error('Guruhlar statistikasini yuklashda xatolik:', error);
    groupsDashboardEl.innerHTML = dashboardErrorHTML('Guruhlarni yuklashda xatolik: ' + error.message);
  }
}

// -------------------- OXIRGI TEKSHIRUVLAR BO'LIMI --------------------

function getRecentCheckRow(check) {
  return `
    <div class="check-row">
      <div class="check-row-main">
        <span class="check-group-name">${check.group_name}</span>
        <span class="check-assistant-name">${check.assistant_full_name}</span>
      </div>
      <div class="check-row-meta">
        <span class="check-flagged-count">${check.flagged_count} ta muammoli</span>
        <span class="check-status-badge ${statusBadgeClass(check.check_status)}">
          ${statusBadgeLabel(check.check_status)}
        </span>
        <span class="check-time">${formatDateTime(check.checked_at)}</span>
      </div>
    </div>
  `;
}

async function loadRecentChecks() {
  recentChecksEl.innerHTML = dashboardLoadingHTML;
  try {
    const response = await fetch('/api/dashboard/recent_checks?limit=20');
    if (!response.ok) throw new Error(`HTTP xato: ${response.status}`);
    const data = await response.json();

    if (data.status !== 'success') {
      recentChecksEl.innerHTML = dashboardErrorHTML('API xatosi: ' + (data.message || "Noma'lum xatolik"));
      return;
    }

    if (!data.checks || data.checks.length === 0) {
      recentChecksEl.innerHTML = dashboardEmptyHTML('Hali hech qanday tekshiruv o\'tkazilmagan.');
      return;
    }

    recentChecksEl.innerHTML = `
      <div class="checks-list">
        ${data.checks.map(getRecentCheckRow).join('')}
      </div>
    `;
  } catch (error) {
    console.error('Oxirgi tekshiruvlarni yuklashda xatolik:', error);
    recentChecksEl.innerHTML = dashboardErrorHTML('Tekshiruvlarni yuklashda xatolik: ' + error.message);
  }
}

// Sahifa yuklanganda ikkala bo'limni ham yuklaymiz
document.addEventListener('DOMContentLoaded', () => {
  loadGroupsDashboard();
  loadRecentChecks();
});

// Pipeline tugagach (script.js dagi "done" state), statistikalarni yangilaymiz
document.addEventListener('DOMContentLoaded', () => {
  const originalFetch = window.fetch;
  window.fetch = function (...args) {
    const result = originalFetch.apply(this, args);
    if (typeof args[0] === 'string' && args[0].includes('/api/check_groups')) {
      result.then((response) => {
        const cloned = response.clone();
        cloned.body?.pipeThrough(new TextDecoderStream()).getReader();
      });
    }
    return result;
  };
});
