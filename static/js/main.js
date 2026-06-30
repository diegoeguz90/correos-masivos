// --- STATE MANAGEMENT ---
let recipientsList = [];
let selectedAttachments = [];
let campaignSocket = null;
let pollInterval = null;

// --- DOM ELEMENTS ---
const smtpForm = document.getElementById('smtp-form');
const smtpHost = document.getElementById('smtp-host');
const smtpPort = document.getElementById('smtp-port');
const smtpUsername = document.getElementById('smtp-username');
const smtpPassword = document.getElementById('smtp-password');
const smtpSenderEmail = document.getElementById('smtp-sender-email');
const smtpSenderName = document.getElementById('smtp-sender-name'); // Optional
const previewSubject = document.getElementById('preview-subject');
const previewBody = document.getElementById('preview-body');
const smtpSsl = document.getElementById('smtp-ssl');
const btnTestSmtp = document.getElementById('btn-test-smtp');

const dropzone = document.getElementById('dropzone');
const dropzoneText = document.getElementById('dropzone-text');
const fileInput = document.getElementById('file-input');
const previewSection = document.getElementById('preview-section');
const recipientCount = document.getElementById('recipient-count');
const previewTableBody = document.querySelector('#preview-table tbody');

const emailSubject = document.getElementById('email-subject');
const emailBody = document.getElementById('email-body');
const minDelaySlider = document.getElementById('min-delay-slider');
const minDelayVal = document.getElementById('min-delay-val');
const maxDelaySlider = document.getElementById('max-delay-slider');
const maxDelayVal = document.getElementById('max-delay-val');
const pauseAfter = document.getElementById('pause-after');
const pauseDuration = document.getElementById('pause-duration');
const sendWindowStart = document.getElementById('send-window-start');
const sendWindowEnd = document.getElementById('send-window-end');
const btnStartCampaign = document.getElementById('btn-start-campaign');
const btnStopCampaign = document.getElementById('btn-stop-campaign');
const btnAbortCampaign = document.getElementById('btn-abort-campaign');
const dailyLimit = document.getElementById('daily-limit');

// Attachments DOM
const attachmentsDropzone = document.getElementById('attachments-dropzone');
const attachmentsDropzoneText = document.getElementById('attachments-dropzone-text');
const attachmentsInput = document.getElementById('attachments-input');
const attachmentsList = document.getElementById('attachments-list');

const progressCard = document.getElementById('campaign-progress-card');
const statTotal = document.getElementById('stat-total');
const statSent = document.getElementById('stat-sent');
const statFailed = document.getElementById('stat-failed');
const statToday = document.getElementById('stat-today');
const progressBarFill = document.getElementById('progress-bar-fill');
const campaignPercentage = document.getElementById('campaign-percentage');
const campaignStatusText = document.getElementById('campaign-status-text');
const currentRecipientVal = document.getElementById('current-recipient-val');
const consoleLogs = document.getElementById('console-logs');

const toast = document.getElementById('toast');
const toastMessage = document.getElementById('toast-message');
const toastIcon = document.getElementById('toast-icon');

