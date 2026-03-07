"""
AI Resume Intelligence Platform with Custom Professional Template
Your specific template structure with categorized skills and contact header
"""

# CRITICAL: Set these BEFORE any other imports
import os
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["PYDANTIC_SKIP_VALIDATING_CORE_SCHEMAS"] = "true"
os.environ["CREWAI_TELEMETRY_ENABLED"] = "false"

import tempfile
import json
import re
import streamlit as st
from crewai import Agent, Task, Crew, LLM
from PyPDF2 import PdfReader
import requests
from bs4 import BeautifulSoup
from typing import Dict, Optional, Tuple
import logging
import subprocess

# --- SECTION 1: SYSTEM INITIALIZATION ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if "GEMINI_API_KEY" in st.secrets:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]
    os.environ["GOOGLE_API_KEY"] = st.secrets["GEMINI_API_KEY"]

# Constants
MAX_PDF_SIZE_MB = 10
MAX_PDF_SIZE_BYTES = MAX_PDF_SIZE_MB * 1024 * 1024

SUPPORTED_LANGUAGES = {
    "English": "en",
    "French": "fr", 
    "Spanish": "es",
    "German": "de",
    "Arabic": "ar",
    "Portuguese": "pt",
    "Italian": "it",
    "Dutch": "nl",
    "Chinese": "zh"
}

# CV TEMPLATE - Single default template logic
CV_TEMPLATES = {
    "ATS Native (FPDF)": {
        "description": "Professional 1-column layout, highly ATS-readable.",
        "color": "#304263",
        "style": "fpdf_native",
        "icon": "📄",
        "best_for": "Data Science, IT, Business"
    }
}

@st.cache_resource
def get_llm():
    """Cached LLM instance to avoid recreation"""
    return LLM(
        model="gemini/gemini-flash-latest",
        api_key=os.environ.get("GEMINI_API_KEY"),
        temperature=0.1
    )

# --- SECTION 2: UTILITY FUNCTIONS ---
class JobScraper:
    """Handles job description extraction from URLs"""
    
    @staticmethod
    def fetch_job_description(url: str, timeout: int = 10) -> Tuple[bool, str]:
        if not url or not url.startswith(('http://', 'https://')):
            return False, "Invalid URL format. Please include http:// or https://"
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()
            
            text = soup.get_text(separator=' ', strip=True)
            text = re.sub(r'\s+', ' ', text).strip()
            
            if len(text) < 100:
                return False, "Unable to extract sufficient job description content."
            
            return True, text[:5000]
            
        except requests.Timeout:
            return False, "Request timed out. Please paste the job description manually."
        except requests.RequestException as e:
            logger.error(f"Error fetching URL: {str(e)}")
            return False, f"Could not fetch job description."
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return False, "An unexpected error occurred while fetching."

class InputValidator:
    """Validates user inputs"""
    
    @staticmethod
    def validate_pdf(file) -> Tuple[bool, str]:
        if file is None:
            return False, "Please upload a PDF file"
        if not file.name.endswith('.pdf'):
            return False, "File must be a PDF"
        if file.size > MAX_PDF_SIZE_BYTES:
            return False, f"File size exceeds {MAX_PDF_SIZE_MB}MB limit"
        return True, ""
    
    @staticmethod
    def validate_inputs(target_role: str, job_source: str) -> Tuple[bool, str]:
        if not target_role or len(target_role.strip()) < 2:
            return False, "Please enter a valid target role"
        if not job_source or len(job_source.strip()) < 20:
            return False, "Please provide a job description"
        return True, ""
    
    @staticmethod
    def sanitize_text(text: str, max_length: int = 1000) -> str:
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text.strip())
        return text[:max_length]

