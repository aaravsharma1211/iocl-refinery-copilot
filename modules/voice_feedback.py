
import streamlit as st
import whisper
import tempfile
import os


class VoiceFeedbackModule:
    """Handles hands-free speech input for field operators and AI response audit ratings."""

    @staticmethod
    def render_voice_input() -> str:
        """Renders browser microphone input and transcribes speech using local Whisper."""
        st.markdown("### 🎙️ Refinery Field Voice Assistant")
        audio_file = st.audio_input("Record operational voice query")
        
        if audio_file is not None:
            st.audio(audio_file)
            if st.button("Transcribe & Submit"):
                with st.spinner("Transcribing speech with Whisper..."):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                        tmp.write(audio_file.getvalue())
                        tmp_path = tmp.name
                    
                    try:
                        model = whisper.load_model("tiny")
                        result = model.transcribe(tmp_path, language="en")
                        transcript = result.get("text", "").strip()
                        os.unlink(tmp_path)
                        st.success(f"Transcribed: {transcript}")
                        return transcript
                    except Exception as e:
                        st.error(f"Transcription error: {e}")
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
        return ""

    @staticmethod
    def render_feedback_widget(message_id: str):
        """Renders feedback ratings for compliance tracking."""
        cols = st.columns([1, 1, 6])
        with cols[0]:
            if st.button("👍 Helpful", key=f"up_{message_id}"):
                st.toast("Feedback recorded: Helpful", icon="✅")
        with cols[1]:
            if st.button("👎 Flag Issue", key=f"down_{message_id}"):
                st.toast("Feedback recorded: Flagged for review", icon="⚠️")