// --- INITIALIZE & LOAD SAVED SMTP ---
document.addEventListener('DOMContentLoaded', () => {
    loadSmtpSettings();
    checkActiveCampaign();
    
    // Toggle advanced settings section
    const toggleBtn = document.getElementById('toggle-advanced-smtp');
    const advancedSection = document.getElementById('advanced-smtp-section');
    toggleBtn.addEventListener('click', () => {
        if (advancedSection.style.display === 'none') {
            advancedSection.style.display = 'block';
            toggleBtn.innerHTML = '<i class="fa-solid fa-sliders"></i> Ocultar Ajustes Avanzados';
        } else {
            advancedSection.style.display = 'none';
            toggleBtn.innerHTML = '<i class="fa-solid fa-sliders"></i> Mostrar Ajustes Avanzados';
        }
    });

    // Auto-fill and default advanced configurations when typing email
    smtpUsername.addEventListener('input', (e) => {
        const val = e.target.value.trim();
        smtpSenderEmail.value = val; // Sync sender email with login username
        
        if (val.toLowerCase().endsWith('@gmail.com')) {
            smtpHost.value = 'smtp.gmail.com';
            smtpPort.value = 465;
            smtpSsl.checked = true;
        }
    });

    // Live email preview updates
    function updateLivePreview() {
        if (!previewSubject || !previewBody) return;
        
        const subVal = emailSubject.value || '';
        const bodyVal = emailBody.value || '';
        
        // Interpolate placeholder for preview with a green highlighted name
        const dummyName = '<strong style="color: var(--accent-violet);">Juan Pérez</strong>';
        const parsedSubject = subVal.replace(/\{\{NOMBRE\}\}/gi, "Juan Pérez");
        let parsedBody = bodyVal.replace(/\{\{NOMBRE\}\}/gi, dummyName);
        
        previewSubject.textContent = parsedSubject || '(Sin Asunto)';
        
        if (parsedBody.toLowerCase().includes("<html>") || parsedBody.toLowerCase().includes("<div") || parsedBody.toLowerCase().includes("<p") || parsedBody.toLowerCase().includes("<br") || parsedBody.toLowerCase().includes("<a")) {
            previewBody.innerHTML = parsedBody || '(Mensaje Vacío)';
        } else {
            // Replace newlines with <br> to preserve formatting in simulated inbox
            const htmlFormattedBody = parsedBody.replace(/\n/g, '<br>');
            previewBody.innerHTML = htmlFormattedBody || '(Mensaje Vacío)';
        }
    }

    emailSubject.addEventListener('input', updateLivePreview);
    emailBody.addEventListener('input', updateLivePreview);
    
    // Make it globally accessible so other functions can call it
    window.updateLivePreview = updateLivePreview;
    
    // Initial call
    updateLivePreview();

    // Init Attachment triggers
    setupAttachmentsUI();
});

// --- TOAST NOTIFICATIONS ---
function showToast(message, type = 'success') {
    toastMessage.textContent = message;
    toast.className = 'toast show';
    
    if (type === 'error') {
        toast.style.borderColor = 'var(--accent-error)';
        toastIcon.className = 'fa-solid fa-circle-exclamation';
        toastIcon.style.color = 'var(--accent-error)';
    } else {
        toast.style.borderColor = 'var(--accent-cyan)';
        toastIcon.className = 'fa-solid fa-circle-check';
        toastIcon.style.color = 'var(--accent-cyan)';
    }
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, 4000);
}

// --- SMTP SETTINGS MANAGEMENT ---
async function loadSmtpSettings() {
    try {
        const response = await fetch('/api/smtp');
        if (response.ok) {
            const data = await response.json();
            if (data.host) {
                smtpHost.value = data.host;
                smtpPort.value = data.port;
                smtpUsername.value = data.username;
                smtpSenderEmail.value = data.sender_email;
                if (smtpSenderName) smtpSenderName.value = data.sender_name || '';
                smtpSsl.checked = data.use_ssl === 1 || data.use_ssl === true;
                // Leave password blank, user must input it if not editing or we can use placeholder
                smtpPassword.value = '';
                smtpPassword.placeholder = '•••••••• (Contraseña Guardada)';
            }
        }
    } catch (error) {
        console.error('Error al cargar credenciales SMTP:', error);
    }
}

// Get form data helper
function getSmtpFormData() {
    return {
        host: smtpHost.value,
        port: parseInt(smtpPort.value),
        username: smtpUsername.value,
        password: smtpPassword.value || '', // if blank, we will validate backend
        use_ssl: smtpSsl.checked,
        sender_email: smtpSenderEmail.value,
        sender_name: smtpSenderName ? smtpSenderName.value : ''
    };
}