class FpdfGenerator:
    """Generates professional 1-column ATS-friendly CV documents using FPDF2"""
    
    @staticmethod
    def generate_pdf(json_data: dict, theme_color_hex: str = "#2C3E50") -> bytes:
        from fpdf import FPDF
        from fpdf.enums import XPos, YPos

        def hex_to_rgb(hex_code: str):
            hex_code = hex_code.lstrip('#')
            if len(hex_code) != 6:
                return (44, 62, 80) # Default fallback
            return tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))
            
        theme_rgb = hex_to_rgb(theme_color_hex)

        # To be safe with ATS unicode compliance, we use standard helvetica encoding
        # and encode/decode to latin-1 replacing complex emojis to prevent crashing
        def safe_text(text: str) -> str:
            if not text: return ""
            # Strip problematic markdown formatting if any lingered
            text = text.replace('**', '').replace('__', '')
            return text.encode('latin-1', 'replace').decode('latin-1')

        pdf = FPDF()
        pdf.add_page()
        # Reduce bottom margin to allow more content on the page
        pdf.set_auto_page_break(auto=True, margin=5)
        
        # --- Header ---
        name = safe_text(json_data.get("name", "Name"))
        title = safe_text(json_data.get("title", ""))
        
        pdf.set_font("helvetica", 'B', 22)
        pdf.set_text_color(*theme_rgb)
        pdf.cell(0, 10, name, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        
        if title:
            pdf.set_font("helvetica", '', 14)
            pdf.set_text_color(127, 140, 141)
            pdf.cell(0, 8, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
            
        pdf.set_text_color(0, 0, 0)
        
        contact = json_data.get("contact", {})
        contact_str = " | ".join(filter(None, [
            safe_text(contact.get("email", "")), 
            safe_text(contact.get("phone", "")), 
            safe_text(contact.get("address", ""))
        ]))
        if contact_str:
            pdf.set_font("helvetica", '', 9)
            pdf.cell(0, 5, contact_str, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
            
        linkedin_url = json_data.get("contact", {}).get("linkedin", "")
        github_url = json_data.get("contact", {}).get("github", "")
        portfolio_url = json_data.get("contact", {}).get("portfolio", "")
        
        socials = []
        if linkedin_url: socials.append(("LinkedIn", linkedin_url))
        if github_url: socials.append(("GitHub", github_url))
        if portfolio_url: socials.append(("Portfolio", portfolio_url))
        
        if socials:
            pdf.set_font("helvetica", '', 9)
            
            # Center the row manually by measuring total text width
            total_width = sum(pdf.get_string_width(s[0]) for s in socials) + (len(socials) - 1) * pdf.get_string_width(" | ")
            start_x = (pdf.w - total_width) / 2
            pdf.set_x(start_x)
            
            for i, (label, url) in enumerate(socials):
                pdf.set_text_color(0, 0, 255) # Blue links
                
                # Make sure the url is valid HTTP
                link_target = url if url.startswith("http") else f"https://{url}"
                pdf.cell(pdf.get_string_width(label), 5, label, link=link_target)
                
                pdf.set_text_color(0, 0, 0)
                if i < len(socials) - 1:
                    pdf.cell(pdf.get_string_width(" | "), 5, " | ")
                    
            pdf.ln(5)
            
        pdf.ln(3)  # Reduced from 8
        
        headers = json_data.get("section_headers", {})
        
        # --- Summary ---
        summary = safe_text(json_data.get("summary", ""))
        if summary:
            pdf.set_font("helvetica", 'B', 11)
            pdf.set_text_color(*theme_rgb)
            pdf.cell(0, 6, safe_text(headers.get("summary", "PROFESSIONAL SUMMARY").upper()), border="B", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)
            pdf.set_font("helvetica", '', 9)
            pdf.multi_cell(0, 4.5, summary, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(2.5)
            
        # --- Experience ---
        experience = json_data.get("experience", [])
        if experience:
            pdf.set_font("helvetica", 'B', 11)
            pdf.set_text_color(*theme_rgb)
            pdf.cell(0, 6, safe_text(headers.get("experience", "PROFESSIONAL EXPERIENCE").upper()), border="B", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)
            
            for exp in experience:
                company = safe_text(exp.get("company", ""))
                role = safe_text(exp.get("role", ""))
                location = safe_text(exp.get("location", ""))
                dates = safe_text(exp.get("dates", ""))
                
                # Title line - absolute positioning for dates
                current_y = pdf.get_y()
                pdf.set_font("helvetica", '', 9)
                pdf.set_xy(pdf.w - pdf.r_margin - 60, current_y)
                pdf.cell(60, 5, dates, align='R', new_x=XPos.LMARGIN, new_y=YPos.TOP)
                
                pdf.set_xy(pdf.l_margin, current_y)
                pdf.set_font("helvetica", 'B', 10)
                pdf.multi_cell(pdf.epw - 65, 5, role, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                
                # Company line
                pdf.set_font("helvetica", 'I', 9.5)
                top_line = company
                if location: top_line += f" - {location}"
                pdf.multi_cell(0, 5, top_line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                
                pdf.set_font("helvetica", '', 9)
                for detail in exp.get("details", []):
                    pdf.multi_cell(0, 4.5, f"- {safe_text(detail)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(1.5)
                
        # --- Skills ---
        skills = json_data.get("skills", [])
        if skills:
            pdf.set_font("helvetica", 'B', 11)
            pdf.set_text_color(*theme_rgb)
            pdf.cell(0, 6, safe_text(headers.get("skills", "TECHNICAL SKILLS").upper()), border="B", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)
            pdf.set_font("helvetica", '', 9)
            for s in skills:
                # Splitting logic to bold category. Use ** for FPDF Markdown parsing or manual width calculation.
                # FPDF allows `markdown=True` in multi_cell if you use asterisk blocks.
                skill_txt = safe_text(s)
                if ":" in skill_txt:
                    parts = skill_txt.split(":", 1)
                    # Use markdown bold syntax
                    skill_txt = f"**{parts[0]}**: {parts[1]}"
                    
                pdf.multi_cell(0, 4.5, "- " + skill_txt, markdown=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(2.5)
            
        # --- Education ---
        education = json_data.get("education", [])
        if education:
            pdf.set_font("helvetica", 'B', 11)
            pdf.set_text_color(*theme_rgb)
            pdf.cell(0, 6, safe_text(headers.get("education", "EDUCATION").upper()), border="B", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)
            
            for edu in education:
                degree = safe_text(edu.get("degree", ""))
                inst = safe_text(edu.get("institution", ""))
                dates = safe_text(edu.get("dates", ""))
                
                current_y = pdf.get_y()
                pdf.set_font("helvetica", '', 9)
                pdf.set_xy(pdf.w - pdf.r_margin - 60, current_y)
                pdf.cell(60, 5, dates, align='R', new_x=XPos.LMARGIN, new_y=YPos.TOP)
                
                pdf.set_xy(pdf.l_margin, current_y)
                pdf.set_font("helvetica", 'B', 9.5)
                pdf.multi_cell(pdf.epw - 65, 5, degree, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                
                pdf.set_font("helvetica", 'I', 9)
                pdf.multi_cell(0, 5, inst, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(1.5)
                
        # --- Certifications ---
        certs = json_data.get("certifications", [])
        if certs:
            pdf.set_font("helvetica", 'B', 11)
            pdf.set_text_color(*theme_rgb)
            pdf.cell(0, 6, safe_text(headers.get("certifications", "CERTIFICATIONS").upper()), border="B", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)
            
            pdf.set_font("helvetica", '', 9.5)
            
            # Extract names depending on if it's a list of dicts (legacy) or simple list (new schema)
            cert_names = []
            for cert in certs:
                if isinstance(cert, dict):
                    name_c = safe_text(cert.get("name", ""))
                    org_c = safe_text(cert.get("organization", ""))
                    cert_names.append(f"{name_c} - {org_c}" if org_c else name_c)
                else:
                    cert_names.append(safe_text(cert))
                    
            cert_str = ", ".join(filter(None, cert_names))
            if cert_str:
                pdf.multi_cell(0, 4.5, cert_str, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(2)
            
        out = pdf.output()
        if isinstance(out, str):
            out = out.encode('latin-1')
        return bytes(out)


# --- SECTION 3: THE INTELLIGENCE ENGINE ---
class ResumeIntelligence:
    """Core resume analysis and tailoring engine"""
    
    def __init__(self, pdf_file):
        self.resume_text = self._read_pdf(pdf_file)
        self.llm = get_llm()
    
    def _read_pdf(self, file) -> str:
        try:
            reader = PdfReader(file)
            if len(reader.pages) == 0:
                raise ValueError("PDF file appears to be empty")
            
            text_parts = []
            for page_num, page in enumerate(reader.pages, 1):
                try:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                except Exception as e:
                    logger.warning(f"Could not extract text from page {page_num}")
                    continue
            
            full_text = " ".join(text_parts)
            if len(full_text.strip()) < 50:
                raise ValueError("Could not extract sufficient text from PDF.")
            
            return full_text
            
        except Exception as e:
            logger.error(f"PDF reading error: {str(e)}")
            raise ValueError(f"Error reading PDF: {str(e)}")
    
    def _parse_scores(self, raw_output: str) -> Optional[Dict[str, int]]:
        try:
            if "```json" in raw_output:
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_output, re.DOTALL)
                if json_match:
                    raw_output = json_match.group(1)
            
            json_match = re.search(r'\{[^{}]*"overall"[^{}]*\}', raw_output)
            if json_match:
                raw_output = json_match.group(0)
            
            scores = json.loads(raw_output)
            required_keys = ['overall', 'content', 'ats', 'tailoring']
            for key in required_keys:
                if key not in scores:
                    scores[key] = 0
                scores[key] = max(0, min(100, int(scores[key])))
            
            return scores
        except Exception as e:
            logger.error(f"Score parsing error: {str(e)}")
            return None
    
    def run_analysis(self, job_description: str, target_role: str, 
                    custom_skills: str, language: str, template_style: str,
                    verbosity: str = "Compact", progress_callback=None) -> Dict:
        try:
            target_role = InputValidator.sanitize_text(target_role, 200)
            custom_skills = InputValidator.sanitize_text(custom_skills, 500)
            
            if progress_callback:
                progress_callback("Creating AI agents...")
            
            analyzer = Agent(
                role='ATS Resume Scorer',
                goal=f'Evaluate resume for {target_role}.',
                backstory='Expert in ATS systems and recruitment.',
                llm=self.llm,
                verbose=False
            )
            
            writer = Agent(
                role=f'Resume Writer - Data/AI Professional',
                goal=f'Create ATS-optimized resume in {language} for {target_role} with categorized skills.',
                backstory=f'Expert resume writer specializing in {language} and technical roles with Data & AI, Analytics, and BI skills categorization.',
                llm=self.llm,
                verbose=False
            )
            
            if progress_callback:
                progress_callback("Analyzing resume...")
            
            task_kpi = Task(
                description=f"""Analyze resume vs job:

RESUME: {self.resume_text[:3000]}
JOB: {job_description[:2000]}
ROLE: {target_role}

Score (0-100): overall, content, ats, tailoring. Return JSON only.""",
                expected_output='JSON: overall, content, ats, tailoring (0-100)',
                agent=analyzer
            )
            
            if progress_callback:
                progress_callback(f"Tailoring resume with custom template...")
            
            skills_instruction = f"\nEmphasize: {custom_skills}" if custom_skills else ""
            
            if verbosity == "Compact":
                bullet_instruction = "Extremely compact and meaningful bullets (1 line max)."
            elif verbosity == "Medium":
                bullet_instruction = "Moderately detailed bullets with 1-2 metrics."
            else:
                bullet_instruction = "Highly detailed bullet points exploring context, actions, and results (multiple sentences ok)."
            
            if progress_callback:
                progress_callback(f"Tailoring resume with LaTeX template constraints...")
            
            task_tailor = Task(
                description=f"""Create tailored resume using this EXACT JSON structure:

ORIGINAL: {self.resume_text}
JOB: {job_description}
ROLE: {target_role}
{skills_instruction}

CRITICAL STRUCTURE - Follow this JSON schema exactly for the final output:
{{
  "name": "First Last",
  "title": "{target_role}",
  "contact": {{
    "email": "user@example.com",
    "phone": "+1 234 567 8900",
    "address": "City, Country",
    "linkedin": "linkedin.com/in/...",
    "github": "github.com/...",
  }},
  "personal": {{
    "citizenship": "Citizenship",
    "family": "Status"
  }},
  "section_headers": {{
    "summary": "Translate 'Professional Summary' to {language}",
    "experience": "Translate 'Professional Experience' to {language}",
    "education": "Translate 'Education' to {language}",
    "skills": "Translate 'Technical Skills' to {language}",
    "certifications": "Translate 'Certifications' to {language}"
  }},
  "languages": ["English", "French"],
  "summary": "3 impactful sentences summarizing expertise and value proposition",
  "skills": ["Category 1: Skill A, Skill B", "Category 2: Skill C, Skill D"],
  "experience": [
    {{
      "company": "Company Name",
      "role": "Job Title",
      "location": "City",
      "dates": "MM/YYYY - MM/YYYY (STRICT FORMAT)",
      "details": ["Compact, highly meaningful achievement 1", "Compact, highly meaningful achievement 2"]
    }}
  ],
  "education": [
    {{
      "degree": "Degree",
      "institution": "University",
      "dates": "MM/YYYY - MM/YYYY"
    }}
  ],
  "certifications": ["Cert 1 - Org 1", "Cert 2 - Org 2", "Cert 3 - Org 3"],
  "hobbies": ["Hobby 1", "Hobby 2"]
}}

Write ENTIRELY in {language}. Use professional {language} terminology. 
- Use EXACTLY MM/YYYY - MM/YYYY format for all dates.
- {bullet_instruction}
- CRITICAL: Count the exact number of bullets for each experience block in the original resume. You MUST output the EXACT SAME NUMBER of bullets for that block in the generated JSON. Do NOT summarize 4 bullets into 2. Output 4 bullets.
- Group skills logically into categories, ONE string per category formatting explicitly like "Category Name: Skill 1, Skill 2".
- Do NOT include dates in certifications, just return a simple list of names and organizations.
Return valid JSON ONLY.""",
                expected_output=f"Output only valid JSON following the schema, written in {language}.",
                agent=writer,
                context=[task_kpi]
            )
            
            crew = Crew(
                agents=[analyzer, writer], 
                tasks=[task_kpi, task_tailor], 
                verbose=False, 
                memory=False
            )
            
            if progress_callback:
                progress_callback("Processing...")
            
            result = crew.kickoff()
            
            scores = None
            if result.tasks_output and len(result.tasks_output) > 0:
                scores = self._parse_scores(result.tasks_output[0].raw)
            
            raw_output = str(result.tasks_output[1].raw)
            if "```json" in raw_output:
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_output, re.DOTALL)
                if json_match:
                    raw_output = json_match.group(1)
            
            try:
                final_json = json.loads(raw_output)
            except Exception as e:
                logger.error(f"Failed to parse AI output into JSON: {raw_output}. Error: {str(e)}")
                # Provide a hard fallback if JSON parsing fails to avoid breaking UI strictly
                final_json = {
                    "name": target_role,
                    "title": "Raw Output Generator",
                    "summary": raw_output[:300] + "...",
                    "skills": [],
                    "experience": [],
                    "education": [],
                    "certifications": [],
                    "hobbies": []
                }

            return {
                'success': True,
                'scores': scores,
                'tailored_resume': final_json,
                'raw_markdown': raw_output
            }
            
        except Exception as e:
            logger.error(f"Analysis error: {str(e)}")
            return {
                'scores': None,
                'tailored_resume': None,
                'success': False,
                'error': str(e)
            }

# --- SECTION 4: STREAMLIT UI ---
def init_session_state():
    if 'analysis_complete' not in st.session_state:
        st.session_state.analysis_complete = False
    if 'result' not in st.session_state:
        st.session_state.result = None
    if 'job_description' not in st.session_state:
        st.session_state.job_description = ""
    if 'selected_template' not in st.session_state:
        st.session_state.selected_template = "ATS Native (FPDF)"
    if 'pdf_bytes' not in st.session_state:
        st.session_state.pdf_bytes = None

def main():
    st.set_page_config(
        page_title="AI Resume Intelligence", 
        layout="wide",
        page_icon="🎯"
    )
    
    init_session_state()
    
    st.title("🎯 AI Resume Intelligence Platform")
    st.markdown("*Professional resume with categorized skills structure*")
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        if st.button("🔄 Reset Application", use_container_width=True):
            st.session_state.clear()
            st.rerun()
            
        st.markdown("---")
        st.subheader("📄 Upload Resume")
        uploaded_file = st.file_uploader(
            "Upload your current resume (PDF)", 
            type="pdf",
            help=f"Maximum file size: {MAX_PDF_SIZE_MB}MB"
        )
        
        if uploaded_file:
            st.success(f"✓ {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)")
        
        st.markdown("---")
        st.subheader("🎨 Template & Styling")
        st.info("✓ Using ATS Native (FPDF) Template")
        
        theme_color = st.color_picker("Section Header Color", value="#2C3E50", help="Choose a custom color for section titles and your name.")
        
        st.markdown("---")
        st.subheader("🌍 Language & Role")
        
        out_lang = st.selectbox(
            "Output Language",
            options=list(SUPPORTED_LANGUAGES.keys()),
            index=1
        )
        
        role_options = [
            "Data Scientist",
            "Data Analyst",
            "Machine Learning Engineer",
            "Data Engineer",
            "AI Engineer",
            "Business Intelligence Analyst",
            "Software Engineer",
            "Other (Specify below)"
        ]
        
        selected_role = st.selectbox(
            "Target Role",
            options=role_options,
            index=0
        )
        
        target_role = selected_role
        if selected_role == "Other (Specify below)":
            target_role = st.text_input(
                "Specify Target Role",
                placeholder="e.g., Cloud Architect"
            )
        
        custom_skills = st.text_area(
            "Priority Keywords",
            placeholder="e.g., Machine Learning, Python, TensorFlow",
            height=100
        )
        
        verbosity_level = st.selectbox(
            "Bullet Detail Level",
            options=["Compact", "Medium", "Detailed"],
            index=0,
            help="Determine how verbose the AI should make your experience bullet points."
        )
    
    # Main Area
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("🔗 Job Information")
        
        input_method = st.radio(
            "Job description source:",
            ["Paste Job URL", "Paste Job Description"],
            horizontal=True
        )
        
        if input_method == "Paste Job URL":
            job_url = st.text_input("Job Posting URL", placeholder="https://...")
            
            if job_url and st.button("🔍 Fetch", type="secondary"):
                with st.spinner("Fetching..."):
                    success, content = JobScraper.fetch_job_description(job_url)
                    if success:
                        st.session_state.job_description = content
                        st.success("✓ Fetched!")
                        st.text_area("Preview:", content[:500] + "...", height=150, disabled=True)
                    else:
                        st.error(f"❌ {content}")
        else:
            job_description_input = st.text_area(
                "Job Description",
                placeholder="Paste full job description...",
                height=300
            )
            if job_description_input:
                st.session_state.job_description = job_description_input
    
    with col2:
        st.subheader("🚀 Generate")
        
        if uploaded_file and target_role and st.session_state.job_description:
            st.success("✓ Ready")
            ready_to_process = True
        else:
            missing = []
            if not uploaded_file:
                missing.append("Resume PDF")
            if not target_role:
                missing.append("Target Role")
            if not st.session_state.job_description:
                missing.append("Job Description")
            st.warning(f"⚠️ Missing: {', '.join(missing)}")
            ready_to_process = False
        
        st.markdown("---")
        
        if st.button(
            f"🎯 Generate {st.session_state.selected_template} Resume", 
            type="primary", 
            disabled=not ready_to_process,
            use_container_width=True
        ):
            is_valid, error_msg = InputValidator.validate_pdf(uploaded_file)
            if not is_valid:
                st.error(f"❌ {error_msg}")
                return
            
            is_valid, error_msg = InputValidator.validate_inputs(
                target_role, 
                st.session_state.job_description
            )
            if not is_valid:
                st.error(f"❌ {error_msg}")
                return
            
            status_placeholder = st.empty()
            
            try:
                status_placeholder.info("🔧 Initializing...")
                bot = ResumeIntelligence(uploaded_file)
                
                def update_progress(msg):
                    status_placeholder.info(f"⚙️ {msg}")
                
                template_info = CV_TEMPLATES[st.session_state.selected_template]
                
                result = bot.run_analysis(
                    st.session_state.job_description,
                    target_role,
                    custom_skills,
                    out_lang,
                    template_info['style'],
                    verbosity=verbosity_level,
                    progress_callback=update_progress
                )
                
                if result['success']:
                    st.session_state.result = result
                    st.session_state.analysis_complete = True
                    status_placeholder.success("✅ Complete!")
                    
                    with st.spinner("Generating Native ATS PDF..."):
                        try:
                            pdf_bytes = FpdfGenerator.generate_pdf(result['tailored_resume'], theme_color_hex=theme_color)
                            if pdf_bytes:
                                st.session_state.pdf_bytes = pdf_bytes
                                st.success("✅ Professional ATS-compliant PDF generated instantly!")
                            else:
                                st.error("❌ Failed to generate PDF.")
                        except Exception as e:
                            st.error(f"❌ Generation failed. (is fpdf installed?) Error: {str(e)}")
                else:
                    st.error(f"❌ Failed: {result.get('error', 'Unknown')}")
                    
            except ValueError as e:
                st.error(f"❌ {str(e)}")
            except Exception as e:
                logger.error(f"Error: {str(e)}")
                st.error(f"❌ Error occurred")
    
    # Results
    if st.session_state.analysis_complete and st.session_state.result:
        st.markdown("---")
        st.header("📊 Results")
        
        result = st.session_state.result
        
        if result['scores']:
            st.subheader("📈 Scores")
            
            col1, col2, col3, col4 = st.columns(4)
            scores = result['scores']
            
            def get_score_color(score):
                return "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
            
            with col1:
                score = scores.get('overall', 0)
                st.metric("Overall", f"{score}%")
                st.caption(f"{get_score_color(score)}")
            
            with col2:
                score = scores.get('content', 0)
                st.metric("Content", f"{score}%")
                st.caption(f"{get_score_color(score)}")
            
            with col3:
                score = scores.get('ats', 0)
                st.metric("ATS", f"{score}%")
                st.caption(f"{get_score_color(score)}")
            
            with col4:
                score = scores.get('tailoring', 0)
                st.metric("Tailoring", f"{score}%")
                st.caption(f"{get_score_color(score)}")
            
            st.markdown("---")
        
        st.subheader(f"📄 Your Resume ({out_lang})")
        
        tab1, tab2 = st.tabs(["📝 Content Preview", "📥 Download"])
        
        with tab1:
            st.json(result['tailored_resume'])
        
        with tab2:
            st.markdown("### Download Options")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if 'pdf_bytes' in st.session_state and st.session_state.pdf_bytes:
                    st.download_button(
                        label="📥 Download PDF (ATS Optimized)",
                        data=st.session_state.pdf_bytes,
                        file_name=f"Resume_{target_role.replace(' ', '_')}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        type="primary"
                    )
                    st.caption("✨ Native 1-Column Format")
                else:
                    st.warning("PDF compilation failed")

            with col2:
                st.download_button(
                    label="📥 Raw JSON Data",
                    data=result['raw_markdown'],
                    file_name=f"Resume_{target_role.replace(' ', '_')}_raw.json",
                    mime="application/json",
                    use_container_width=True
                )
                st.caption("📝 Base AI Output structure")
            
            st.success("✅ Resume generation complete!")
            st.info(f"💡 Language: {out_lang}")
        
        if st.button("🔄 New Resume", use_container_width=True):
            st.session_state.analysis_complete = False
            st.session_state.result = None
            st.session_state.job_description = ""
            st.session_state.pdf_bytes = None
            st.session_state.latex_bytes = None
            st.rerun()

    st.markdown("---")
    st.caption("🤖 AI-Powered Resume Intelligence")

if __name__ == "__main__":
    main()