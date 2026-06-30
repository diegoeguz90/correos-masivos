import os
import sqlite3
import smtplib
import time
import csv
import io
import mimetypes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import openpyxl

# --- DATABASE SETUP ---
DB_PATH = "/app/data/antigravity_mail.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS smtp_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            use_ssl INTEGER DEFAULT 1,
            sender_email TEXT NOT NULL,
            sender_name TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            daily_limit INTEGER NOT NULL DEFAULT 200,
            min_delay_seconds INTEGER NOT NULL DEFAULT 5,
            max_delay_seconds INTEGER NOT NULL DEFAULT 15,
            pause_after_emails INTEGER NOT NULL DEFAULT 0,
            pause_duration_minutes INTEGER NOT NULL DEFAULT 0,
            send_window_start TEXT DEFAULT '08:00',
            send_window_end TEXT DEFAULT '17:00',
            timezone_offset INTEGER DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Run migrations for existing DBs
    try:
        cursor.execute("ALTER TABLE campaigns ADD COLUMN min_delay_seconds INTEGER DEFAULT 5")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE campaigns ADD COLUMN max_delay_seconds INTEGER DEFAULT 15")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE campaigns ADD COLUMN pause_after_emails INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE campaigns ADD COLUMN pause_duration_minutes INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE campaigns ADD COLUMN send_window_start TEXT DEFAULT '08:00'")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE campaigns ADD COLUMN send_window_end TEXT DEFAULT '17:00'")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE campaigns ADD COLUMN timezone_offset INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            name TEXT,
            email TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            sent_at DATETIME,
            error_msg TEXT,
            FOREIGN KEY (campaign_id) REFERENCES campaigns (id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            FOREIGN KEY (campaign_id) REFERENCES campaigns (id)
        )
    """)
    conn.commit()
    conn.close()

def save_smtp_settings(settings: dict):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    password = settings["password"]
    if not password:
        existing = get_smtp_settings()
        if existing:
            password = existing["password"]
            
    # Delete existing settings (only keep the latest one)
    cursor.execute("DELETE FROM smtp_settings")
    cursor.execute("""
        INSERT INTO smtp_settings (host, port, username, password, use_ssl, sender_email, sender_name)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        settings["host"],
        int(settings["port"]),
        settings["username"],
        password,
        1 if settings.get("use_ssl", True) else 0,
        settings["sender_email"],
        settings.get("sender_name", "")
    ))
    conn.commit()
    conn.close()

def get_smtp_settings():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM smtp_settings ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def test_smtp_connection(settings: dict):
    """Prueba si las credenciales de conexión son válidas."""
    host = settings["host"]
    port = int(settings["port"])
    username = settings["username"]
    password = settings["password"]
    use_ssl = settings.get("use_ssl", True)

    if not password:
        existing = get_smtp_settings()
        if existing:
            password = existing["password"]

    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=10)
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            server.starttls()
        
        server.login(username, password)
        server.quit()
        return True, "Conexión exitosa"
    except Exception as e:
        return False, str(e)

# --- RECIPIENTS PARSER ---
def parse_recipients_file(file_content: bytes, filename: str):
    """Parsea el archivo subido (Excel o CSV) y devuelve una lista de destinatarios con nombre y correo."""
    recipients = []
    
    if filename.endswith('.csv'):
        # Decode bytes to text
        try:
            text = file_content.decode('utf-8')
        except UnicodeDecodeError:
            text = file_content.decode('latin-1')
        
        # Detect delimiter
        dialect = ';'
        if ',' in text.split('\n')[0]:
            dialect = ','
        
        reader = csv.reader(io.StringIO(text), delimiter=dialect)
        header = [h.strip().lower() for h in next(reader, [])]
        
        # Find column indexes
        email_idx = -1
        name_idx = -1
        
        for i, h in enumerate(header):
            if 'correo' in h or 'email' in h or 'mail' in h:
                email_idx = i
            elif 'nombre' in h or 'name' in h:
                name_idx = i
        
        # Fallback if no matching header
        if email_idx == -1 and len(header) > 0:
            email_idx = 0
        if name_idx == -1 and len(header) > 1:
            name_idx = 1
            
        for row in reader:
            if not row or len(row) <= max(email_idx, name_idx):
                continue
            email = row[email_idx].strip()
            name = row[name_idx].strip() if name_idx != -1 else ""
            if email and '@' in email:
                recipients.append({"nombre": name, "correo": email})
                
    elif filename.endswith('.xlsx'):
        # Parse Excel using openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True)
        sheet = wb.active
        
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []
            
        header = [str(cell).strip().lower() if cell is not None else "" for cell in rows[0]]
        
        email_idx = -1
        name_idx = -1
        
        for i, h in enumerate(header):
            if 'correo' in h or 'email' in h or 'mail' in h:
                email_idx = i
            elif 'nombre' in h or 'name' in h:
                name_idx = i
                
        # Fallbacks
        if email_idx == -1 and len(header) > 0:
            email_idx = 0
        if name_idx == -1 and len(header) > 1:
            name_idx = 1
            
        for row in rows[1:]:
            if len(row) <= max(email_idx, name_idx):
                continue
            email = str(row[email_idx]).strip() if row[email_idx] is not None else ""
            name = str(row[name_idx]).strip() if name_idx != -1 and row[name_idx] is not None else ""
            if email and '@' in email:
                recipients.append({"nombre": name, "correo": email})
                
    return recipients