// Test Connection
btnTestSmtp.addEventListener('click', async () => {
    const settings = getSmtpFormData();
    if (!settings.host || !settings.port || !settings.username) {
        showToast('Por favor completa los campos del servidor, puerto y usuario para realizar la prueba.', 'error');
        return;
    }
    
    btnTestSmtp.disabled = true;
    btnTestSmtp.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Probando...';
    
    try {
        const response = await fetch('/api/smtp/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        const data = await response.json();
        if (response.ok) {
            showToast('¡Conexión con el servidor SMTP exitosa!', 'success');
        } else {
            showToast('Fallo de conexión: ' + (data.detail || 'Error desconocido'), 'error');
        }
    } catch (error) {
        showToast('Error de red al intentar conectar.', 'error');
    } finally {
        btnTestSmtp.disabled = false;
        btnTestSmtp.innerHTML = '<i class="fa-solid fa-plug"></i> Probar Conexión';
    }
});

// Save settings on submit
smtpForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const settings = getSmtpFormData();
    
    try {
        const response = await fetch('/api/smtp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        if (response.ok) {
            showToast('Configuración SMTP guardada localmente.', 'success');
            smtpPassword.placeholder = '•••••••• (Contraseña Guardada)';
            smtpPassword.value = '';
        } else {
            showToast('Error al guardar credenciales.', 'error');
        }
    } catch (error) {
        showToast('Error de red al guardar.', 'error');
    }
});

// --- RECIPIENTS FILE UPLOAD ---
dropzone.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFile(e.target.files[0]);
    }
});

dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
});

dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
});

dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
        handleFile(e.dataTransfer.files[0]);
    }
});

