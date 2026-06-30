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
    conn.commit()
    conn.close()

def save_smtp_settings(settings: dict):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Delete existing settings (only keep the latest one)
    cursor.execute("DELETE FROM smtp_settings")
    cursor.execute("""
        INSERT INTO smtp_settings (host, port, username, password, use_ssl, sender_email, sender_name)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        settings["host"],
        int(settings["port"]),
        settings["username"],
        settings["password"],
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

# Initialize database on import
init_db()
