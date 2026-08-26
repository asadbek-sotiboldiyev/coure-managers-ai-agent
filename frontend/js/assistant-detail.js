const outputDiv = document.getElementById('output');
const reloadBtn = document.getElementById('reload-btn');
const assistantNameSpan = document.getElementById('assistant-name');

// Get assistant ID from URL
const pathParts = window.location.pathname.split('/');
const assistantId = parseInt(pathParts[2], 10);

let DATA_ASSISTANTS = null;
let ALL_REPORTS = []; // Barcha reportlarni saqlash uchun

if (!assistantId || isNaN(assistantId)) {
  outputDiv.innerHTML = getErrorHTML('Noto\'g\'ri assistentning ID raqami');
}

// Loading indicator
const loadingHTML = `
  <div class="loading-state">
    <div class="spinner"></div>
    <span>Yuklanmoqda...</span>
  </div>
`;

// Error state
function getErrorHTML(message) {
  return `
    <div class="error-state">
      <div class="error-icon">⚠️</div>
      <p>${message}</p>
    </div>
  `;
}

// Get assistant info from all assistants endpoint
async function fetchAssistantInfo(id) {
  try {
    const response = await fetch(`/api/assistants`);
    if (!response.ok) throw new Error('Assistentlar ma\'lumotlarini olishda xato');
    const data = await response.json();
    DATA_ASSISTANTS = data.assistants;
    
    const assistant = data.assistants.find(a => a.assistant_id === id);
    if (!assistant) throw new Error('Assistentni topilmadi');
    
    return assistant;
  } catch (error) {
    throw new Error(`Assistentni olishda xato: ${error.message}`);
  }
}

// Get assistant reports
async function fetchAssistantReports(id) {
  try {
    const response = await fetch(`/api/assistants/${id}/reports`);
    if (!response.ok) throw new Error('Reportlarni olishda xato');
    const data = await response.json();
    return data.reports || [];
  } catch (error) {
    console.error('Reportlarni olishda xato:', error);
    return [];
  }
}

// Get student statistics for specified group IDs
async function fetchStudentStats(groupIds) {
  if (!groupIds || groupIds.length === 0) return null;
  try {
    const response = await fetch(`/api/students/stats/?group_ids=${groupIds.join(',')}`);
    if (!response.ok) throw new Error('Talabalar statistikasini olishda xato');
    const res = await response.json();
    return res.data;
  } catch (error) {
    console.error('Statistika olishda xato:', error);
    return null;
  }
}

// Render assistant info section
function getAssistantInfoHTML(assistant) {
  const statusClass = assistant.is_active ? 'active' : 'inactive';
  const statusText = assistant.is_active ? '🟢 Faol' : '🔴 Nofaol';
  
  return `
    <div class="assistant-info-section">
      <div class="assistant-avatar-large">${assistant.first_name.charAt(0).toUpperCase()}</div>
      
      <div class="assistant-header-info">
        <h2>${assistant.full_name}</h2>
        
        <div class="assistant-contact-info">
          <div class="contact-item">
            <span class="contact-label">ID</span>
            <span class="contact-value">${assistant.assistant_id}</span>
          </div>
          <div class="contact-item">
            <span class="contact-label">Foydalanuvchi nomi</span>
            <span class="contact-value">@${assistant.username}</span>
          </div>
          <div class="contact-item">
            <span class="contact-label">Telefon</span>
            <span class="contact-value">${assistant.phone_number}</span>
          </div>
        </div>
        
        <div>
          <span class="status-badge ${statusClass}">
            <span class="status-indicator"></span>
            ${statusText}
          </span>
        </div>
      </div>
    </div>
  `;
}

