const outputDiv = document.getElementById('output');
const reloadBtn = document.getElementById('reload-btn');

let assistantsData = [];  // Global variable to store assistants data

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
function getEmptyHTML() {
  return `
    <div class="empty-state">
      <div class="empty-icon">👤</div>
      <p>Hech qanday assistentlar topilmadi</p>
    </div>
  `;
}

// Single assistant card
function getAssistantCard(assistant) {
  const groupsHTML = assistant.groups && assistant.groups.length > 0
    ? `
      <div class="groups-section">
        <h4>Guruhlar:</h4>
        <div class="groups-list">
          ${assistant.groups.map(group => `
            <span class="group-badge ${group.is_active ? 'active' : 'inactive'}">
              ${group.group_name}
              <span class="status-dot"></span>
            </span>
          `).join('')}
        </div>
      </div>
    `
    : '';

  return `
    <div class="assistant-card">
      <div class="assistant-header">
        <div class="assistant-avatar">${assistant.first_name.charAt(0).toUpperCase()}</div>
        <div class="assistant-info">
          <h3><a href="/assistant/${assistant.assistant_id}" class="assistant-name-link">${assistant.full_name}</a></h3>
          <p class="assistant-username">@${assistant.username}</p>
        </div>
        <div class="assistant-status ${assistant.is_active ? 'active' : 'inactive'}">
          <span class="status-indicator"></span>
          ${assistant.is_active ? 'Faol' : 'Nofaol'}
        </div>
      </div>

      <div class="assistant-details">
        <div class="detail-row">
          <span class="detail-label">ID:</span>
          <span class="detail-value">${assistant.assistant_id}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Telefon:</span>
          <span class="detail-value">${assistant.phone_number}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Telegram:</span>
          <span class="tg-status-badge ${assistant.tg_connected ? 'tg-connected' : 'tg-not-connected'}">
            <span class="status-dot"></span>
            ${assistant.tg_connected ? 'Ulangan' : 'Ulanmagan'}
          </span>
        </div>
      </div>

      ${groupsHTML}
    </div>
  `;
}

function renderAssistants(assistants) {
  if (!assistants || assistants.length === 0) {
    outputDiv.innerHTML = getEmptyHTML();
    return;
  }
  const assistantsHTML = `
      <div class="assistants-header">
        <h2>Assistentlar (${assistants.length})</h2>
      </div>
      <div class="assistants-container">
        ${assistants.map(assistant => getAssistantCard(assistant)).join('')}
      </div>
    `;
    outputDiv.innerHTML = assistantsHTML;
}


// Main render function
async function loadAssistants() {
  outputDiv.innerHTML = loadingHTML;

  try {
    const response = await fetch('http://localhost:8000/api/assistants');
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();

    if (data.status !== 'success') {
      outputDiv.innerHTML = getErrorHTML('API xatosi: ' + (data.message || 'Noma\'lum xatolik'));
      return;
    }

    if (!data.assistants || data.assistants.length === 0) {
      outputDiv.innerHTML = getEmptyHTML();
      return;
    }
    // Render all assistants
    let sorted_assistants = data.assistants
      .sort((a, b) => {
        // 1. Avval is_active bo'yicha tekshiramiz: true bo'lganlar (1) oldinga o'tadi
        if (a.is_active !== b.is_active) {
          return b.is_active - a.is_active; // true (1) - false (0) natijasi musbat chiqib, true ni oldinga qo'yadi
        }
        
        // 2. Agar is_active holatlari bir xil bo'lsa, groups uzunligi kattasi tepaga chiqadi
        return b.groups.length - a.groups.length;
      });
    assistantsData = sorted_assistants;  // Update the global variable with sorted data
    renderAssistants(sorted_assistants);

  } catch (error) {
    console.error('Assistentlarni yuklanishida xatolik:', error);
    outputDiv.innerHTML = getErrorHTML('Assistentlarni yuklanishida xatolik: ' + error.message);
  }
}

function filterAssistants(searchTerm) {
  
  const filteredAssistants = assistantsData.filter(assistant => {
    const fullNameMatch = assistant.full_name.toLowerCase().includes(searchTerm.toLowerCase());
    const usernameMatch = assistant.username.toLowerCase().includes(searchTerm.toLowerCase());
    return fullNameMatch || usernameMatch;
  });
  renderAssistants(filteredAssistants);
}

function clearInput(){
  const searchInput = document.getElementById('search-input');
  searchInput.value = '';
  if (searchInput) {
    renderAssistants(assistantsData);  // Show all assistants when input is cleared
  }
}


// Event listeners
if (reloadBtn) {
  reloadBtn.addEventListener('click', loadAssistants);
}

// Initial load
document.addEventListener('DOMContentLoaded', loadAssistants);
