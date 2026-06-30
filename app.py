import os
import asyncio
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import smtp_manager
import scheduler

app = FastAPI(title="Antigravity Mail Campaign Manager")

# Create templates & static directory structure if they do not exist
os.makedirs("templates", exist_ok=True)
os.makedirs("static/css", exist_ok=True)
os.makedirs("static/js", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Store the scheduler instance
app_scheduler = None

@app.on_event("startup")
async def startup_event():
    global app_scheduler
    app_scheduler = scheduler.start_scheduler()

@app.on_event("shutdown")
async def shutdown_event():
    global app_scheduler
    if app_scheduler:
        app_scheduler.shutdown()

# WebSocket connections list
active_connections = []

def get_current_campaign_state():
    latest = smtp_manager.get_latest_campaign()
    if not latest:
        return {
            "is_running": False,
            "total": 0, "sent": 0, "failed": 0, "progress": 0,
            "logs": [], "current_recipient": ""
        }
        
    campaign_id = latest["id"]
    stats = smtp_manager.get_campaign_stats(campaign_id)
    total = stats["total"]
    sent = stats["sent"]
    failed = stats["failed"]
    
    logs = smtp_manager.get_recent_logs(campaign_id, limit=40)
    
    # Get current recipient being processed (the one pending or the last sent)
    pending = smtp_manager.get_pending_recipients(campaign_id, limit=1)
    current_recipient = ""
    if latest["status"] == "active" and pending:
        current_recipient = f"{pending[0]['name']} <{pending[0]['email']}>"
        
    is_running = latest["status"] == "active"
    
    status_msg = "Pausada"
    if is_running:
        from datetime import datetime
        now_str = datetime.now().strftime("%H:%M")
        start_w = latest.get("send_window_start", "08:00")
        end_w = latest.get("send_window_end", "17:00")
        if not (start_w <= now_str <= end_w):
            status_msg = f"Fuera de horario (Espera a las {start_w})"
        else:
            status_msg = "Enviando..."
    elif total == sent + failed:
        status_msg = "Completada"
    
    return {
        "is_running": is_running,
        "total": total,
        "sent": sent,
        "failed": failed,
        "progress": int((sent + failed) / total * 100) if total > 0 else 0,
        "logs": logs,
        "current_recipient": current_recipient,
        "status_msg": status_msg,
        "sent_today": smtp_manager.get_sent_today_count(campaign_id),
        "daily_limit": latest["daily_limit"]
    }

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

from typing import List
import json

@app.post("/api/campaign/start")
async def api_start_campaign(
    subject: str = Form(...),
    body: str = Form(...),
    daily_limit: int = Form(...),
    min_delay_seconds: int = Form(...),
    max_delay_seconds: int = Form(...),
    pause_after_emails: int = Form(...),
    pause_duration_minutes: int = Form(...),
    send_window_start: str = Form("08:00"),
    send_window_end: str = Form("17:00"),
    timezone_offset: int = Form(0),
    recipients: str = Form(...),
    attachments: List[UploadFile] = File(default=[])
):
    # Check if there is already an active campaign
    active = smtp_manager.get_active_campaigns()
    if active:
        raise HTTPException(status_code=400, detail="Ya hay una campaña ejecutándose actualmente.")
        
    settings = smtp_manager.get_smtp_settings()
    if not settings:
        raise HTTPException(status_code=400, detail="Por favor configura y guarda las credenciales SMTP primero.")
        
    try:
        recipients_list = json.loads(recipients)
    except Exception:
        raise HTTPException(status_code=400, detail="El formato de los destinatarios es inválido.")
        
    if not recipients_list:
        raise HTTPException(status_code=400, detail="La lista de destinatarios está vacía.")
        
    # Check total size
    total_size = 0
    valid_attachments = [a for a in attachments if a.filename]
    
    for attachment in valid_attachments:
        content = await attachment.read()
        total_size += len(content)
        await attachment.seek(0)
        
    if total_size > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El tamaño total de los archivos adjuntos supera los 25 MB.")
        
    # Create campaign and recipients in DB
    campaign_id = smtp_manager.create_campaign(
        subject=subject,
        body=body,
        daily_limit=daily_limit,
        min_delay=min_delay_seconds,
        max_delay=max_delay_seconds,
        pause_after=pause_after_emails,
        pause_duration=pause_duration_minutes,
        send_window_start=send_window_start,
        send_window_end=send_window_end,
        timezone_offset=timezone_offset,
        recipients_list=recipients_list
    )
    
    # Save attachments physically and in DB
    if valid_attachments:
        attach_dir = f"/app/data/attachments/{campaign_id}"
        os.makedirs(attach_dir, exist_ok=True)
        for attachment in valid_attachments:
            file_path = os.path.join(attach_dir, attachment.filename)
            content = await attachment.read()
            with open(file_path, "wb") as f:
                f.write(content)
            smtp_manager.save_attachment(campaign_id, attachment.filename, file_path)
    
    return {"status": "success", "message": "Campaña guardada e iniciada con éxito."}

@app.post("/api/campaign/stop")
async def api_stop_campaign():
    latest = smtp_manager.get_latest_campaign()
    if latest and latest["status"] == "active":
        smtp_manager.update_campaign_status(latest["id"], "paused")
        return {"status": "success", "message": "Campaña pausada."}
    return {"status": "success", "message": "No hay ninguna campaña activa."}

@app.post("/api/campaign/abort")
async def api_abort_campaign():
    latest = smtp_manager.get_latest_campaign()
    if latest and latest["status"] == "active":
        smtp_manager.update_campaign_status(latest["id"], "aborted")
        smtp_manager.delete_attachments_from_disk_and_db(latest["id"])
        return {"status": "success", "message": "Campaña abortada."}
    return {"status": "success", "message": "No hay ninguna campaña activa."}

@app.get("/api/campaign/status")
async def api_campaign_status():
    return get_current_campaign_state()

# --- WEBSOCKET FOR REALTIME CAMPAIGN PROGRESS ---
@app.websocket("/ws/campaign")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            state = get_current_campaign_state()
            await websocket.send_json(state)
            await asyncio.sleep(1.0) # Poll every 1 second
    except WebSocketDisconnect:
        active_connections.remove(websocket)
    except Exception:
        if websocket in active_connections:
            active_connections.remove(websocket)
