const outputDiv = document.getElementById('output');
const startBtn = document.getElementById('start-analysis-btn');
const assistantSearch = document.getElementById('assistant-search');
const assistantList = document.getElementById('assistant-list');
const selectedAssistantId = document.getElementById('selected-assistant-id');
const selectedAssistantName = document.getElementById('selected-assistant-name');
const groupsContainer = document.getElementById('groups-container');
const selectAllBtn = document.getElementById('select-all-btn');
const deselectAllBtn = document.getElementById('deselect-all-btn');

let selectedGroups = [];
let assistantsData = [];
let filteredAssistants = [];


const workingLabel = `<div id="current-state">
      <div class="loader-wrapper">
        <div class="spinner"></div>
        <span>Working...</span>
      </div>
    </div>`

// Indikator/loader holatini tozalovchi yordamchi funksiya
function removeActiveCheckingLoaders() {
    const activeLoaders = outputDiv.querySelectorAll('.checking-loader');
    activeLoaders.forEach(loader => loader.remove());
}

// Assistentlarni va guruhlarni yuklash
async function loadAssistantsAndGroups() {
    try {
        const response = await fetch('/api/assistants');
        const data = await response.json();
        // Faqat Telegram akkаunti ulangan assistentlar ro'yxatda ko'rsatiladi
        assistantsData = (data.assistants || []).filter(asst => asst.tg_connected);
        filteredAssistants = [...assistantsData];
        renderAssistantList();
    } catch (error) {
        console.error('Assistentlarni yuklashda xatolik:', error);
        assistantList.innerHTML = '<div class="assistant-item" style="color: red;">Xatolik yuz berdi</div>';
    }
}

// Assistentlar ro'yxatini render qilish
function renderAssistantList() {
    assistantList.innerHTML = '';
    
    if (filteredAssistants.length === 0) {
        const emptyMsg = assistantsData.length === 0
            ? 'Telegram akkаunti ulangan assistent topilmadi'
            : 'Topilmadi';
        assistantList.innerHTML = `<div class="assistant-item" style="cursor: default;">${emptyMsg}</div>`;
        return;
    }
    
    filteredAssistants.forEach(asst => {
        const div = document.createElement('div');
        div.className = 'assistant-item';
        if (asst.assistant_id == selectedAssistantId.value) {
            div.classList.add('selected');
        }
        
        div.innerHTML = `
            <div class="assistant-name">${asst.full_name}</div>
            <div class="assistant-id">ID: ${asst.assistant_id}</div>
        `;
        
        div.addEventListener('click', () => {
            selectAssistant(asst);
        });
        
        assistantList.appendChild(div);
    });
}

// Assistentni tanlash
function selectAssistant(asst) {
    selectedAssistantId.value = asst.assistant_id;
    selectedAssistantName.value = asst.full_name;
    assistantSearch.value = asst.full_name;
    assistantList.classList.remove('show');
    displayGroups(asst);
    selectedGroups = [];
    startBtn.disabled = true;
}

// Tanlangan assistentning guruhlarini ko'rsatish
function displayGroups(selectedAssistant) {
    if (!selectedAssistant || !selectedAssistant.groups || selectedAssistant.groups.length === 0) {
        groupsContainer.innerHTML = '<p style="color: var(--text-muted); font-size: 14px;">Hech qanday guruh topilmadi</p>';
        selectAllBtn.style.display = 'none';
        deselectAllBtn.style.display = 'none';
        startBtn.disabled = true;
        selectedGroups = [];
        return;
    }
    
    groupsContainer.innerHTML = '';
    selectedAssistant.groups.forEach(group => {
        const label = document.createElement('label');
        label.className = 'group-checkbox';
        label.innerHTML = `
            <input type="checkbox" value="${group.group_id}" data-name="${group.group_name}">
            <span>${group.group_name}</span>
        `;
        
        label.querySelector('input').addEventListener('change', (e) => {
            if (e.target.checked) {
                selectedGroups.push({ id: group.group_id, name: group.group_name });
            } else {
                selectedGroups = selectedGroups.filter(g => g.id !== group.group_id);
            }
            startBtn.disabled = selectedGroups.length === 0;
            updateSelectAllButtons();
        });
        
        groupsContainer.appendChild(label);
    });
    
    selectAllBtn.style.display = 'inline-block';
    deselectAllBtn.style.display = 'inline-block';
    updateSelectAllButtons();
}

function updateSelectAllButtons() {
    const checkboxes = groupsContainer.querySelectorAll('input[type="checkbox"]');
    const checkedCount = groupsContainer.querySelectorAll('input[type="checkbox"]:checked').length;
    const totalCount = checkboxes.length;
    
    selectAllBtn.disabled = checkedCount === totalCount;
    deselectAllBtn.disabled = checkedCount === 0;
}

function selectAllGroups() {
    const checkboxes = groupsContainer.querySelectorAll('input[type="checkbox"]');
    selectedGroups = [];
    checkboxes.forEach(cb => {
        cb.checked = true;
        selectedGroups.push({
            id: cb.value,
            name: cb.dataset.name
        });
    });
    startBtn.disabled = selectedGroups.length === 0;
    updateSelectAllButtons();
}

function deselectAllGroups() {
    const checkboxes = groupsContainer.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(cb => cb.checked = false);
    selectedGroups = [];
    startBtn.disabled = true;
    updateSelectAllButtons();
}

// Qidiruv funksiyasi
function filterAssistants(searchText) {
    const searchLower = searchText.toLowerCase();
    filteredAssistants = searchText.trim() === ''
        ? [...assistantsData]
        : assistantsData.filter(asst =>
            asst.full_name.toLowerCase().includes(searchLower) ||
            asst.assistant_id.toString().includes(searchLower)
        );
    renderAssistantList();
    assistantList.classList.add('show');
}

