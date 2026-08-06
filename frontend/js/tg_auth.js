// ===== STATE MANAGEMENT =====
let state = {
    selectedAssistantId: null,
    selectedAssistantName: null,
    phone: null,
    assistants: [],
    currentStep: 1
};

// ===== DOM ELEMENTS =====
const elements = {
    // Step 1
    assistantSearch: document.getElementById('assistant-search'),
    assistantList: document.getElementById('assistant-list'),
    selectedAssistantId: document.getElementById('selected-assistant-id'),
    selectedAssistantName: document.getElementById('selected-assistant-name'),
    phoneInput: document.getElementById('phone-input'),
    btnSendCode: document.getElementById('btn-send-code'),

    // Step 2
    codeInput: document.getElementById('code-input'),
    btnVerifyCode: document.getElementById('btn-verify-code'),
    btnBackFromCode: document.getElementById('btn-back-from-code'),

    // Step 3
    passwordInput: document.getElementById('password-input'),
    btnVerifyPassword: document.getElementById('btn-verify-password'),
    btnBackFromPassword: document.getElementById('btn-back-from-password'),

    // Step 4
    btnNewAuth: document.getElementById('btn-new-auth'),
    successInfo: document.getElementById('success-info'),

    // Alerts
    alertSuccess: document.getElementById('alert-success'),
    alertError: document.getElementById('alert-error'),
    alertWarning: document.getElementById('alert-warning')
};

// ===== HELPER FUNCTIONS =====
function showAlert(type, message, duration = 5000) {
    const alertEl = elements[`alert${type.charAt(0).toUpperCase() + type.slice(1)}`];
    if (!alertEl) return;

    alertEl.textContent = message;
    alertEl.classList.add('show');

    setTimeout(() => {
        alertEl.classList.remove('show');
    }, duration);
}

function goToStep(stepNumber) {
    // Hide all step contents
    for (let i = 1; i <= 4; i++) {
        document.getElementById(`step-${i}-content`).classList.add('hidden');
        document.getElementById(`step-${i}`).classList.remove('active');
    }

    // Show the target step
    document.getElementById(`step-${stepNumber}-content`).classList.remove('hidden');
    document.getElementById(`step-${stepNumber}`).classList.add('active');

    // Mark previous steps as done
    for (let i = 1; i < stepNumber; i++) {
        document.getElementById(`step-${i}`).classList.add('done');
        document.getElementById(`step-${i}`).classList.remove('active');
    }

    state.currentStep = stepNumber;
}

async function loadAssistants() {
    try {
        const response = await fetch('/api/assistants');
        if (!response.ok) throw new Error('Assistentlar yuklanmadi');

        const data = await response.json();
        state.assistants = data.assistants || data || [];
        renderAssistantList(state.assistants);
    } catch (error) {
        showAlert('error', `Xato: ${error.message}`);
    }
}

function renderAssistantList(assistants) {
    elements.assistantList.innerHTML = '';

    assistants.forEach(assistant => {
        const div = document.createElement('div');
        div.className = 'assistant-item';
        if (state.selectedAssistantId === assistant.assistant_id) {
            div.classList.add('selected');
        }

        const name = assistant.full_name || assistant.name || 'Noma\'lum';
        const assistantId = assistant.assistant_id || '—';

        div.innerHTML = `
            <div class="assistant-name">${name}</div>
            <div class="assistant-id">ID: ${assistantId}</div>
        `;

        div.addEventListener('click', () => selectAssistant(assistant));
        elements.assistantList.appendChild(div);
    });
}


// ===== SEARCH FUNCTIONALITY =====
// Inputga bosilganda ro'yxatni ochish
elements.assistantSearch.addEventListener('focus', () => {
    elements.assistantList.classList.add('show');
});
elements.assistantSearch.addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase();
    const filtered = state.assistants.filter(a => {
        const name = (a.first_name || a.name || '').toLowerCase();
        return name.includes(query);
    });
    renderAssistantList(filtered);
    elements.assistantList.classList.add('show');
});
// Assistent tanlanganda ro'yxatni yopish
function selectAssistant(assistant) {
    state.selectedAssistantId = assistant.assistant_id;
    state.selectedAssistantName = assistant.full_name || assistant.name || 'Noma\'lum';

    elements.selectedAssistantId.value = assistant.assistant_id;
    elements.selectedAssistantName.value = state.selectedAssistantName;
    elements.assistantSearch.value = '';
    
    elements.assistantList.classList.remove('show'); // Yopish
    renderAssistantList(state.assistants);
}

