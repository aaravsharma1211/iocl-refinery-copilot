from core.analytics_engine import AnalyticsEngine
from agents.supervisor import SupervisorAgent
from core.report_engine import ReportEngine
import smtplib
from email.message import EmailMessage


def send_enterprise_alert(recipient_email, subject, alert_body):
  """Sends a real operational or safety alert via Gmail SMTP."""
  SMTP_SERVER = "smtp.gmail.com"
  SMTP_PORT = 587
  SENDER_EMAIL = os.getenv("ALERT_EMAIL")
  SENDER_PASSWORD = os.getenv("ALERT_EMAIL_PASSWORD")

  if not SENDER_EMAIL or not SENDER_PASSWORD:
    st.error("Email alert credentials are not configured.")
    return False

  msg = EmailMessage()
  msg.set_content(alert_body)
  msg["Subject"] = f"[IOCL COPILOT ALERT] {subject}"
  msg["From"] = SENDER_EMAIL
  msg["To"] = recipient_email

  try:
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
      server.starttls()
      server.login(SENDER_EMAIL, SENDER_PASSWORD)
      server.send_message(msg)
    return True
  except Exception as e:
    st.error(f"Failed to dispatch alert: {e}")
    return False