// ------------------------------------------------------------------
// 1-BOSQICH: PREVIEW -- DB'dan olingan xom studentlar ro'yxati + AI
// tomonidan aniqlangan muammoli studentlar. Bu bosqich streaming EMAS --
// bitta oddiy so'rov, natija kelgach jadval ko'rsatiladi va pipeline
// "Davom etish" tugmasi bosilguncha shu yerda to'xtab turadi.
// ------------------------------------------------------------------
let currentPreviewId = null;

async function startPreview() {
    outputDiv.innerHTML = workingLabel;
    currentPreviewId = null;

    const groupIds = selectedGroups.map(g => g.id);
    const assistantId = selectedAssistantId.value;

    try {
        const response = await fetch("/api/check_groups/preview", {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                assistant_id: assistantId,
                group_ids: groupIds
            })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            outputDiv.innerHTML = `<div class="status-check-card error-card"><span>⚠️ ${err.detail || 'Preview olishda xatolik yuz berdi.'}</span></div>`;
            return;
        }

        const result = await response.json();
        console.log(result);
        currentPreviewId = result.preview_id;
        result.groups.forEach(group => {
            group.students.forEach(student => {
                STUDENTS[student.student_id] = student;
            });
        })

        outputDiv.innerHTML = makePreviewHTML(result);

        const continueBtn = document.getElementById('continue-analysis-btn');
        if (continueBtn) {
            continueBtn.addEventListener('click', () => startContinueStream(currentPreviewId));
        }
    } catch (error) {
        console.error("Preview olishda xatolik:", error);
        outputDiv.innerHTML = `<div class="status-check-card error-card"><span>⚠️ Preview olishda xatolik yuz berdi.</span></div>`;
    } finally {
        startBtn.disabled = false;
    }
}

// ------------------------------------------------------------------
// 2-BOSQICH: CONTINUE -- foydalanuvchi "Davom etish"ni bosgach, preview_id
// bilan chat + AI-summary bosqichini streaming tarzda ishga tushiradi.
// ------------------------------------------------------------------
async function startContinueStream(previewId) {
    if (!previewId) return;

    const previewSection = document.getElementById('preview-section');
    const continueBtn = document.getElementById('continue-analysis-btn');
    if (continueBtn) {
        continueBtn.disabled = true;
        continueBtn.textContent = 'Ishlanmoqda...';
    }

    // Natijalar preview jadvalidan keyin shu blokka qo'shiladi.
    const resultsBlock = document.createElement('div');
    resultsBlock.id = 'continue-results';
    resultsBlock.innerHTML = workingLabel;
    outputDiv.appendChild(resultsBlock);

    try {
        const response = await fetch("/api/check_groups/continue", {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                preview_id: previewId
            })
        });

        const reader = response.body
            .pipeThrough(new TextDecoderStream())
            .getReader();

        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) {
                const currentStateDiv = resultsBlock.querySelector('#current-state');
                if (currentStateDiv) currentStateDiv.remove();
                break;
            };

            buffer += value;
            const lines = buffer.split('\n');

            buffer = lines.pop();

            for (const line of lines) {
                if (!line.trim()) continue;

                try {
                    const parsedData = JSON.parse(line);
                    console.log(line)

                    if (parsedData.state === "summary" || parsedData.state === "error") {
                        const activeLoaders = resultsBlock.querySelectorAll('.checking-loader');
                        activeLoaders.forEach(loader => loader.remove());
                    }

                    const htmlContent = makeElement(parsedData);
                    if (htmlContent) {
                        const currentStateDiv = resultsBlock.querySelector('#current-state');
                        if (currentStateDiv) {
                            currentStateDiv.insertAdjacentHTML('beforebegin', htmlContent);
                        } else {
                            resultsBlock.insertAdjacentHTML('beforeend', htmlContent);
                        }
                    }

                    if (parsedData.state === "done") {
                        const currentStateDiv = resultsBlock.querySelector('#current-state');
                        if (currentStateDiv) {
                            currentStateDiv.remove();
                        }
                    }

                } catch (err) {
                    console.error("JSON Parsing xatosi:", err, line);
                }
            }
        }
    } catch (error) {
        console.error("Stream yuklanishida xatolik:", error);
    } finally {
        if (continueBtn) {
            continueBtn.disabled = true;
            continueBtn.textContent = 'Yakunlandi';
        }
    }
}

function handleStartClick(e) {
    e.preventDefault();
    startBtn.disabled = true;
    startPreview();
}

// Event listeners
if (assistantSearch) {
    assistantSearch.addEventListener('input', (e) => {
        filterAssistants(e.target.value);
    });
    
    assistantSearch.addEventListener('focus', () => {
        filteredAssistants = [...assistantsData];
        renderAssistantList();
        assistantList.classList.add('show');
    });
}

// Document click - dropdown yopish
document.addEventListener('click', (e) => {
    if (!e.target.closest('.control-section:first-child') && assistantList.classList.contains('show')) {
        assistantList.classList.remove('show');
    }
});

if (selectAllBtn) {
    selectAllBtn.addEventListener('click', selectAllGroups);
}

if (deselectAllBtn) {
    deselectAllBtn.addEventListener('click', deselectAllGroups);
}

if (startBtn) {
    startBtn.addEventListener('click', handleStartClick);
}

// Sahifa yuklanganda assistentlarni va guruhlarni olish
document.addEventListener('DOMContentLoaded', loadAssistantsAndGroups);
