"""
sema_core: the framework-free SEMA backend.

Everything here runs identically under Streamlit, FastAPI, tests, and scripts:
the agent loop, SQL safety, semantic layer, client registry, DB pools,
settings, observability, and the alerts engine. UI code (Streamlit) lives in
app/; the REST layer lives in api/. Neither is imported from here.
"""