# --- CAMPAIGN CRUD ---
def create_campaign(subject: str, body: str, daily_limit: int, min_delay: int, max_delay: int, pause_after: int, pause_duration: int, send_window_start: str, send_window_end: str, timezone_offset: int, recipients_list: list):
    """Crea una campaña y guarda todos los destinatarios como pendientes."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Insert campaign
    cursor.execute("""
        INSERT INTO campaigns (subject, body, daily_limit, min_delay_seconds, max_delay_seconds, pause_after_emails, pause_duration_minutes, send_window_start, send_window_end, timezone_offset, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
    """, (subject, body, daily_limit, min_delay, max_delay, pause_after, pause_duration, send_window_start, send_window_end, timezone_offset))
    campaign_id = cursor.lastrowid
    
    # 2. Insert recipients
    for r in recipients_list:
        cursor.execute("""
            INSERT INTO recipients (campaign_id, name, email, status)
            VALUES (?, ?, ?, 'pending')
        """, (campaign_id, r.get("nombre", ""), r.get("correo", "")))
        
    conn.commit()
    conn.close()
    return campaign_id

def get_active_campaigns():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM campaigns WHERE status = 'active'")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_campaign_stats(campaign_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM recipients WHERE campaign_id = ?", (campaign_id,))
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM recipients WHERE campaign_id = ? AND status = 'sent'", (campaign_id,))
    sent = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM recipients WHERE campaign_id = ? AND status = 'failed'", (campaign_id,))
    failed = cursor.fetchone()[0]
    
    conn.close()
    return {"total": total, "sent": sent, "failed": failed}

def get_pending_recipients(campaign_id: int, limit: int = None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT * FROM recipients WHERE campaign_id = ? AND status = 'pending' ORDER BY id ASC"
    params = [campaign_id]
    
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
        
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_recipient_status(recipient_id: int, status: str, error_msg: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if error_msg:
        cursor.execute("""
            UPDATE recipients SET status = ?, error_msg = ?, sent_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, error_msg, recipient_id))
    else:
        cursor.execute("""
            UPDATE recipients SET status = ?, sent_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, recipient_id))
    conn.commit()
    conn.close()

def get_sent_today_count(campaign_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT timezone_offset FROM campaigns WHERE id = ?", (campaign_id,))
    row = cursor.fetchone()
    tz_offset = row[0] if row else 0
    
    # SQLite offset formatting (e.g. '-300 minutes')
    offset_str = f"{tz_offset} minutes"
    
    cursor.execute("""
        SELECT COUNT(*) FROM recipients 
        WHERE campaign_id = ? 
          AND status = 'sent' 
          AND date(sent_at, ?) = date('now', ?)
    """, (campaign_id, offset_str, offset_str))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def update_campaign_status(campaign_id: int, status: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE campaigns SET status = ? WHERE id = ?", (status, campaign_id))
    conn.commit()
    conn.close()

def get_recent_logs(campaign_id: int, limit: int = 40):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT status, email, error_msg FROM recipients 
        WHERE campaign_id = ? AND status != 'pending' 
        ORDER BY sent_at DESC LIMIT ?
    """, (campaign_id, limit))
    rows = cursor.fetchall()
    conn.close()
    
    logs = []
    for row in reversed(rows): # Older first
        if row['status'] == 'sent':
            logs.append(f"✅ [Éxito] Correo enviado a {row['email']}")
        else:
            logs.append(f"❌ [Error] No se pudo enviar a {row['email']}: {row['error_msg']}")
    return logs

def get_latest_campaign():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM campaigns ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_last_sent_time(campaign_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT sent_at FROM recipients 
        WHERE campaign_id = ? AND sent_at IS NOT NULL
        ORDER BY sent_at DESC LIMIT 1
    """, (campaign_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        from datetime import datetime
        # SQLite returns string like '2023-10-25 12:00:00'
        try:
            return datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    return None

def save_attachment(campaign_id: int, file_name: str, file_path: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO attachments (campaign_id, file_name, file_path)
        VALUES (?, ?, ?)
    """, (campaign_id, file_name, file_path))
    conn.commit()
    conn.close()

def get_attachments(campaign_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM attachments WHERE campaign_id = ?", (campaign_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_attachments_from_disk_and_db(campaign_id: int):
    import shutil
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Delete from DB
    cursor.execute("DELETE FROM attachments WHERE campaign_id = ?", (campaign_id,))
    
    # Delete physically
    campaign_dir = f"/app/data/attachments/{campaign_id}"
    if os.path.exists(campaign_dir):
        try:
            shutil.rmtree(campaign_dir)
        except Exception:
            pass
            
    conn.commit()
    conn.close()

# Initialize database on import
init_db()