// Render groups section with statistics
function getGroupsHTML(groups, statsData) {
  if (!groups || groups.length === 0) {
    return `
      <div class="groups-detail-section">
        <h3 class="section-title">👥 Biriktirilgan Guruhlar</h3>
        <div class="groups-empty">
          <p>Hech qanday guruh biriktirilmagan</p>
        </div>
      </div>
    `;
  }

  const students = statsData?.students || [];
  const checked = statsData?.students_checked || [];

  // Overall Statistics across all groups
  const totalStudents = students.length;
  const totalChecked = checked.length;
  const totalResolved = checked.filter(s => s.is_resolved === 1).length;
  const totalHighScore = checked.filter(s => s.score >= 5).length;

  const groupCardsHTML = groups.map(group => {
    const gStudents = students.filter(s => s.group_id === group.group_id);
    const gChecked = checked.filter(s => s.group_id === group.group_id);
    
    const countStudents = gStudents.length;
    const countChecked = gChecked.length;
    const countResolved = gChecked.filter(s => s.is_resolved === 1).length;
    const countHighScore = gChecked.filter(s => s.score >= 5).length;
    const countLowScore = gChecked.filter(s => s.score < 5).length;

    const isChecked = gChecked.length > 0;

    const detailsHTML = `
    <div class="group-detail-row">
            <span class="group-detail-label">Talabalar soni:</span>
            <span class="group-detail-value">${countStudents}</span>
          </div><hr>
          <div class="group-detail-row">
            <span class="group-detail-label">Tekshirilganlar:</span>
            <span class="group-detail-value">${countChecked}</span>
          </div><hr>
          <div class="group-detail-row">
            <span class="group-detail-label">Hal etilgan (Resolved):</span>
            <span class="group-detail-value">${countResolved}</span>
          </div><hr>
          <div class="group-detail-row">
            <span class="group-detail-label">Yuqori ball (Score ≥ 5):</span>
            <span class="group-detail-value">${countHighScore}</span>
          </div><hr>
          <div class="group-detail-row">
            <span class="group-detail-label">Past ball (Score < 5):</span>
            <span class="group-detail-value">${countLowScore}</span>
          </div>
        `

    return `
      <div class="group-card">
        <div class="group-card-header">
          <h4 class="group-card-title">${group.group_name}(${group.group_id})</h4>
        </div>
        
        <div class="group-card-details">
          
          ${!isChecked ? `
        <div style="margin-top: 1rem;">
          <p style='margin-bottom:5px'>Bu guruh uchun hali tekshirishlar mavjud emas.</p>
          <a style='display:inline-block;text-decoration:none' class='btn-primary' href="/group-check?group_id=${group.group_id}" class="btn-check">Tekshirish</a>
        </div>
      ` : detailsHTML}
        </div>
      </div>
    `;
  }).join('');


  return `
    <div class="groups-detail-section">
      <h3 class="section-title">👥 Biriktirilgan Guruhlar (${groups.length})</h3>
      
      <!-- Overall Stats Summary Card -->
      <div class="overall-stats-card" style="margin-bottom: 1.5rem; padding: 1rem; background: var(--bg-surface, #f8f9fa); border-radius: 8px;">
        <h4>📊 Umumiy Guruhlar Statistikasi</h4>
        <div style="display: flex; gap: 1.5rem; flex-wrap: wrap; margin-top: 0.5rem;">
          <div><strong>Jami talabalar:</strong> ${totalStudents}</div>
          <div><strong>Jami tekshirilgan:</strong> ${totalChecked}</div>
          <div><strong>Hal etilgan:</strong> ${totalResolved}</div>
          <div><strong>Yuqori ball (≥ 5):</strong> ${totalHighScore}</div>
        </div>
      </div>

      <div class="groups-grid">
        ${groupCardsHTML}
      </div>
    </div>
  `;
}

// Render single report card
function getReportCardHTML(report) {
  const createdDate = new Date(report.created_at).toLocaleDateString('uz-UZ', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });

  const lastContactedDisplay = report.last_contacted_date || 'Noma\'lum';

  const recommendationsHTML = report.raw_json && report.raw_json.recommendations
    ? `
      <div class="report-recommendations">
        <h4>Tavsiyalar:</h4>
        <p>${report.raw_json.recommendations}</p>
      </div>
    `
    : '';

  return `
    <div class="report-card">
      <div class="report-header">
        <div>
          <span class="report-id-label">O'quvchi:</span>
          <span class="report-id-value">${report.student_full_name || ('Student #' + report.student_id)}</span>
        </div>
        <div class="report-meta">
          <span>Guruh: <strong>${report.group_name || "Noma'lum guruh"}</strong></span>
        </div>
      </div>

      ${report.problem ? `
        <div class="report-problem">
          <h4>Muammo:</h4>
          <p>${report.problem}</p>
        </div>
      ` : ''}

      ${report.ai_summary ? `
        <div class="report-summary">
          <h4>AI Xulosa:</h4>
          <p>${report.ai_summary}</p>
        </div>
      ` : ''}

      ${recommendationsHTML}

      <div class="report-dates">
        <div class="date-item">
          <span class="date-label">Oxirgi murojaat:</span>
          <span class="date-value">${lastContactedDisplay}</span>
        </div>
        <div class="date-item">
          <span class="date-label">Yaratilgan:</span>
          <span class="date-value">${createdDate}</span>
        </div>
      </div>
    </div>
  `;
}

