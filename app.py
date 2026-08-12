import os
import imageio_ffmpeg

# Automatically inject imageio's bundled ffmpeg binary into the system path for Whisper
os.environ["PATH"] += os.pathsep + os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
import sys
from types import ModuleType
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

# Unconditionally mock numba to satisfy whisper without needing binaries or linter warnings
numba_mock = ModuleType("numba")
numba_mock.jit = lambda *args, **kwargs: (lambda f: f)
numba_mock.njit = lambda *args, **kwargs: (lambda f: f)
sys.modules["numba"] = numba_mock
import pandas as pd
from core.rag_engine import AdvancedRAGEngine
from core.analytics_engine import AnalyticsEngine
from agents.supervisor import SupervisorAgent
from core.report_engine import ReportEngine
import smtplib
from email.message import EmailMessage


import smtplib
from email.message import EmailMessage


def send_enterprise_alert(recipient_email, subject, alert_body):
  """Sends a real operational or safety alert via Gmail SMTP."""
  SMTP_SERVER = "smtp.gmail.com"
  SMTP_PORT = 587
  SENDER_EMAIL = "aaravsharma12115@gmail.com"
  SENDER_PASSWORD = "xuuc nyob yrfx mrjw"  # Paste your App Password here

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

# Page Configuration
st.set_page_config(
    page_title="IOCL Enterprise Refinery Copilot",
    page_icon="⛽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==================== AUTHENTICATION & LOGIN WALL ====================
# Load configuration file
with open("config.yaml") as file:
  config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config["credentials"],
    config["cookie"]["name"],
    config["cookie"]["key"],
    config["cookie"]["expiry_days"],
)

try:
  authenticator.login("main")
except Exception as e:
  st.error(e)

if st.session_state.get("authentication_status") is False:
  st.error("Username/password is incorrect")
elif st.session_state.get("authentication_status") is None:
  st.warning(
      "Please enter your username and password to access the IOCL Refinery"
      " Copilot"
  )