async function handleFile(file) {
    dropzoneText.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Cargando ${file.name}...`;
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/api/recipients/parse', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        if (response.ok && data.status === 'success') {
            recipientsList = data.recipients;
            recipientCount.textContent = recipientsList.length;
            
            // Populate Preview Table
            previewTableBody.innerHTML = '';
            recipientsList.forEach(rec => {
                const tr = document.createElement('tr');
                tr.innerHTML = `<td>${rec.nombre}</td><td>${rec.correo}</td>`;
                previewTableBody.appendChild(tr);
            });
            
            dropzoneText.innerHTML = `<i class="fa-solid fa-file-circle-check" style="color: var(--accent-success);"></i> ${file.name}`;
            previewSection.style.display = 'block';
            showToast(`¡Lista cargada! ${recipientsList.length} destinatarios válidos.`, 'success');
        } else {
            dropzoneText.innerHTML = 'Arrastra tu Excel (.xlsx) o CSV aquí';
            showToast('Error al parsear el archivo: ' + (data.detail || 'Formato no soportado o inválido'), 'error');
        }
    } catch (error) {
        dropzoneText.innerHTML = 'Arrastra tu Excel (.xlsx) o CSV aquí';
        showToast('Error de red al cargar el archivo.', 'error');
    }
}

// --- TEMPLATE EDITING HELPERS ---
// Delay Sliders
minDelaySlider.addEventListener('input', (e) => {
    minDelayVal.textContent = e.target.value + 's';
    if (parseInt(minDelaySlider.value) > parseInt(maxDelaySlider.value)) {
        maxDelaySlider.value = minDelaySlider.value;
        maxDelayVal.textContent = minDelaySlider.value + 's';
    }
});

maxDelaySlider.addEventListener('input', (e) => {
    maxDelayVal.textContent = e.target.value + 's';
    if (parseInt(maxDelaySlider.value) < parseInt(minDelaySlider.value)) {
        minDelaySlider.value = maxDelaySlider.value;
        minDelayVal.textContent = maxDelaySlider.value + 's';
    }
});

// Insert Placeholder Helper
function insertPlaceholder() {
    const textToInsert = '{{NOMBRE}}';
    const startPos = emailBody.selectionStart;
    const endPos = emailBody.selectionEnd;
    const textVal = emailBody.value;
    
    emailBody.value = textVal.substring(0, startPos) + textToInsert + textVal.substring(endPos, textVal.length);
    emailBody.focus();
    emailBody.selectionStart = startPos + textToInsert.length;
    emailBody.selectionEnd = startPos + textToInsert.length;
    
    if (window.updateLivePreview) {
        window.updateLivePreview();
    }
}

// Insert Placeholder Subject Helper
function insertPlaceholderSubject() {
    const textToInsert = '{{NOMBRE}}';
    const startPos = emailSubject.selectionStart;
    const endPos = emailSubject.selectionEnd;
    const textVal = emailSubject.value;
    
    emailSubject.value = textVal.substring(0, startPos) + textToInsert + textVal.substring(endPos, textVal.length);
    emailSubject.focus();
    emailSubject.selectionStart = startPos + textToInsert.length;
    emailSubject.selectionEnd = startPos + textToInsert.length;
    
    if (window.updateLivePreview) {
        window.updateLivePreview();
    }
}
window.insertPlaceholderSubject = insertPlaceholderSubject;

// Insert Link Helper
function insertLinkHelper() {
    const url = prompt("Introduce la dirección de tu enlace (URL):", "https://");
    if (url === null || url.trim() === "" || url === "https://") return;

    const label = prompt("Introduce el texto que verá el usuario para hacer clic:", "Haz clic aquí");
    if (label === null || label.trim() === "") return;

    const linkHtml = `<a href="${url.trim()}" target="_blank">${label.trim()}</a>`;
    
    const startPos = emailBody.selectionStart;
    const endPos = emailBody.selectionEnd;
    const textVal = emailBody.value;
    
    emailBody.value = textVal.substring(0, startPos) + linkHtml + textVal.substring(endPos, textVal.length);
    emailBody.focus();
    emailBody.selectionStart = startPos + linkHtml.length;
    emailBody.selectionEnd = startPos + linkHtml.length;
    
    if (window.updateLivePreview) {
        window.updateLivePreview();
    }
}

// --- ATTACHMENTS MANAGEMENT ---
function setupAttachmentsUI() {
    attachmentsDropzone.addEventListener('click', () => attachmentsInput.click());
    
    attachmentsInput.addEventListener('change', (e) => {
        handleAttachmentsSelect(e.target.files);
    });
    
    attachmentsDropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        attachmentsDropzone.classList.add('dragover');
    });
    
    attachmentsDropzone.addEventListener('dragleave', () => {
        attachmentsDropzone.classList.remove('dragover');
    });
    
    attachmentsDropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        attachmentsDropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleAttachmentsSelect(e.dataTransfer.files);
        }
    });
}

function handleAttachmentsSelect(files) {
    const totalCurrentSize = selectedAttachments.reduce((sum, f) => sum + f.size, 0);
    let extraSize = 0;
    
    const newFiles = Array.from(files);
    for (let f of newFiles) {
        extraSize += f.size;
    }
    
    // Check Gmail Limit: 25MB (26214400 bytes)
    if (totalCurrentSize + extraSize > 25 * 1024 * 1024) {
        showToast('El límite máximo total para archivos adjuntos es de 25 MB.', 'error');
        return;
    }
    
    for (let f of newFiles) {
        // Prevent duplicate file names in selection
        if (!selectedAttachments.some(existing => existing.name === f.name)) {
            selectedAttachments.push(f);
        }
    }
    
    renderAttachmentsList();
}

function renderAttachmentsList() {
    attachmentsList.innerHTML = '';
    
    if (selectedAttachments.length === 0) {
        attachmentsDropzoneText.innerHTML = 'Arrastra archivos para adjuntar o haz clic aquí';
        return;
    }
    
    const totalMB = (selectedAttachments.reduce((sum, f) => sum + f.size, 0) / (1024 * 1024)).toFixed(2);
    attachmentsDropzoneText.innerHTML = `<i class="fa-solid fa-circle-check" style="color: var(--accent-success);"></i> ${selectedAttachments.length} archivos adjuntos (${totalMB} MB)`;
    
    selectedAttachments.forEach((file, index) => {
        const item = document.createElement('div');
        item.className = 'attachment-item';
        
        const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
        
        item.innerHTML = `
            <div class="attachment-name">
                <i class="fa-solid fa-file-arrow-up" style="color: var(--accent-violet);"></i>
                <span>${file.name} <small style="color: var(--text-secondary);">(${sizeMB} MB)</small></span>
            </div>
            <span class="attachment-remove" onclick="removeAttachment(${index})">
                <i class="fa-solid fa-circle-xmark"></i>
            </span>
        `;
        attachmentsList.appendChild(item);
    });
}

function removeAttachment(index) {
    selectedAttachments.splice(index, 1);
    renderAttachmentsList();
}

// Make it globally accessible for the onclick remove button
window.removeAttachment = removeAttachment;

// --- CAMPAIGN REAL-TIME UPDATES (WEBSOCKET & SSE FALLBACK) ---
function startRealtimeConnection() {
    if (pollInterval) clearInterval(pollInterval);
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/campaign`;
    
    progressCard.style.display = 'block';
    consoleLogs.innerHTML = '<div class="log-line info">Conectando canal de actualizaciones...</div>';
    
    try {
        campaignSocket = new WebSocket(wsUrl);
        
        campaignSocket.onmessage = (event) => {
            const state = JSON.parse(event.data);
            updateCampaignUI(state);
        };
        
        campaignSocket.onclose = () => {
            console.log('WebSocket cerrado. Cambiando a modo de sondeo alternativo.');
            startFallbackPolling();
        };
        
        campaignSocket.onerror = () => {
            console.log('Error en WebSocket.');
        };
    } catch (e) {
        startFallbackPolling();
    }
}

function startFallbackPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/campaign/status');
            if (response.ok) {
                const state = await response.json();
                updateCampaignUI(state);
            }
        } catch (error) {
            console.error('Error en sondeo de progreso:', error);
        }
    }, 1000);
}

function updateCampaignUI(state) {
    statTotal.textContent = state.total;
    statSent.textContent = state.sent;
    statFailed.textContent = state.failed;
    if (statToday && state.daily_limit !== undefined) {
        statToday.textContent = `${state.sent_today} / ${state.daily_limit}`;
    }
    progressBarFill.style.width = state.progress + '%';
    campaignPercentage.textContent = state.progress + '%';
    
    if (state.is_running || state.sent > 0 || state.failed > 0) {
        progressCard.style.display = 'block';
    }

    if (state.is_running) {
        btnStartCampaign.disabled = true;
        btnStartCampaign.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Campaña en curso...';
        campaignStatusText.textContent = state.status_msg || 'Enviando correos...';
        currentRecipientVal.textContent = state.current_recipient || '-';
        btnStopCampaign.disabled = false;
        if (btnAbortCampaign) btnAbortCampaign.disabled = false;
    } else {
        btnStartCampaign.disabled = false;
        btnStartCampaign.innerHTML = '<i class="fa-solid fa-rocket"></i> Iniciar Envío Masivo';
        campaignStatusText.textContent = state.status_msg || 'Campaña inactiva';
        currentRecipientVal.textContent = '-';
        btnStopCampaign.disabled = true;
        if (btnAbortCampaign) btnAbortCampaign.disabled = true;
        if (pollInterval) clearInterval(pollInterval);
    }
    
    // Process logs in console
    consoleLogs.innerHTML = '';
    state.logs.forEach(log => {
        const div = document.createElement('div');
        div.className = 'log-line';
        if (log.includes('[Éxito]') || log.includes('exitosa')) {
            div.classList.add('success');
        } else if (log.includes('[Error]') || log.includes('fallido') || log.includes('Fallo')) {
            div.classList.add('error');
        } else {
            div.classList.add('info');
        }
        div.textContent = log;
        consoleLogs.appendChild(div);
    });
    
    consoleLogs.scrollTop = consoleLogs.scrollHeight;
}

