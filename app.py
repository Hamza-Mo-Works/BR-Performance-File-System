"""Streamlit entry point. Run: python -m streamlit run app.py"""
import streamlit as st
from ui.ingestion_page import render_ingestion_page
from ui.matching_page import render_matching_page
from ui.assistant_page import render_assistant_page
from ui.review_page import render_review_page

st.set_page_config(page_title="Engineering Request Copilot", page_icon="🚗", layout="wide")
upload_tab, matching_tab, assistant_tab, review_tab = st.tabs([
    "1. Upload request", "2. Historical matching", "3. Engineering assistant", "4. Review and export"])
with upload_tab:
    render_ingestion_page()
with matching_tab:
    render_matching_page()
with assistant_tab:
    render_assistant_page()
with review_tab:
    render_review_page()
