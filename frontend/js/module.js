// ==============================================================================
// main_app/orchestrator.py -> run_full_pipeline_stream() dan kelishi mumkin
// bo'lgan barcha {"state": ..., "data": ...} shaklidagi hodisalarni HTML'ga
// o'giruvchi modul.
//
// Mumkin bo'lgan state'lar:
//   - "error"            -> {stage, message, group_ids?, assistant_id?, student_id?}
//   - "accounts_batches"  -> {group_ids, students: []}  (muammoli student topilmadi)
//   - "accounts"          -> {group_ids, students: [{student_id, full_name, group_id,
//                             problem, assistant: {assistant_id, full_name}}]}
//   - "chat_history_checking" -> {student: {student_id, assistant_id, problem,
//                             message_count, messages: [...], skipped_reason?}}
//   - "summary"           -> InteractionReport (flat dict): {assistant_id, student_id,
//                             support_quality_score, addressed_issues,
//                             discussed_flagged_problem, summary, recommendations,
//                             problem, raw_model_response, last_contacted_date}
//   - "done"              -> {total_reports}
// ==============================================================================

// Kichik yordamchi: HTML-injection oldini olish uchun matnni escape qilish
function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function formatDate(value) {
    if (!value) return "Noma'lum";
    try {
        const d = new Date(value);
        if (isNaN(d.getTime())) return escapeHtml(value);
        return d.toLocaleString('uz-UZ', {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit'
        });
    } catch (e) {
        return escapeHtml(value);
    }
}

// ------------------------------------------------------------------
// STATE: accounts
// Muammoli deb topilgan studentlar (assistantga bog'langan) ro'yxati.
// ------------------------------------------------------------------
function makeAccountsHTML(data) {
    const students = data.students || [];
    const groupIds = data.group_ids || [];

    if (students.length === 0) {
        return `
        <div class="accounts">
            <div class="accounts-header">
                <h2>Guruhlar tekshirildi (${groupIds.join(', ')}) -- muammoli student topilmadi</h2>
            </div>
        </div>`;
    }

    const students_list = students.map(st => `
        <li class="students-li">
            <div class="left">
                <h3>${escapeHtml(st.full_name)} <span style="color: var(--text-muted); font-weight: 400;">(ID: ${escapeHtml(st.student_id)})</span></h3>
            </div>
            <div class="right">
                <h3>${escapeHtml(st.problem)}</h3>
            </div>
        </li>
    `).join('');

    return `
        <div class="accounts">
            <div class="accounts-header">
                <h2>Muammoli deb topilgan o'quvchilar ${students.length} ta</h2>
            </div>
            <ul class="students-ul">
                ${students_list}
            </ul>
        </div>
    `;
}

// ------------------------------------------------------------------
// PREVIEW: DB'dan olingan xom (AI ga yuborilmasdan oldingi) studentlar
// ma'lumoti. Har bir guruh uchun alohida nomlangan jadval, muammoli
// studentlar (has_problem=true) alohida rangda ajratiladi. Pastda
// "Davom etish" tugmasi chiqadi -- shu bosilgandagina keyingi (chat + AI
// summary) bosqich boshlanadi.
// ------------------------------------------------------------------
function makePreviewHTML(previewResult) {
    const groups = previewResult.groups || [];
    const problematicCount = previewResult.problematic_count ?? 0;

    const groupsHtml = groups.map(g => {
        const rows = (g.students || []).map(st => `
            <tr class="${st.has_problem ? 'preview-row-problem' : ''}">
                <td>${escapeHtml(st.student_id)}</td>
                <td>${escapeHtml(st.full_name)}</td>
                <td>${escapeHtml(st.uploaded_homeworks_count)}</td>
                <td>${escapeHtml(st.last_upload_date || "—")}</td>
                <td>${st.has_problem ? `<span class="flag-badge flag-bad">${escapeHtml(st.problem || 'Muammo')}</span>` : `<span class="flag-badge flag-good">Muammo yo'q</span>`}</td>
            </tr>
        `).join('');

        const progress = g.progress || {};
        const progressLine = [
            progress.module ? `Modul: ${escapeHtml(progress.module)}` : null,
            progress.tool ? `Yo'nalish: ${escapeHtml(progress.tool)}` : null,
            progress.current_lesson ? `Dars: ${escapeHtml(progress.current_lesson)} (№${escapeHtml(progress.current_lesson_number)})` : null,
        ].filter(Boolean).join(' • ');

        return `
        <div class="preview-group-table">
            <h3>Guruh: ${escapeHtml(g.group_name)} <span style="color: var(--text-muted); font-weight: 400;">(ID: ${escapeHtml(g.group_id)}, ${(g.students || []).length} ta student)</span></h3>
            ${progressLine ? `<p class="preview-group-progress" style="color: var(--text-muted); font-size: 0.85rem; margin: 0 0 10px;">${progressLine}</p>` : ''}
            <table class="preview-table">
                <thead>
                    <tr>
                        <th>Student ID</th>
                        <th>F.I.Sh.</th>
                        <th>Topshirilgan HW (joriy modul)</th>
                        <th>Oxirgi topshirgan sana</th>
                        <th>Holat</th>
                    </tr>
                </thead>
                <tbody>
                    ${rows || '<tr><td colspan="5" style="color: var(--text-muted);">Studentlar topilmadi</td></tr>'}
                </tbody>
            </table>
        </div>
        `;
    }).join('');

    return `
    <div id="preview-section" class="preview-section">
        <div class="accounts-header">
            <h2>Tekshirilgan o'quvchilar ro'yxati (jami ${problematicCount} ta muammoli topildi)</h2>
        </div>
        ${groupsHtml}
        <div class="preview-actions">
            <button id="continue-analysis-btn" class="btn-primary" ${problematicCount === 0 ? 'disabled' : ''}>
                ${problematicCount === 0 ? "Muammoli o'quvchi yo'q" : `Davom etish (${problematicCount} ta student uchun AI tahlili)`}
            </button>
        </div>
    </div>
    `;
}

