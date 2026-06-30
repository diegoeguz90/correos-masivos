import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import smtp_manager

def process_campaigns():
    """
    Función principal que revisa la DB y envía correos según los límites y retardos.
    Esta función está diseñada para ser ejecutada periódicamente (ej. cada 10 segundos).
    """
    active_campaigns = smtp_manager.get_active_campaigns()
    if not active_campaigns:
        return

    smtp_settings = smtp_manager.get_smtp_settings()
    if not smtp_settings:
        return

    for campaign in active_campaigns:
        campaign_id = campaign["id"]
        daily_limit = campaign["daily_limit"]
        min_delay = campaign["min_delay_seconds"]
        max_delay = campaign["max_delay_seconds"]
        pause_after = campaign["pause_after_emails"]
        pause_duration = campaign["pause_duration_minutes"]
        send_window_start = campaign.get("send_window_start", "08:00")
        send_window_end = campaign.get("send_window_end", "17:00")
        timezone_offset = campaign.get("timezone_offset", 0)
        subject_template = campaign["subject"]
        body_template = campaign["body"]

        # Check sending window (based on campaign timezone offset)
        if send_window_start and send_window_end:
            from datetime import timezone, timedelta
            tz = timezone(timedelta(minutes=timezone_offset))
            current_time = datetime.now(tz).strftime("%H:%M")
            if not (send_window_start <= current_time <= send_window_end):
                continue

        # Check pending recipients
        pending = smtp_manager.get_pending_recipients(campaign_id, limit=1)
        if not pending:
            # If no pending recipients left, mark campaign as completed
            smtp_manager.update_campaign_status(campaign_id, "completed")
            # Clean up attachments
            smtp_manager.delete_attachments_from_disk_and_db(campaign_id)
            continue
            
        recipient = pending[0]

        # Check daily limit
        sent_today = smtp_manager.get_sent_today_count(campaign_id)
        if sent_today >= daily_limit:
            # Daily limit reached, skip this campaign for now
            continue

        # Check long pause & delay
        last_sent = smtp_manager.get_last_sent_time(campaign_id)
        if last_sent:
            now = datetime.utcnow()
            elapsed_seconds = (now - last_sent).total_seconds()
            
            # 1. Check long pause
            stats = smtp_manager.get_campaign_stats(campaign_id)
            sent_count = stats["sent"]
            if pause_after > 0 and sent_count > 0 and (sent_count % pause_after == 0):
                if elapsed_seconds < (pause_duration * 60):
                    # We are in long pause
                    continue
            
            # 2. Check regular random delay
            import random
            random_delay = random.randint(min_delay, max_delay)
            if elapsed_seconds < random_delay:
                # Not enough time has passed
                continue

        # Ready to send!
        email = recipient["email"]
        name = recipient["name"] or ""

        # Interpolate
        sub = subject_template.replace("{{NOMBRE}}", name).replace("{{Nombre}}", name).replace("{{nombre}}", name)
        body = body_template.replace("{{NOMBRE}}", name).replace("{{Nombre}}", name).replace("{{nombre}}", name)

        # Construct Email
        msg = MIMEMultipart()
        msg['From'] = f"{smtp_settings.get('sender_name', '')} <{smtp_settings['sender_email']}>" if smtp_settings.get('sender_name') else smtp_settings['sender_email']
        msg['To'] = email
        msg['Subject'] = sub

        if any(tag in body.lower() for tag in ["<html>", "<div", "<p", "<br", "<a", "href="]):
            html_body = body
            # If it's simple text containing links/HTML but not a full HTML page, convert newlines to <br>
            if not ("<html>" in body.lower() or "<body>" in body.lower()):
                html_body = body.replace("\n", "<br>")
            msg.attach(MIMEText(html_body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))

        # Add attachments
        import os
        from email.mime.application import MIMEApplication
        attachments = smtp_manager.get_attachments(campaign_id)
        for att in attachments:
            file_path = att["file_path"]
            if os.path.exists(file_path):
                try:
                    with open(file_path, "rb") as f:
                        part = MIMEApplication(f.read(), Name=att["file_name"])
                        part['Content-Disposition'] = f'attachment; filename="{att["file_name"]}"'
                        msg.attach(part)
                except Exception as e:
                    # Log error loading attachment, but continue sending email
                    pass

        # Send
        try:
            if smtp_settings["use_ssl"]:
                server = smtplib.SMTP_SSL(smtp_settings["host"], smtp_settings["port"], timeout=15)
            else:
                server = smtplib.SMTP(smtp_settings["host"], smtp_settings["port"], timeout=15)
                server.starttls()
            server.login(smtp_settings["username"], smtp_settings["password"])
            server.send_message(msg)
            server.quit()
            
            # Mark as sent
            smtp_manager.update_recipient_status(recipient["id"], "sent")
            
        except Exception as e:
            # Mark as failed
            smtp_manager.update_recipient_status(recipient["id"], "failed", str(e))

def start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler
    import logging
    
    # Mute apscheduler logs unless error to avoid spamming the console
    logging.getLogger('apscheduler').setLevel(logging.WARNING)

    scheduler = BackgroundScheduler()
    # Run every 5 seconds to be responsive, but it will respect the delay_seconds internally
    scheduler.add_job(process_campaigns, 'interval', seconds=5, max_instances=1)
    scheduler.start()
    return scheduler