// Render reports section
function getReportsHTML(reports, groups = []) {
  const rawReports = reports || [];

  // Har bir talaba bo'yicha eng oxirgi reportni ajratib olish
  const latestReportsMap = new Map();

  rawReports.forEach(report => {
    const existing = latestReportsMap.get(report.student_id);
    
    if (!existing) {
      latestReportsMap.set(report.student_id, report);
    } else {
      // created_at sanasini solishtirib eng oxirgisini saqlaymiz
      const existingDate = new Date(existing.created_at);
      const currentDate = new Date(report.created_at);
      
      if (currentDate > existingDate) {
        latestReportsMap.set(report.student_id, report);
      }
    }
  });

  // Map'dan massiv hosil qilamiz va ALL_REPORTS'ga beramiz
  ALL_REPORTS = Array.from(latestReportsMap.values());

  // Select option larini shakllantirish
  const groupOptionsHTML = groups.map(g => `
    <option value="${g.group_id}">${g.group_name}</option>
  `).join('');

  return `
    <div class="reports-section">
      <div class="reports-header-actions" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
        <h3 class="section-title" style="margin: 0;">📋 Oxirgi AI Hisobotlar</h3>
        
        <select id="group-report-filter" style="padding: 6px 12px; border-radius: 6px; border: 1px solid var(--border-color, #ccc);">
          <option value="">Barcha guruhlar</option>
          ${groupOptionsHTML}
        </select>
      </div>

      <div id="reports-container-wrapper">
        ${getReportsListHTML(ALL_REPORTS)}
      </div>
    </div>
  `;
}
function getReportsListHTML(reports) {
  if (!reports || reports.length === 0) {
    return `
      <div class="reports-empty">
        <p>Hech qanday hisobotlar topilmadi</p>
      </div>
    `;
  }

  const reportCardsHTML = reports.slice(0, 10).map(report => getReportCardHTML(report)).join('');

  return `
    <div class="reports-container">
      ${reportCardsHTML}
    </div>
    ${reports.length > 10 ? `<p style="text-align: center; color: var(--text-muted); margin-top: 1rem;">va yana ${reports.length - 10} ta...</p>` : ''}
  `;
}

// Main render function
async function renderPage() {
  outputDiv.innerHTML = loadingHTML;
  
  try {
    const [assistant, reports] = await Promise.all([
      fetchAssistantInfo(assistantId),
      fetchAssistantReports(assistantId)
    ]);

    assistantNameSpan.textContent = assistant.full_name;

    // Fetch stats for all groups belonging to the current assistant
    const groupIds = (assistant.groups || []).map(g => g.group_id);
    const statsData = await fetchStudentStats(groupIds);

    const html = `
      ${getAssistantInfoHTML(assistant)}
      ${getGroupsHTML(assistant.groups, statsData)}
      ${getReportsHTML(reports, assistant.groups)}
    `;

    outputDiv.innerHTML = html;
  } catch (error) {
    console.error('Sahifani yuklashda xato:', error);
    outputDiv.innerHTML = getErrorHTML(error.message);
  }
}

// Event listeners
reloadBtn?.addEventListener('click', renderPage);

// Filter o'zgarganda ishlaydigan listener
outputDiv.addEventListener('change', (e) => {
  if (e.target && e.target.id === 'group-report-filter') {
    const selectedGroupId = e.target.value;
    
    // Tanlangan guruh bo'yicha filterlash (bo'sh bo'lsa hammasi)
    const filteredReports = selectedGroupId 
      ? ALL_REPORTS.filter(r => String(r.group_id) === String(selectedGroupId))
      : ALL_REPORTS;

    // Faqat reportlar konteynerini yangilash
    const container = document.getElementById('reports-container-wrapper');
    if (container) {
      container.innerHTML = getReportsListHTML(filteredReports);
    }
  }
});

// Initial render
renderPage();