// ------------------------------------------------------------------
// STATE: accounts_batches
// Berilgan guruhlarda umuman muammoli student topilmagan holat
// (pipeline shu yerda erta to'xtaydi, "done" keyin darhol keladi).
// ------------------------------------------------------------------
function makeAccountsBatchesHTML(data) {
    const groupIds = data.group_ids || [];
    return `
        <div class="status-check-card" style="border-style: solid;">
            ℹ️ Guruhlar (${groupIds.join(', ') || '—'}) tekshirildi, muammoli student aniqlanmadi.
        </div>
    `;
}

// ------------------------------------------------------------------
// STATE: chat_history_checking
// Har bir student uchun chat tarixi olinayotgani (yoki o'tkazib
// yuborilgani) haqida holat kartasi.
// ------------------------------------------------------------------
function makeChatCheckingHTML(data) {
    const student = data.student || {};
    const skipped = student.skipped_reason;

    if (skipped === 'no_new_messages') {
        return `
        <div class="status-check-card">
            <span class="dot" style="background: var(--text-muted);"></span>
            <span>O'tkazib yuborildi <b>(${student.student_name})</b> -- yangi xabar topilmadi.</span>
        </div>
        `;
    }

    return `
        <div class="status-check-card checking-loader">
            <span class="dot"></span>
            <span>Chat tarixi tekshirilmoqda... <b>(${student.student_name})</b> -- ${escapeHtml(student.message_count ?? 0)} ta xabar</span>
        </div>
    `;
}

// ------------------------------------------------------------------
// STATE: summary
// AI tahlili natijasi -- InteractionReport (flat dict).
// ------------------------------------------------------------------
function makeSummaryHTML(data) {
    const score = data.support_quality_score ?? '-';
    const addressed = !!data.addressed_issues;
    const discussed = !!data.discussed_flagged_problem;

    return `
        <div class="summary-card">
            <div class="summary-header">
                <span class="summary-title">Tahlil hisoboti (${student.student_name})</span>
                <span class="score-badge">Qo'llab-quvvatlash balli: ${escapeHtml(score)}/10</span>
            </div>
            <div class="summary-body">
                ${escapeHtml(data.summary)}
            </div>
            <div class="recommendation-box">
                <span>Tavsiya:</span> ${escapeHtml(data.recommendations)}
            </div>
            <div class="summary-flags">
                <span class="flag-badge ${addressed ? 'flag-good' : 'flag-bad'}">${addressed ? '✓ Muammo hal qilingan' : '✕ Muammo hal qilinmagan'}</span>
                <span class="flag-badge ${discussed ? 'flag-good' : 'flag-bad'}">${discussed ? '✓ Muammo muhokama qilingan' : '✕ Muammo muhokama qilinmagan'}</span>
            </div>
            <div class="summary-footer">
                <span>Muammo: ${escapeHtml(data.problem || '—')}</span>
                <span>Sana: ${formatDate(data.last_contacted_date)}</span>
            </div>
        </div>
    `;
}

// ------------------------------------------------------------------
// STATE: error
// Pipeline'ning turli bosqichlarida (accounts, chat_history_checking,
// summary, pipeline) yuz bergan xatoliklar.
// ------------------------------------------------------------------
const STAGE_LABELS = {
    accounts: "Progress tahlili",
    chat_history_checking: "Chat tarixini olish",
    summary: "AI tahlili",
    pipeline: "Umumiy pipeline",
};

function makeErrorHTML(data) {
    const stage = data.stage || 'pipeline';
    const stageLabel = STAGE_LABELS[stage] || stage;

    const details = [];
    if (data.group_ids) details.push(`Guruhlar: ${[].concat(data.group_ids).join(', ')}`);
    if (data.student_id !== undefined) details.push(`${data.student_name}`);

    return `
        <div class="status-check-card error-card">
            <span class="dot" style="background: var(--danger-text);"></span>
            <span>
                <b>⚠️ Xatolik (${escapeHtml(stageLabel)}) ${details.join(' • ')}</b>: ${escapeHtml(data.message || 'Noma\'lum xatolik')}
            </span>
        </div>
    `;
}

// ------------------------------------------------------------------
// STATE: done
// Pipeline yakunlandi -- yaratilgan reportlar soni bilan.
// ------------------------------------------------------------------
function makeDoneHTML(data) {
    const total = data?.total_reports ?? 0;
    return `
        <div class="done-card">
            🎉 Barcha jarayonlar muvaffaqiyatli yakunlandi! Jami ${escapeHtml(total)} ta hisobot yaratildi.
        </div>
    `;
}

// ------------------------------------------------------------------
// Asosiy Routing funksiyasi
// ------------------------------------------------------------------
function makeElement(response) {
    const state = response.state;
    const data = response.data || {};
    console.log("MakeElement: ", data);
    

    switch (state) {
        case "accounts":
            return makeAccountsHTML(data);
        case "accounts_batches":
            return makeAccountsBatchesHTML(data);
        case "chat_history_checking":
            return makeChatCheckingHTML(data);
        case "summary":
            return makeSummaryHTML(data);
        case "done":
            return makeDoneHTML(data);
        case "error":
            return makeErrorHTML(data);
        default:
            console.warn("Noma'lum state:", state, response);
            return '';
    }
}