// Sahifaning istalgan boshqa joyiga bosganda ro'yxatni yopish
document.addEventListener('click', (e) => {
    if (!e.target.closest('.form-group')) {
        elements.assistantList.classList.remove('show');
    }
}); 

// ===== STEP 1: SEND CODE =====
elements.btnSendCode.addEventListener('click', async () => {
    const phone = elements.phoneInput.value.trim();

    if (!state.selectedAssistantId) {
        showAlert('error', 'Assistent tanlang');
        return;
    }

    if (!phone || !phone.startsWith('+')) {
        showAlert('error', 'Telefon raqamini to\'g\'ri kiriting (+998...)');
        return;
    }

    state.phone = phone;
    elements.btnSendCode.disabled = true;
    elements.btnSendCode.innerHTML = '<span class="loading"></span> Yuborilmoqda...';

    try {
        const response = await fetch('/telegram/assistant/send-code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                assistant_id: state.selectedAssistantId,
                phone_number: phone
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Kod yuborishlash muvaffaqiyatsiz bo\'ldi');
        }

        showAlert('success', 'Kod yuborildi. SMS orqali kodni tasdiqlang.');
        goToStep(2);
    } catch (error) {
        showAlert('error', error.message);
    } finally {
        elements.btnSendCode.disabled = false;
        elements.btnSendCode.innerHTML = 'Kod Yuborish';
    }
});

// ===== STEP 2: VERIFY CODE =====
elements.btnVerifyCode.addEventListener('click', async () => {
    const code = elements.codeInput.value.trim();

    if (!code || code.length !== 5) {
        showAlert('error', '5 raqamli kodni kiriting');
        return;
    }

    elements.btnVerifyCode.disabled = true;
    elements.btnVerifyCode.innerHTML = '<span class="loading"></span> Tekshirilmoqda...';

    try {
        const response = await fetch('/telegram/assistant/verify-code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                phone_number: state.phone,
                code: code
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Kod noto\'g\'ri');
        }

        if (data.status === '2fa_required') {
            showAlert('warning', '2FA paroli talab qilinadi');
            goToStep(3);
        } else if (data.status === 'success') {
            showSuccessStep(data);
        }
    } catch (error) {
        showAlert('error', error.message);
    } finally {
        elements.btnVerifyCode.disabled = false;
        elements.btnVerifyCode.innerHTML = 'Kodni Tasdiqlang';
    }
});

elements.btnBackFromCode.addEventListener('click', () => {
    elements.codeInput.value = '';
    goToStep(1);
});

// ===== STEP 3: VERIFY PASSWORD (2FA) =====
elements.btnVerifyPassword.addEventListener('click', async () => {
    const password = elements.passwordInput.value;

    if (!password) {
        showAlert('error', 'Parolni kiriting');
        return;
    }

    elements.btnVerifyPassword.disabled = true;
    elements.btnVerifyPassword.innerHTML = '<span class="loading"></span> Tekshirilmoqda...';

    try {
        const response = await fetch('/telegram/assistant/verify-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                phone_number: state.phone,
                password: password
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Paroli noto\'g\'ri');
        }

        if (data.status === 'success') {
            showSuccessStep(data);
        }
    } catch (error) {
        showAlert('error', error.message);
    } finally {
        elements.btnVerifyPassword.disabled = false;
        elements.btnVerifyPassword.innerHTML = 'Parolni Tasdiqlang';
    }
});

elements.btnBackFromPassword.addEventListener('click', () => {
    elements.passwordInput.value = '';
    goToStep(2);
});

// ===== STEP 4: SUCCESS =====
function showSuccessStep(data) {
    elements.successInfo.innerHTML = `
        <strong>Assistent ID:</
        <strong>Telegram User ID:</strong> ${data.tg_user_id}<br>
        <strong>Session:</strong> ${data.session_name}<br>
        <strong>Telefon:</strong> ${state.phone}
    `;
    goToStep(4);
}

elements.btnNewAuth.addEventListener('click', () => {
    // Reset state
    state.selectedAssistantId = null;
    state.selectedAssistantName = null;
    state.phone = null;
    state.currentStep = 1;

    // Reset form fields
    elements.selectedAssistantId.value = '';
    elements.selectedAssistantName.value = '';
    elements.phoneInput.value = '+998';
    elements.codeInput.value = '';
    elements.passwordInput.value = '';
    elements.assistantSearch.value = '';

    // Reset alerts
    elements.alertSuccess.classList.remove('show');
    elements.alertError.classList.remove('show');
    elements.alertWarning.classList.remove('show');

    // Go back to step 1
    renderAssistantList(state.assistants);
    goToStep(1);
});

// ===== INITIALIZATION =====
loadAssistants();
