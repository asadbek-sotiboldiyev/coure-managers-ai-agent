const outputDiv = document.getElementById('output');
const reloadBtn = document.getElementById('reload-btn');

let assistantsData = [];

const loadingHTML = `
  <div class="loading-state">
    <div class="spinner"></div>
    <span>Yuklanmoqda...</span>
  </div>
`;

function getErrorHTML(message) {
  return `
    <div class="error-state">
      <div class="error-icon">⚠️</div>
      <p>${message}</p>
    </div>
  `;
}

function getEmptyHTML() {
  return `
    <div class="empty-state">
      <div class="empty-icon">👤</div>
      <p>Hech qanday assistent topilmadi</p>
    </div>
  `;
}

function getAssistantRow(assistant) {
  const disabled = assistant.is_disabled;
  return `
    <div class="settings-row ${disabled ? 'disabled-row' : ''}" data-id="${assistant.assistant_id}">
      <div class="settings-row-info">
        <div class="settings-avatar">${(assistant.full_name || '?').charAt(0).toUpperCase()}</div>
        <div>
          <h3>${assistant.full_name || 'Noma\'lum'}</h3>
          <p class="settings-username">@${assistant.username || '-'} &middot; ID: ${assistant.assistant_id}</p>
        </div>
      </div>
      <div class="settings-row-actions">
        <span class="settings-status ${disabled ? 'status-disabled' : 'status-enabled'}">
          <span class="status-dot"></span>
          ${disabled ? "O'chirilgan" : 'Faol'}
        </span>
        <button class="btn-toggle ${disabled ? 'btn-enable' : 'btn-disable'}" data-id="${assistant.assistant_id}" data-disabled="${disabled}">
          ${disabled ? "Qayta yoqish" : "O'chirish"}
        </button>
      </div>
    </div>
  `;
}

function renderAssistants(assistants) {
  if (!assistants || assistants.length === 0) {
    outputDiv.innerHTML = getEmptyHTML();
    return;
  }
  outputDiv.innerHTML = `
    <div class="settings-list">
      ${assistants.map(a => getAssistantRow(a)).join('')}
    </div>
  `;

  outputDiv.querySelectorAll('.btn-toggle').forEach(btn => {
    btn.addEventListener('click', onToggleClick);
  });
}

async function onToggleClick(e) {
  const btn = e.currentTarget;
  const assistantId = btn.dataset.id;
  const isDisabled = btn.dataset.disabled === 'true';
  const action = isDisabled ? 'enable' : 'disable';

  btn.disabled = true;
  btn.textContent = '...';

  try {
    const response = await fetch(`http://localhost:8000/api/settings/assistants/${assistantId}/${action}`, {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    await response.json();
    await loadAssistants();
  } catch (error) {
    console.error('Holatni o\'zgartirishda xatolik:', error);
    alert('Xatolik yuz berdi: ' + error.message);
    btn.disabled = false;
    btn.textContent = isDisabled ? 'Qayta yoqish' : "O'chirish";
  }
}

async function loadAssistants() {
  outputDiv.innerHTML = loadingHTML;

  try {
    const response = await fetch('http://localhost:8000/api/settings/assistants');

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();

    if (data.status !== 'success') {
      outputDiv.innerHTML = getErrorHTML('API xatosi: ' + (data.message || 'Noma\'lum xatolik'));
      return;
    }

    assistantsData = data.assistants || [];
    renderAssistants(assistantsData);

  } catch (error) {
    console.error('Assistentlarni yuklanishida xatolik:', error);
    outputDiv.innerHTML = getErrorHTML('Assistentlarni yuklanishida xatolik: ' + error.message);
  }
}

function filterAssistants(searchTerm) {
  const term = searchTerm.toLowerCase();
  const filtered = assistantsData.filter(a => {
    const nameMatch = (a.full_name || '').toLowerCase().includes(term);
    const usernameMatch = (a.username || '').toLowerCase().includes(term);
    return nameMatch || usernameMatch;
  });
  renderAssistants(filtered);
}

if (reloadBtn) {
  reloadBtn.addEventListener('click', loadAssistants);
}

document.addEventListener('DOMContentLoaded', loadAssistants);
