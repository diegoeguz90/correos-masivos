import os
import asyncio
import threading
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import smtp_manager

app = FastAPI(title="Antigravity Mail Campaign Manager")

# Create templates & static directory structure if they do not exist
os.makedirs("templates", exist_ok=True)
os.makedirs("static/css", exist_ok=True)
os.makedirs("static/js", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- GLOBAL CAMPAIGN STATE ---
class CampaignState:
    def __init__(self):
        self.is_running = False
        self.total = 0
        self.sent = 0
        self.failed = 0
        self.logs = []
        self.should_stop = False
        self.current_recipient = ""

campaign = CampaignState()

# WebSocket connections list
active_connections = []

async def broadcast_campaign_update():
    state = {
        "is_running": campaign.is_running,
        "total": campaign.total,
        "sent": campaign.sent,
        "failed": campaign.failed,
        "progress": int((campaign.sent + campaign.failed) / campaign.total * 100) if campaign.total > 0 else 0,
        "logs": campaign.logs[-20:],  # last 20 logs
        "current_recipient": campaign.current_recipient
    }
    for connection in active_connections:
        try:
            await connection.send_json(state)
        except Exception:
            pass

# Background Campaign Thread
def run_campaign_thread(smtp_settings: dict, recipients: list, subject_template: str, body_template: str, delay: float):
    global campaign
    campaign.is_running = True
    campaign.total = len(recipients)
    campaign.sent = 0
    campaign.failed = 0
    campaign.logs = []
    campaign.should_stop = False
    
    server = None
    
    def connect_smtp():
        nonlocal server
        if smtp_settings["use_ssl"]:
            server = smtplib.SMTP_SSL(smtp_settings["host"], smtp_settings["port"], timeout=15)
        else:
            server = smtplib.SMTP(smtp_settings["host"], smtp_settings["port"], timeout=15)
            server.starttls()
        server.login(smtp_settings["username"], smtp_settings["password"])

    try:
        campaign.logs.append("Iniciando conexión con el servidor SMTP...")
        connect_smtp()
        campaign.logs.append("Conexión SMTP establecida exitosamente.")
    except Exception as e:
        campaign.logs.append(f"Error al conectar con SMTP: {str(e)}")
        campaign.is_running = False
        return

    for idx, recipient in enumerate(recipients):
        if campaign.should_stop:
            campaign.logs.append("Campaña detenida manualmente por el usuario.")
            break
            
        name = recipient.get("nombre", "")
        email = recipient.get("correo", "")
        campaign.current_recipient = f"{name} <{email}>"
        
        # Interpolate placeholders (case insensitive for Nombre)
        sub = subject_template.replace("{{NOMBRE}}", name).replace("{{Nombre}}", name).replace("{{nombre}}", name)
        body = body_template.replace("{{NOMBRE}}", name).replace("{{Nombre}}", name).replace("{{nombre}}", name)
        
        # Construct Email
        msg = MIMEMultipart()
        msg['From'] = f"{smtp_settings.get('sender_name', '')} <{smtp_settings['sender_email']}>" if smtp_settings.get('sender_name') else smtp_settings['sender_email']
        msg['To'] = email
        msg['Subject'] = sub
        
        # Body can be HTML or Plain text (We'll send HTML if it starts with < or has HTML tags, else plain text)
        if "<html>" in body.lower() or "<div" in body.lower() or "<p" in body.lower() or "<br" in body.lower():
            msg.attach(MIMEText(body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))
            
        # Send Email with retry mechanism
        sent_successfully = False
        for attempt in range(2):
            try:
                if server is None:
                    connect_smtp()
                server.send_message(msg)
                sent_successfully = True
                break
            except Exception as ex:
                campaign.logs.append(f"Intento {attempt+1} fallido para {email}: {str(ex)}")
                # Force reconnect on next attempt
                try:
                    server.close()
                except:
                    pass
                server = None
                time.sleep(2)
                
        if sent_successfully:
            campaign.sent += 1
            campaign.logs.append(f"✅ [Éxito] Correo enviado a {email}")
        else:
            campaign.failed += 1
            campaign.logs.append(f"❌ [Error] No se pudo enviar a {email}")
            
        # Delay
        if idx < len(recipients) - 1:
            time.sleep(delay)
            
    # Cleanup
    if server:
        try:
            server.quit()
        except:
            pass
            
    campaign.logs.append(f"Campaña finalizada. Éxitos: {campaign.sent}, Errores: {campaign.failed}")
    campaign.is_running = False
    campaign.current_recipient = ""

# --- REST ENDPOINTS ---

@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/api/smtp")
async def api_get_smtp():
    settings = smtp_manager.get_smtp_settings()
    if settings:
        # Clear password for security
        settings["password"] = ""
        return settings
    return {}

class SmtpSettingsSchema(BaseModel):
    host: str
    port: int
    username: str
    password: str
    use_ssl: bool
    sender_email: str
    sender_name: str = ""

@app.post("/api/smtp")
async def api_save_smtp(settings: SmtpSettingsSchema):
    smtp_manager.save_smtp_settings(settings.dict())
    return {"status": "success", "message": "Configuración SMTP guardada exitosamente."}

@app.post("/api/smtp/test")
async def api_test_smtp(settings: SmtpSettingsSchema):
    success, msg = smtp_manager.test_smtp_connection(settings.dict())
    if success:
        return {"status": "success", "message": msg}
    else:
        raise HTTPException(status_code=400, detail=msg)

@app.post("/api/recipients/parse")
async def api_parse_recipients(file: UploadFile = File(...)):
    content = await file.read()
    recipients = smtp_manager.parse_recipients_file(content, file.filename)
    return {"status": "success", "count": len(recipients), "recipients": recipients[:100]} # Limit preview to first 100

class CampaignStartSchema(BaseModel):
    subject: str
    body: str
    delay: float
    recipients: list

@app.post("/api/campaign/start")
async def api_start_campaign(data: CampaignStartSchema):
    global campaign
    if campaign.is_running:
        raise HTTPException(status_code=400, detail="Ya hay una campaña ejecutándose actualmente.")
        
    settings = smtp_manager.get_smtp_settings()
    if not settings:
        raise HTTPException(status_code=400, detail="Por favor configura y guarda las credenciales SMTP primero.")
        
    if not data.recipients:
        raise HTTPException(status_code=400, detail="La lista de destinatarios está vacía.")
        
    # Start campaign in a separate background thread
    thread = threading.Thread(
        target=run_campaign_thread,
        args=(settings, data.recipients, data.subject, data.body, data.delay)
    )
    thread.daemon = True
    thread.start()
    
    return {"status": "success", "message": "Campaña iniciada con éxito."}

@app.post("/api/campaign/stop")
async def api_stop_campaign():
    global campaign
    if not campaign.is_running:
        return {"status": "success", "message": "No hay ninguna campaña activa."}
    campaign.should_stop = True
    return {"status": "success", "message": "Deteniendo campaña..."}

@app.get("/api/campaign/status")
async def api_campaign_status():
    return {
        "is_running": campaign.is_running,
        "total": campaign.total,
        "sent": campaign.sent,
        "failed": campaign.failed,
        "progress": int((campaign.sent + campaign.failed) / campaign.total * 100) if campaign.total > 0 else 0,
        "logs": campaign.logs[-40:],  # last 40 logs
        "current_recipient": campaign.current_recipient
    }

# --- WEBSOCKET FOR REALTIME CAMPAIGN PROGRESS ---
@app.websocket("/ws/campaign")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        # Send initial status
        state = {
            "is_running": campaign.is_running,
            "total": campaign.total,
            "sent": campaign.sent,
            "failed": campaign.failed,
            "progress": int((campaign.sent + campaign.failed) / campaign.total * 100) if campaign.total > 0 else 0,
            "logs": campaign.logs[-40:],
            "current_recipient": campaign.current_recipient
        }
        await websocket.send_json(state)
        
        while True:
            # Periodically broadcast state if running
            if campaign.is_running:
                state = {
                    "is_running": campaign.is_running,
                    "total": campaign.total,
                    "sent": campaign.sent,
                    "failed": campaign.failed,
                    "progress": int((campaign.sent + campaign.failed) / campaign.total * 100) if campaign.total > 0 else 0,
                    "logs": campaign.logs[-40:],
                    "current_recipient": campaign.current_recipient
                }
                await websocket.send_json(state)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        active_connections.remove(websocket)
    except Exception:
        if websocket in active_connections:
            active_connections.remove(websocket)
