import os
import re
from langchain_groq import ChatGroq


class SupervisorAgent:
    """
    Intelligent Orchestrator Agent for IOCL Enterprise Refinery Copilot.
    Classifies user intent and routes execution to specialized core modules:
    - RAG: SOP manuals, PDFs, safety specs, equipment guides.
    - ANALYTICS: Dynamic Pandas code interpreter & Plotly visualization for CSV/XLSX logs.
    - SQL: Natural language to ANSI SQL execution on operational databases.
    - REPORT: Shift report compiling & PDF exports.
    """

    INTENT_RAG = "RAG"
    INTENT_SQL = "SQL"
    INTENT_ANALYTICS = "ANALYTICS"
    INTENT_REPORT = "REPORT"

    def __init__(self, rag_engine=None, analytics_engine=None, groq_api_key: str = None):
        self.rag_engine = rag_engine
        self.analytics_engine = analytics_engine
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY")

    def _get_llm(self, api_key: str = None) -> ChatGroq:
        key = api_key or self.groq_api_key
        if not key:
            raise ValueError("Groq API Key is missing. Please provide it in the sidebar or config.")
        return ChatGroq(
            model_name="llama-3.3-70b-versatile",
            groq_api_key=key,
            temperature=0.0
        )

    def classify_intent(self, query: str, has_data_log: bool = False, api_key: str = None) -> str:
        """
        Uses Llama 3.3 to classify the user query into exact operational categories.
        Includes rule-based fallback if the LLM API key is missing.
        """
        try:
            llm = self._get_llm(api_key)
        except ValueError:
            # Fallback keyword rules if API key isn't provided yet
            q_lower = query.lower()
            if any(w in q_lower for w in ["plot", "chart", "graph", "vibration", "trend", "scatter", "bar chart", "csv", "excel"]):
                return self.INTENT_ANALYTICS
            elif any(w in q_lower for w in ["database", "select", "sql", "how many employees", "serviced this month", "table"]):
                return self.INTENT_SQL
            elif any(w in q_lower for w in ["shift report", "download pdf", "export summary", "incident report"]):
                return self.INTENT_REPORT
            return self.INTENT_RAG

        prompt = f"""You are the Supervisor Router for the IOCL Enterprise Refinery Copilot.
Analyze the user's request and classify it into EXACTLY ONE of these 4 categories:

1. RAG: Questions about refinery SOPs, manuals, safety guidelines, pump isolation, IT policies, conduct rules, equipment specs, or general document knowledge.
2. SQL: Questions asking for structured database metrics (e.g., employee training records, database tables, equipment maintenance records).
3. ANALYTICS: Requests to analyze data logs, calculate column metrics, compare parameters, or plot visual graphs/charts from uploaded CSV/Excel files.
4. REPORT: Explicit requests to generate, compile, or export shift reports or PDF summaries.

Context state: Data log file uploaded = {has_data_log}

User Query: "{query}"

Respond with ONLY ONE word: RAG, SQL, ANALYTICS, or REPORT.
Do not include punctuation, quotes, or markdown formatting.
"""
        response = llm.invoke(prompt).content.strip().upper()

        # Clean LLM response to match intent constants
        for valid_intent in [self.INTENT_RAG, self.INTENT_SQL, self.INTENT_ANALYTICS, self.INTENT_REPORT]:
            if valid_intent in response:
                return valid_intent

        return self.INTENT_RAG

    def process_query(
        self,
        user_query: str,
        data_file=None,
        groq_api_key: str = None,
        override_intent: str = None
    ) -> dict:
        """
        Main execution router. Classifies intent and delegates execution.
        Returns a unified dictionary payload designed for easy rendering in app.py.
        """
        api_key = groq_api_key or self.groq_api_key
        has_data_log = data_file is not None or (
            self.analytics_engine and getattr(self.analytics_engine, "df", None) is not None
        )

        # 1. Classify Intent
        intent = override_intent or self.classify_intent(user_query, has_data_log=has_data_log, api_key=api_key)

        response_payload = {
            "intent": intent,
            "answer": "",
            "citations": [],
            "fig": None,
            "sql_query": None,
            "data_table": None,
            "error": None
        }

        try:
            # Pathway A: Hybrid RAG Search
            if intent == self.INTENT_RAG:
                if self.rag_engine:
                    rag_response = self.rag_engine.query(user_query, groq_api_key=api_key)
                    response_payload["answer"] = rag_response.get("answer", "")
                    response_payload["citations"] = rag_response.get("citations", [])
                else:
                    response_payload["answer"] = "RAG Engine is not initialized in system state."

            # Pathway B: Excel / CSV Data Analytics & Plotly Generation
            elif intent == self.INTENT_ANALYTICS:
                if self.analytics_engine:
                    if data_file and hasattr(self.analytics_engine, "load_data"):
                        self.analytics_engine.load_data(data_file)
                    
                    analysis_text, fig = self.analytics_engine.analyze_query(user_query, api_key=api_key)
                    response_payload["answer"] = analysis_text
                    response_payload["fig"] = fig
                else:
                    response_payload["answer"] = "Analytics Engine is not initialized in system state."

            # Pathway C: Text-to-SQL
            
            elif intent == self.INTENT_SQL:
                if self.analytics_engine and hasattr(self.analytics_engine, "execute_sql"):
                    sql_result = self.analytics_engine.execute_sql(user_query, api_key=api_key)
                    
                    data_rows = sql_result.get("data", [])
                    sql_text = sql_result.get("sql", "")
                    
                    # Force-inject raw rows into the answer text if they exist
                    if data_rows and isinstance(data_rows, list):
                        lines = [f"Retrieved {len(data_rows)} record(s):"]
                        for idx, row in enumerate(data_rows, 1):
                            row_str = ", ".join([f"**{k}**: {v}" for k, v in row.items()])
                            lines.append(f"{idx}. {row_str}")
                        response_payload["answer"] = "\n".join(lines)
                    else:
                        response_payload["answer"] = sql_result.get("explanation", "SQL query executed.")

                    response_payload["sql_query"] = sql_text
                    response_payload["data_table"] = data_rows
                else:
                    response_payload["answer"] = "Text-to-SQL engine module is not configured."

            # Pathway D: Report Generator
            elif intent == self.INTENT_REPORT:
                response_payload["answer"] = f"Ready to generate an official IOCL operational shift report summarizing: '{user_query}'."

        except Exception as e:
            response_payload["error"] = str(e)
            response_payload["answer"] = f"An execution error occurred in {intent} mode: {str(e)}"

        return response_payload