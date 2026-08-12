import streamlit as st


class RBACAdminModule:
    """Handles Role-Based Access Control (Operator vs Admin) and Admin Dashboard controls."""

    @staticmethod
    def render_auth_sidebar() -> str:
        """Renders role selection in the sidebar."""
        st.sidebar.markdown("### 🔐 User Authentication & RBAC")
        role = st.sidebar.selectbox("Select User Role", ["Refinery Operator", "Administrator"])
        
        if role == "Administrator":
            admin_pass = st.sidebar.text_input("Admin Passcode", type="password")
            if admin_pass != "IOCL@Admin2026":
                st.sidebar.warning("Incorrect passcode. Defaulting to Operator permissions.")
                return "Refinery Operator"
        return role

    @staticmethod
    def render_admin_dashboard(rag_engine, sql_engine):
        """Renders administrative controls and system audit view."""
        st.markdown("## 🛡️ Admin Dashboard & System Audit")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Vector DB Status", "Active", "ChromaDB Persistent")
        with col2:
            st.metric("SQL Engine Status", "Active", "In-Memory SQLite")

        st.markdown("### 📋 System Management & Vector Maintenance")
        if st.button("Clear Vector Database Cache"):
            try:
                rag_engine.chroma_client.delete_collection("iocl_sops")
                rag_engine.collection = rag_engine.chroma_client.get_or_create_collection(name="iocl_sops")
                st.success("Vector database cache successfully cleared.")
            except Exception as e:
                st.error(f"Error clearing vector database: {e}")

        st.markdown("### 📊 Active Operational Schema View")
        if sql_engine.df is not None:
            st.dataframe(sql_engine.df.head(10))
        else:
            st.info("No operational log dataset loaded currently.")