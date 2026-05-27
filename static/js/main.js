// --- STATE MANAGEMENT ---
let recipientsList = [];
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
const delaySlider = document.getElementById('delay-slider');
const delayVal = document.getElementById('delay-val');
const btnStartCampaign = document.getElementById('btn-start-campaign');
const btnStopCampaign = document.getElementById('btn-stop-campaign');

const progressCard = document.getElementById('campaign-progress-card');
const statTotal = document.getElementById('stat-total');
const statSent = document.getElementById('stat-sent');
const statFailed = document.getElementById('stat-failed');
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
    // Live email preview updates
    function updateLivePreview() {
        if (!previewSubject || !previewBody) return;
        
        const subVal = emailSubject.value || '';
        const bodyVal = emailBody.value || '';
        
        // Interpolate placeholder for preview with a green highlighted name
        const dummyName = '<strong style="color: var(--accent-success);">Juan Pérez</strong>';
        const parsedSubject = subVal.replace(/\{\{NOMBRE\}\}/gi, "Juan Pérez");
        let parsedBody = bodyVal.replace(/\{\{NOMBRE\}\}/gi, dummyName);
        
        previewSubject.textContent = parsedSubject || '(Sin Asunto)';
        
        if (parsedBody.toLowerCase().includes("<html>") || parsedBody.toLowerCase().includes("<div") || parsedBody.toLowerCase().includes("<p") || parsedBody.toLowerCase().includes("<br")) {
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
// Drag and Drop Effects
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
// Delay Slider
delaySlider.addEventListener('input', (e) => {
    delayVal.textContent = e.target.value + 's';
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
    
    // Update live preview dynamically
    if (window.updateLivePreview) {
        window.updateLivePreview();
    }
}

// --- CAMPAIGN REAL-TIME UPDATES (WEBSOCKET & SSE FALLBACK) ---
function startRealtimeConnection() {
    // Clear old polling intervals if any
    if (pollInterval) clearInterval(pollInterval);
    
    // Construct websocket URL
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
    progressBarFill.style.width = state.progress + '%';
    campaignPercentage.textContent = state.progress + '%';
    
    if (state.is_running) {
        btnStartCampaign.disabled = true;
        btnStartCampaign.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Campaña en curso...';
        campaignStatusText.textContent = 'Enviando correos...';
        currentRecipientVal.textContent = state.current_recipient || '-';
    } else {
        btnStartCampaign.disabled = false;
        btnStartCampaign.innerHTML = '<i class="fa-solid fa-rocket"></i> Iniciar Envío Masivo';
        campaignStatusText.textContent = 'Campaña completada o inactiva';
        currentRecipientVal.textContent = '-';
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
    
    // Auto scroll down console
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
    
    const campaignData = {
        subject: emailSubject.value,
        body: emailBody.value,
        delay: parseFloat(delaySlider.value),
        recipients: recipientsList
    };
    
    try {
        btnStartCampaign.disabled = true;
        btnStartCampaign.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Iniciando...';
        
        const response = await fetch('/api/campaign/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(campaignData)
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
            showToast('Comando de detención enviado.', 'info');
        }
    } catch (e) {
        showToast('Error al detener la campaña.', 'error');
    }
});

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
