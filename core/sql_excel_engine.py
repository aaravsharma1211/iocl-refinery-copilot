import sqlite3
import pandas as pd
import re
from langchain_groq import ChatGroq


class SqlExcelEngine:
    """Handles Excel/CSV analytics and Natural Language to SQL querying for refinery operational logs."""
    def __init__(self, groq_api_key: str = None):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.df = None
        self.api_key = groq_api_key

    def load_excel_or_csv(self, uploaded_file) -> str:
        """Loads Excel or CSV into a pandas DataFrame and syncs to SQLite with sanitized columns."""
        if uploaded_file.name.endswith('.csv'):
            self.df = pd.read_csv(uploaded_file)
        else:
            self.df = pd.read_excel(uploaded_file)
        
        self._sync_df_to_sqlite()
        return f"Successfully loaded {uploaded_file.name} with {len(self.df)} rows."

    def _sync_df_to_sqlite(self):
        """Syncs DataFrame to an in-memory SQLite table with sanitized column names."""
        if self.df is None:
            return
        clean_df = self.df.copy()
        clean_df.columns = [re.sub(r'[^0-9a-zA-Z_]', '_', str(col)).lower() for col in clean_df.columns]
        clean_df.to_sql("operational_logs", self.conn, if_exists="replace", index=False)

    def query_with_natural_language(self, user_question: str) -> dict:
        """Translates natural language to SQL, executes it on SQLite, and summarizes via Groq."""
        if self.df is None:
            return {"result": "No operational log file loaded. Please upload an Excel or CSV file first.", "sql": ""}

        # Get schema description
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA table_info(operational_logs);")
        columns = [row[1] for row in cursor.fetchall()]
        schema_desc = f"Table name: operational_logs\nColumns: {', '.join(columns)}"

        llm = ChatGroq(model_name="llama-3.3-70b-versatile", groq_api_key=self.api_key, temperature=0.0)
        
        prompt = f"""You are a SQL expert. Given the following SQLite table schema, write a valid SQL query to answer the user's question. 
Return ONLY the executable SQL query inside a markdown code block (e.g., ```sql ... ```), with no extra text.

Schema:
{schema_desc}

User Question: {user_question}
"""
        response = llm.invoke(prompt).content
        
        # Extract SQL from code block
        sql_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", response, re.DOTALL)
        sql_query = sql_match.group(1).strip() if sql_match else response.strip()

        try:
            result_df = pd.read_sql_query(sql_query, self.conn)
            summary_prompt = f"""Based on the following query result for the question '{user_question}', provide a clear, professional operational summary.

SQL Query used: {sql_query}
Query Result:
{result_df.to_string(index=False)}
"""
            summary = llm.invoke(summary_prompt).content
            return {"result": summary, "sql": sql_query, "data": result_df}
        except Exception as e:
            return {"result": f"SQL Execution Error: {e}", "sql": sql_query, "data": None}