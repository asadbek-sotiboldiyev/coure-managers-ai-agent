const outputDiv = document.getElementById('output');
const reloadBtn = document.getElementById('reload-btn');
const assistantSelect = document.getElementById('assistant-select');


let allAssistants = [];

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

// Empty state
function getEmptyHTML(message = 'Hech qanday hisobotlar topilmadi') {
  return `
    <div class="empty-state">
      <div class="empty-icon">📋</div>
      <p>${message}</p>
    </div>
  `;
}

// Single report card
function getReportCard(report, assistantName) {
  const createdDate = new Date(report.created_at).toLocaleDateString('uz-UZ', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });

  return `
    <div class="report-card">
      <div class="report-header">
        <div class="report-id">
          <span class="report-id-label">O'quvchi:</span>
          <span class="report-id-value">${report.student_full_name || ('Student #' + report.student_id)}</span>
        </div>
        <div class="report-meta">
          <span class="meta-item">Guruh: <strong>${report.group_name || "Noma'lum guruh"}</strong></span>
        </div>
      </div>

      <div class="report-problem">
        <h4>Muammo:</h4>
        <p>${report.problem}</p>
      </div>

      <div class="report-summary">
        <h4>AI Xulosa:</h4>
        <p>${report.ai_summary}</p>
      </div>

      <div class="report-dates">
        <div class="date-item">
          <span class="date-label">Oxirgi murojaat:</span>
          <span class="date-value">${report.last_contacted_date}</span>
        </div>
        <div class="date-item">
          <span class="date-label">Yaratilgan:</span>
          <span class="date-value">${createdDate}</span>
        </div>
      </div>

      ${report.raw_json ? `
        <div class="report-raw">
          <details>
            <summary>Raw JSON ma'lumotlarini ko'rish</summary>
            <pre><code>${JSON.stringify(JSON.parse(report.raw_json || '{}'), null, 2)}</code></pre>
          </details>
        </div>
      ` : ''}
    </div>
  `;
}



// Load all assistants for dropdown
async function loadAssistantsForDropdown() {
  try {
    const response = await fetch('http://localhost:8000/api/assistants');
    const data = await response.json();

    if (data.status === 'success' && data.assistants) {
      allAssistants = data.assistants;
      
      // Populate dropdown
      const options = data.assistants.map(assistant => 
        `<option value="${assistant.assistant_id}">${assistant.full_name} (@${assistant.username})</option>`
      ).join('');

      assistantSelect.innerHTML = '<option value="">Assistentni tanlang...</option>' + options;
    }
  } catch (error) {
    console.error('Assistentlarni yuklanishida xatolik:', error);
  }
}

// Load reports for selected assistant
async function loadReports(assistantId) {
  if (!assistantId) {
    outputDiv.innerHTML = getEmptyHTML('Assistentni tanlang');
    return;
  }

  outputDiv.innerHTML = loadingHTML;

  try {
    const response = await fetch(`http://localhost:8000/api/assistants/${assistantId}/reports`);
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();

    // Find assistant name
    const assistant = allAssistants.find(a => a.assistant_id == assistantId);
    const assistantName = assistant ? assistant.full_name : 'Assistentlar';

    if (data.status !== 'success') {
      outputDiv.innerHTML = getErrorHTML('API xatosi: ' + (data.message || 'Noma\'lum xatolik'));
      return;
    }

    if (!data.reports || data.reports.length === 0) {
      outputDiv.innerHTML = getEmptyHTML('Bu assistentning hisobotlari yo\'q');
      return;
    }


    // Render all reports
    const reportsHTML = `
      <div class="reports-header">
        <h2>${assistantName} - Hisobotlari (${data.count})</h2>
        <p class="reports-subtitle">Jami ${data.count} ta hisobot</p>
      </div>
      <div class="reports-container">
        ${data.reports.map(report => getReportCard(report, assistantName)).join('')}
      </div>
    `;

    outputDiv.innerHTML = reportsHTML;

  } catch (error) {
    console.error('Hisobotlarni yuklanishida xatolik:', error);
    outputDiv.innerHTML = getErrorHTML('Hisobotlarni yuklanishida xatolik: ' + error.message);
  }
}

// Event listeners
if (reloadBtn) {
  reloadBtn.addEventListener('click', () => {
    const selectedId = assistantSelect.value;
    if (selectedId) {
      loadReports(selectedId);
    }
  });
}

if (assistantSelect) {
  assistantSelect.addEventListener('change', (e) => {
    loadReports(e.target.value);
  });
}

// Initial load
document.addEventListener('DOMContentLoaded', loadAssistantsForDropdown);
