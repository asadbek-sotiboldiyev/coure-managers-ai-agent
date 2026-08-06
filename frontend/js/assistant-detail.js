const outputDiv = document.getElementById('output');
const reloadBtn = document.getElementById('reload-btn');
const assistantNameSpan = document.getElementById('assistant-name');

// Get assistant ID from URL
const pathParts = window.location.pathname.split('/');
const assistantId = parseInt(pathParts[2], 10);

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

// Render groups section
function getGroupsHTML(groups) {
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

  const groupCardsHTML = groups.map(group => `
    <div class="group-card">
      <div class="group-card-header">
        <h4 class="group-card-title">${group.group_name}</h4>
        <span class="group-card-status ${group.is_active ? 'active' : 'inactive'}">
          ${group.is_active ? '✓ Faol' : '✗ Nofaol'}
        </span>
      </div>
      
      <div class="group-card-details">
        <div class="group-detail-row">
          <span class="group-detail-label">Guruh ID:</span>
          <span class="group-detail-value">${group.group_id}</span>
        </div>
        <div class="group-detail-row">
          <span class="group-detail-label">Status:</span>
          <span class="group-detail-value">${group.status}</span>
        </div>
      </div>
    </div>
  `).join('');

  return `
    <div class="groups-detail-section">
      <h3 class="section-title">👥 Biriktirilgan Guruhlar (${groups.length})</h3>
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
function getReportsHTML(reports) {
  if (!reports || reports.length === 0) {
    return `
      <div class="reports-section">
        <h3 class="section-title">📋 Oxirgi AI Hisobotlar</h3>
        <div class="reports-empty">
          <p>Hech qanday hisobotlar topilmadi</p>
        </div>
      </div>
    `;
  }

  const reportCardsHTML = reports.slice(0, 10).map(report => getReportCardHTML(report)).join('');

  return `
    <div class="reports-section">
      <h3 class="section-title">📋 Oxirgi AI Hisobotlar (Jami: ${reports.length})</h3>
      <div class="reports-container">
        ${reportCardsHTML}
      </div>
      ${reports.length > 10 ? `<p style="text-align: center; color: var(--text-muted); margin-top: 1rem;">va yana ${reports.length - 10} ta...</p>` : ''}
    </div>
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

    const html = `
      ${getAssistantInfoHTML(assistant)}
      ${getGroupsHTML(assistant.groups)}
      ${getReportsHTML(reports)}
    `;

    outputDiv.innerHTML = html;
  } catch (error) {
    console.error('Sahifani yuklashda xato:', error);
    outputDiv.innerHTML = getErrorHTML(error.message);
  }
}

// Event listeners
reloadBtn?.addEventListener('click', renderPage);

// Initial render
renderPage();
