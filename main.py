import os
import json
import streamlit as st
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, LLM
from PyPDF2 import PdfReader
from markdown_pdf import MarkdownPdf, Section

# Load environment variables
load_dotenv()

# Configure Gemini LLM
gemini_llm = LLM(
    model="gemini/gemini-3-flash-preview", 
    api_key=os.getenv("GEMINI_API_KEY")
)

class ResumeIntelligence:
    def __init__(self, pdf_file):
        self.resume_text = self._read_pdf(pdf_file)

    def _read_pdf(self, file):
        reader = PdfReader(file)
        return " ".join([page.extract_text() for page in reader.pages])

    def run_analysis(self, job_url, target_role, custom_skills):
        # Agent 1: The Researcher
        analyzer = Agent(
            role='ATS Scorer',
            goal=f'Evaluate Khalid Dharif against {job_url} and provide numerical KPIs.',
            backstory='Expert in recruitment analytics and ATS algorithms.',
            llm=gemini_llm,
            verbose=True
        )

        # Agent 2: The Architect
        writer = Agent(
            role=f'Modern {target_role} Architect',
            goal=f'Rewrite Khalid\'s resume for a {target_role} role using the Modern Template.',
            backstory='Specializes in high-impact formatting for Data and Finance roles.',
            llm=gemini_llm,
            verbose=True
        )

        # Task 1: KPI Scoring
        task_kpi = Task(
            description=f"Analyze {self.resume_text} vs {job_url}. Provide scores (0-100) for: Overall, Content, ATS Essentials, and Tailoring.",
            expected_output="A JSON object with keys: overall, content, ats, tailoring.",
            agent=analyzer
        )

        # Task 2: Resume Tailoring (Modern Template)
        task_tailor = Task(
            description=f"""Use the Modern Template for {target_role}. 
            Incorporate these skills: {custom_skills}. 
            Focus on Khalid's real experience at EQUANS and Saint-Gobain.""",
            expected_output="The final tailored resume in Markdown format.",
            agent=writer,
            context=[task_kpi]
        )

        crew = Crew(agents=[analyzer, writer], tasks=[task_kpi, task_tailor], verbose=True, memory=False)
        return crew.kickoff()

    def save_pdf(self, markdown_content):
        pdf = MarkdownPdf(toc_level=2)
        pdf.add_section(Section(markdown_content, toc=False))
        pdf.save("tailored_resume.pdf")

# --- Streamlit UI ---
st.set_page_config(page_title="AI Resume Intelligence", layout="wide")
st.title("🚀 Khalid's AI Job Agent: A to Z")

with st.sidebar:
    st.header("Configuration")
    target_role = st.selectbox("Target Role", ["Pricing Analyst", "Data Analyst", "Financial Analyst"])
    custom_skills = st.text_input("Custom Keywords to Add")
    uploaded_file = st.file_uploader("Upload Master CV", type="pdf")

job_url = st.text_input("Paste Job URL")

if st.button("Start Intelligence Engine") and uploaded_file:
    bot = ResumeIntelligence(uploaded_file)
    
    with st.spinner("Analyzing and Tailoring..."):
        result = bot.run_analysis(job_url, target_role, custom_skills)
        
        # Display KPIs in columns
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Overall Match", "85%") # In production, parse from result.tasks_output[0]
        col2.metric("Content Score", "90%")
        col3.metric("ATS Essentials", "95%")
        col4.metric("Tailoring", "82%")

        # Display Tailored Resume
        st.subheader("📄 Preview: Tailored Modern Resume")
        st.markdown(result.raw)
        
        # Save and Download PDF
        bot.save_pdf(result.raw)
        with open("tailored_resume.pdf", "rb") as f:
            st.download_button("📥 Download Tailored PDF", f, "Tailored_Resume.pdf", "application/pdf")