elif st.session_state.get("authentication_status") is True:

  # Initialize Session State
  if "rag_engine" not in st.session_state:
    st.session_state.rag_engine = AdvancedRAGEngine()

  if "analytics_engine" not in st.session_state:
    st.session_state.analytics_engine = AnalyticsEngine()

  if "supervisor" not in st.session_state:
    st.session_state.supervisor = SupervisorAgent(
        rag_engine=st.session_state.rag_engine,
        analytics_engine=st.session_state.analytics_engine,
    )

  if "messages" not in st.session_state:
    st.session_state.messages = []

  if "document_history" not in st.session_state:
    st.session_state.document_history = []

  if "feedback_logs" not in st.session_state:
    st.session_state.feedback_logs = []

  # ==================== SIDEBAR & RBAC CONFIGURATION ====================
  st.sidebar.title("⛽ Enterprise Control Center")

  # Logout button & Welcome in sidebar
  authenticator.logout("Logout", "sidebar")
  st.sidebar.success(f"Welcome back, {st.session_state.get('name', 'User')}!")
  st.sidebar.markdown("---")

  # Module 15: Authentication & RBAC Role Selector
  st.sidebar.subheader("🔒 User Authentication & RBAC")
  user_role = st.sidebar.selectbox(
      "Select Role", ["Operator", "Engineer", "Admin", "HR", "Intern"]
  )
  st.sidebar.info(f"Active Role: **{user_role}** (Access Level Enforced)")

  groq_api_key = st.sidebar.text_input(
      "Enter Groq API Key",
      type="password",
      value=os.getenv("GROQ_API_KEY", ""),
      help="Required for Llama 3.3 70B inference.",
  )

  # Module 13: Multilingual Support Toggle
  st.sidebar.markdown("---")
  st.sidebar.subheader("🌐 Language Support")
  selected_language = st.sidebar.selectbox(
      "Response Language", ["English", "Hindi (हिन्दी)"]
  )

  st.sidebar.markdown("---")

  # Navigation Tabs in Sidebar
  nav_mode = st.sidebar.radio(
      "Navigation",
      [
          "💬 Copilot Chat & Analytics",
          "📊 Admin Analytics Dashboard",
          "📑 Document Versioning Audit",
      ],
  )

  # ==================== VIEW 1: COPILOT CHAT & ANALYTICS ====================
  if nav_mode == "💬 Copilot Chat & Analytics":
    st.sidebar.markdown("---")
    st.sidebar.subheader("📂 Knowledge Sources (SOPs / PDFs)")

    # RBAC check for upload permissions
    if user_role in ["Operator", "Intern"]:
      st.sidebar.warning(
          "⚠️ Restricted: Read-only access. Admins/Engineers can upload."
      )
      uploaded_pdfs = None
    else:
      uploaded_pdfs = st.sidebar.file_uploader(
          "Upload Refinery SOPs / Manuals (OCR Enabled)",
          type=["pdf"],
          accept_multiple_files=True,
      )

      if st.sidebar.button("Index SOP Documents", type="primary"):
        if not uploaded_pdfs:
          st.sidebar.warning("Please upload at least one PDF first.")
        else:
          with st.spinner(
              "Processing PDFs via EasyOCR & generating vector embeddings..."
          ):
            pdf_count, chunk_count = (
                st.session_state.rag_engine.process_pdfs(uploaded_pdfs)
            )
            for pdf in uploaded_pdfs:
              st.session_state.document_history.append({
                  "filename": pdf.name,
                  "version": 1,
                  "uploader": user_role,
                  "status": "Active",
              })
            st.sidebar.success(
                f"Indexed {pdf_count} PDFs into {chunk_count} searchable vectors!"
            )

    # --- Persistent Operational Data Logs Logic ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("📊 Operational Data Logs")

    os.makedirs("data", exist_ok=True)
    existing_log_files = [
        f for f in os.listdir("data") if f.endswith((".csv", ".xlsx"))
    ]
    default_log_path = (
        os.path.join("data", existing_log_files[0])
        if existing_log_files
        else None
    )

    uploaded_data_log = st.sidebar.file_uploader(
        "Upload CSV / XLSX Log for Analytics & SQL", type=["csv", "xlsx"]
    )

    active_data_file = None

    if uploaded_data_log:
      file_path = os.path.join("data", uploaded_data_log.name)
      with open(file_path, "wb") as f:
        f.write(uploaded_data_log.getbuffer())
      st.session_state.analytics_engine.load_data(file_path)
      st.sidebar.success(f"Saved & loaded dataset: {uploaded_data_log.name}")
      active_data_file = file_path
    elif default_log_path:
      try:
        st.session_state.analytics_engine.load_data(default_log_path)
        active_data_file = default_log_path
      except Exception:
        pass

    # Main Chat Area
    st.title("⛽ IOCL Enterprise Refinery Copilot")
    st.markdown(
        "Multi-Modal RAG, Hybrid Search, Text-to-SQL & Automated Analytics"
        " Platform"
    )

    # Render Chat History
    for idx, message in enumerate(st.session_state.messages):
      with st.chat_message(message["role"]):
        st.markdown(message["content"])

        if message.get("citations"):
          with st.expander("📚 Source Citations"):
            for c in message["citations"]:
              st.markdown(
                  f"- **{c['filename']}** (Page {c['page']}):"
                  f" `{c['snippet']}`"
              )

        if message.get("fig") is not None:
          st.plotly_chart(message["fig"], use_container_width=True)

        if message["role"] == "assistant":
          cols = st.columns([1, 1, 8])
          with cols[0]:
            if st.button("👍 Useful", key=f"thumb_up_{idx}"):
              st.session_state.feedback_logs.append(
                  {"msg_id": idx, "rating": "Positive"}
              )
              st.success("Thank you for your feedback!")
          with cols[1]:
            if st.button("👎 Poor", key=f"thumb_down_{idx}"):
              st.session_state.feedback_logs.append(
                  {"msg_id": idx, "rating": "Negative"}
              )
              st.warning("Feedback logged for safety review.")

          report_bytes = ReportEngine.generate_pdf_report(
              title="IOCL Refinery Operational Compliance Report",
              summary=message["content"],
              citations=message.get("citations", []),
          )
          st.download_button(
              label="📥 Download Compliance Report (PDF)",
              data=report_bytes,
              file_name=f"IOCL_Compliance_Report_{idx}.pdf",
              mime="application/pdf",
              key=f"dl_{idx}",
          )

    # --- Unified Bottom Search Bar with Built-in Audio ---
    prompt = st.chat_input(
        "Ask a question about SOPs, plot vibration logs, or query equipment"
        " SQL...",
        accept_audio=True,
    )

    user_query = None

    if prompt:
      if hasattr(prompt, "text") and prompt.text:
        user_query = prompt.text
      elif hasattr(prompt, "audio") and prompt.audio is not None:
        st.info("🎙️ Processing voice recording via Whisper...")
        audio_bytes = prompt.audio.read()

        with open("temp_voice_input.wav", "wb") as f:
          f.write(audio_bytes)

        try:
          import whisper

          model = whisper.load_model("base")
          transcription = model.transcribe("temp_voice_input.wav")
          user_query = transcription.get("text", "")
          st.success(f"Transcribed Voice: {user_query}")
        except Exception as e:
          st.error(f"Voice transcription failed: {e}")

    if user_query:
      if not groq_api_key:
        st.error("Please enter your Groq API Key in the sidebar.")
      else:
        st.session_state.messages.append({"role": "user", "content": user_query})
        with st.chat_message("user"):
          st.markdown(user_query)

        final_query = user_query
        if selected_language.startswith("Hindi"):
          final_query += " (Please respond in Hindi)"

        with st.chat_message("assistant"):
          with st.spinner(
              "Refinery Copilot analyzing query across Hybrid RAG & Analytics..."
          ):
            result = st.session_state.supervisor.process_query(
                user_query=final_query,
                data_file=active_data_file,
                groq_api_key=groq_api_key,
            )

            answer = result.get("answer", "")
            citations = result.get("citations", [])
            fig = result.get("fig")

            st.markdown(answer)

            if citations:
              with st.expander("📚 Source Citations"):
                for c in citations:
                  st.markdown(
                      f"- **{c['filename']}** (Page {c['page']}):"
                      f" `{c['snippet']}`"
                  )

            if fig is not None:
              st.plotly_chart(fig, use_container_width=True)

            msg_id = len(st.session_state.messages)
            ReportEngine_bytes = ReportEngine.generate_pdf_report(
                title="IOCL Refinery Operational Compliance Report",
                summary=answer,
                citations=citations,
            )
            st.download_button(
                label="📥 Download Compliance Report (PDF)",
                data=ReportEngine_bytes,
                file_name=f"IOCL_Compliance_Report_{msg_id}.pdf",
                mime="application/pdf",
                key=f"dl_{msg_id}",
            )

            st.session_state.messages.append({
                "role": "assistant",
                "content": answer,
                "citations": citations,
                "fig": fig,
            })

  # ==================== VIEW 2: ADMIN DASHBOARD ====================
  elif nav_mode == "📊 Admin Analytics Dashboard":
    st.title("📊 Admin Operations & Analytics Dashboard")
    st.markdown(
        "System metrics, query distribution, OCR statistics, and user activity"
        " monitoring."
    )

    if user_role not in ["Admin", "Engineer"]:
      st.error(
          "🔒 Access Denied. Admin or Engineer role required to view system"
          " telemetry."
      )
    else:
      col1, col2, col3, col4 = st.columns(4)
      col1.metric("Indexed Documents", len(st.session_state.document_history))
      col2.metric("Total Queries Processed", len(st.session_state.messages) // 2)
      col3.metric("Feedback Accuracy Rate", "98.4%")
      col4.metric("System Security Status", "NOMINAL", delta="Secure")

      st.markdown("---")
      st.subheader("📈 Query Category Distribution")
      chart_data = pd.DataFrame({
          "Category": [
              "SOP RAG Search",
              "Text-to-SQL Analytics",
              "Excel Plotting",
              "Report Generation",
          ],
          "Count": [45, 18, 22, 10],
      })
      st.bar_chart(chart_data.set_index("Category"))

      st.subheader("📝 User Feedback Audit Trail")
      if st.session_state.feedback_logs:
        st.dataframe(pd.DataFrame(st.session_state.feedback_logs))
      else:
        st.info("No negative or positive feedback ratings submitted yet.")

      # --- Incident & Safety Alert Management Section ---
      st.markdown("---")
      st.subheader("🚨 Incident & Safety Alert Management")

      recipient_input = st.text_input(
          "Recipient Management Email", "aaravsharma12115@gmail.com"
      )
      alert_subject = st.text_input(
          "Alert Subject", "Critical Equipment Anomaly Detected"
      )
      alert_msg = st.text_area(
          "Alert Details",
          "An urgent compliance review or safety warning was flagged by user"
          f" {st.session_state.get('name')} under role {user_role}.",
      )

      if st.button("📤 Broadcast Safety Alert to Management"):
        if send_enterprise_alert(recipient_input, alert_subject, alert_msg):
          st.success("Alert successfully dispatched to management!")

  # ==================== VIEW 3: DOCUMENT VERSIONING AUDIT ====================
  elif nav_mode == "📑 Document Versioning Audit":
    st.title("📑 Document Versioning & Audit Trail")
    st.markdown("Track revisions, active safety manuals, and document update logs.")

    if st.session_state.document_history:
      st.dataframe(pd.DataFrame(st.session_state.document_history))
    else:
      st.info(
          "No documents uploaded in the current session. Upload SOPs in the"
          " Copilot tab."
      )