import os
import re
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from langchain_groq import ChatGroq


class AnalyticsEngine:
    """
    Core Data Analytics & Text-to-SQL Engine for IOCL Enterprise Copilot.
    Handles:
    1. Dynamic Pandas analysis & Plotly visual generation via code execution.
    2. Natural Language to SQL translation and execution on relational DBs / SQLite.
    """

    def __init__(self, db_path: str = None, groq_api_key: str = None):
        self.df = None
        self.conn = None
        self.db_path = db_path
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY")

    def load_data(self, file_input) -> pd.DataFrame:
        """
        Loads CSV or Excel data into self.df and automatically syncs it
        to an in-memory SQLite table for Text-to-SQL capability.
        """
        if isinstance(file_input, str):
            if file_input.endswith(".csv"):
                self.df = pd.read_csv(file_input)
            else:
                self.df = pd.read_excel(file_input)
        elif hasattr(file_input, "read"):
            # Supports Streamlit UploadedFile buffers
            try:
                self.df = pd.read_csv(file_input)
            except Exception:
                file_input.seek(0)
                self.df = pd.read_excel(file_input)

        # Sync dataset to in-memory SQLite database for Text-to-SQL queries
        if self.df is not None:
            self._sync_df_to_sqlite()

        return self.df

    def _sync_df_to_sqlite(self) -> None:
        """Syncs the loaded DataFrame to an in-memory SQLite table with sanitized column names."""
        if self.df is None:
            return
        
        # Sanitize column names directly on self.df to keep Pandas and SQL synchronized
        self.df.columns = [re.sub(r'[^0-9a-zA-Z_]', '_', str(col)).lower() for col in self.df.columns]
        
        # Initialize connection and write to SQLite
        self.conn = sqlite3.connect(":memory:")
        self.df.to_sql("operational_logs", self.conn, if_exists="replace", index=False)

    def _get_llm(self, api_key: str = None) -> ChatGroq:
        key = api_key or self.groq_api_key
        if not key:
            raise ValueError("Groq API Key is missing. Please provide it in the sidebar or environment.")
        return ChatGroq(
            model_name="llama-3.3-70b-versatile",
            groq_api_key=key,
            temperature=0.0
        )

    def analyze_query(self, query: str, api_key: str = None) -> tuple[str, go.Figure | None]:
        """
        Generates Python code for pandas data processing and Plotly chart creation,
        executes it in a controlled environment, and returns a text explanation + Plotly Figure object.
        """
        if self.df is None:
            return "No dataset loaded. Please upload a CSV or Excel operational log file first.", None

        llm = self._get_llm(api_key)

        data_sample = self.df.head(3).to_markdown()
        data_types = self.df.dtypes.to_dict()

        prompt = f"""You are an Expert Python Data Analyst for IOCL Refinery Operations.
You are given a pandas DataFrame named `df` with the following schema:
Columns & Types: {data_types}
Sample Data:
{data_sample}

User Query: "{query}"

Write executable Python code to analyze the data and create a Plotly figure if requested or appropriate.
Follow these STRICT rules:
1. Assign your final Plotly figure to a variable named `fig` (using `px.line`, `px.scatter`, `px.bar`, `px.histogram`, etc.).
2. Assign a concise textual summary of findings to a variable named `summary`.
3. Do NOT import pandas, plotly, or other libraries inside the code snippet (they are pre-imported as `pd`, `px`, `go`).
4. Output ONLY valid Python code wrapped inside triple backticks ```python ... ``` without conversational fluff.
"""

        response = llm.invoke(prompt).content
        code = self._extract_code(response)

        # Execution scope
        exec_scope = {
            "pd": pd,
            "px": px,
            "go": go,
            "df": self.df.copy(),
            "fig": None,
            "summary": "Analysis completed."
        }

        try:
            exec(code, exec_scope)
            fig = exec_scope.get("fig", None)
            summary = exec_scope.get("summary", "Analysis executed successfully.")
            return summary, fig
        except Exception as e:
            return f"Error executing generated code: {str(e)}\n\n**Executed Code:**\n```python\n{code}\n```", None

    def execute_sql(self, query: str, api_key: str = None) -> dict:
        """
        Converts natural language user query into an ANSI SQL query,
        executes it against SQLite database connection, and returns results.
        """
        llm = self._get_llm(api_key)

        if self.conn and self.df is not None:
            schema_info = f"Table 'operational_logs' with columns: {list(self.df.columns)}"
            conn_to_use = self.conn
        else:
            schema_info = """
            Available Tables:
            1. equipment_maintenance (id, equipment_id, name, unit, last_serviced_date, status, technician)
            2. employee_trainings (emp_id, name, department, course_name, completion_date, status)
            3. refinery_units (unit_id, unit_name, capacity_bpd, status, manager)
            """
            conn_to_use = self._get_mock_db_connection()

        prompt = f"""You are a Database Engineer for IOCL Refinery Enterprise Systems.
Translate the user's natural language question into a clean ANSI SQL query.

Database Schema:
{schema_info}

User Question: "{query}"

Rules:
1. Return ONLY the SQL query enclosed in ```sql ... ``` code block.
2. Read-only queries only (SELECT statements). Do NOT use DROP, DELETE, INSERT, or UPDATE.
3. Keep column names accurate to the schema provided.
4. IMPORTANT: When asked for names, lists, or records, select the columns directly (e.g., SELECT name FROM ...) without using COUNT(*) so all individual rows are returned.
"""

        llm_response = llm.invoke(prompt).content
        sql_query = self._extract_sql(llm_response)

        try:
            cursor = conn_to_use.cursor()
            cursor.execute(sql_query)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()

            data_result = [dict(zip(columns, row)) for row in rows]
            
            if data_result:
                lines = [f"Query executed successfully. Retrieved {len(data_result)} record(s):"]
                for idx, row in enumerate(data_result, 1):
                    row_str = ", ".join([f"**{k}**: {v}" for k, v in row.items()])
                    lines.append(f"{idx}. {row_str}")
                explanation = "\n".join(lines)
            else:
                explanation = "Query executed successfully, but no matching records were found."

            return {
                "sql": sql_query,
                "data": data_result,
                "explanation": explanation
            }
        except Exception as e:
            return {
                "sql": sql_query,
                "data": [],
                "explanation": f"SQL Execution Error: {str(e)}"
            }

    def _get_mock_db_connection(self) -> sqlite3.Connection:
        """Generates an in-memory relational database with realistic refinery sample tables."""
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE equipment_maintenance (
                id INTEGER PRIMARY KEY,
                equipment_id TEXT,
                name TEXT,
                unit TEXT,
                last_serviced_date TEXT,
                status TEXT,
                technician TEXT
            )
        """)
        cursor.executemany("""
            INSERT INTO equipment_maintenance VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            (1, "PUMP-101A", "Crude Charge Pump", "CDU-1", "2026-06-15", "Operational", "R. K. Sharma"),
            (2, "COMP-202B", "Hydrogen Compressor", "HCU-2", "2026-07-01", "Maintenance Required", "A. Verma"),
            (3, "EXCH-304C", "Heat Exchanger", "VDU-1", "2026-05-20", "Operational", "S. Patel"),
            (4, "PUMP-102B", "Boiler Feed Pump", "UTILITIES", "2026-07-10", "Operational", "R. K. Sharma"),
        ])

        cursor.execute("""
            CREATE TABLE employee_trainings (
                emp_id TEXT PRIMARY KEY,
                name TEXT,
                department TEXT,
                course_name TEXT,
                completion_date TEXT,
                status TEXT
            )
        """)
        cursor.executemany("""
            INSERT INTO employee_trainings VALUES (?, ?, ?, ?, ?, ?)
        """, [
            ("IOCL-8041", "Rajesh Kumar", "Operations", "Hazop Safety Certification", "2026-03-10", "Certified"),
            ("IOCL-8042", "Priya Singh", "Maintenance", "Vibration Analysis Level 2", "2026-04-15", "Certified"),
            ("IOCL-8043", "Amit Roy", "Safety", "Fire & Gas System Handling", "2026-06-01", "Expired"),
        ])

        conn.commit()
        return conn

    @staticmethod
    def _extract_code(text: str) -> str:
        """Helper to extract executable Python code from LLM responses."""
        match = re.search(r"```python\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1)
        return text.strip()

    @staticmethod
    def _extract_sql(text: str) -> str:
        """Helper to extract clean SQL query strings from LLM responses."""
        match = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1)
        return text.replace("```sql", "").replace("```", "").strip()