// Start Campaign Trigger
btnStartCampaign.addEventListener('click', async () => {
    if (recipientsList.length === 0) {
        showToast('Primero debes cargar una lista válida de destinatarios (Excel o CSV).', 'error');
        return;
    }
    if (!emailSubject.value.trim() || !emailBody.value.trim()) {
        showToast('Por favor completa el asunto y el cuerpo del correo.', 'error');
        return;
    }
    
    const settings = getSmtpFormData();
    if (!smtpHost.value || !smtpPort.value || !smtpUsername.value) {
        showToast('Por favor completa y guarda las credenciales SMTP antes de iniciar.', 'error');
        return;
    }
    
    // Construct Form Data to handle attachments
    const formData = new FormData();
    formData.append('subject', emailSubject.value);
    formData.append('body', emailBody.value);
    formData.append('daily_limit', parseInt(dailyLimit.value) || 200);
    formData.append('min_delay_seconds', parseInt(minDelaySlider.value) || 5);
    formData.append('max_delay_seconds', parseInt(maxDelaySlider.value) || 15);
    formData.append('pause_after_emails', parseInt(pauseAfter.value) || 0);
    formData.append('pause_duration_minutes', parseInt(pauseDuration.value) || 0);
    formData.append('send_window_start', sendWindowStart.value || '08:00');
    formData.append('send_window_end', sendWindowEnd.value || '17:00');
    
    const tzOffset = -new Date().getTimezoneOffset();
    formData.append('timezone_offset', tzOffset);
    
    formData.append('recipients', JSON.stringify(recipientsList));
    
    selectedAttachments.forEach(file => {
        formData.append('attachments', file);
    });
    
    try {
        btnStartCampaign.disabled = true;
        btnStartCampaign.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Iniciando...';
        
        const response = await fetch('/api/campaign/start', {
            method: 'POST',
            body: formData // Let browser set the multipart Content-Type header with boundaries
        });
        
        const data = await response.json();
        if (response.ok) {
            showToast('¡Campaña iniciada con éxito!', 'success');
            startRealtimeConnection();
        } else {
            showToast('Error al iniciar: ' + (data.detail || 'Inténtalo de nuevo'), 'error');
            btnStartCampaign.disabled = false;
            btnStartCampaign.innerHTML = '<i class="fa-solid fa-rocket"></i> Iniciar Envío Masivo';
        }
    } catch (e) {
        showToast('Error de red al iniciar la campaña.', 'error');
        btnStartCampaign.disabled = false;
        btnStartCampaign.innerHTML = '<i class="fa-solid fa-rocket"></i> Iniciar Envío Masivo';
    }
});

// Stop Campaign Trigger
btnStopCampaign.addEventListener('click', async () => {
    try {
        const response = await fetch('/api/campaign/stop', { method: 'POST' });
        if (response.ok) {
            showToast('Comando de detención/pausa enviado.', 'info');
        }
    } catch (e) {
        showToast('Error al detener la campaña.', 'error');
    }
});

// Abort Campaign Trigger
if (btnAbortCampaign) {
    btnAbortCampaign.addEventListener('click', async () => {
        if (!confirm('¿Estás seguro de que deseas abortar la campaña? Esto detendrá permanentemente los envíos y eliminará los archivos adjuntos del servidor.')) return;
        try {
            const response = await fetch('/api/campaign/abort', { method: 'POST' });
            if (response.ok) {
                showToast('Campaña abortada y archivos eliminados.', 'info');
            }
        } catch (e) {
            showToast('Error al abortar la campaña.', 'error');
        }
    });
}

// Check status on load in case a campaign is already running
async function checkActiveCampaign() {
    try {
        const response = await fetch('/api/campaign/status');
        if (response.ok) {
            const state = await response.json();
            if (state.is_running) {
                progressCard.style.display = 'block';
                startRealtimeConnection();
            }
        }
    } catch (e) {
        console.error('Error al verificar campaña activa:', e);
    }
}
