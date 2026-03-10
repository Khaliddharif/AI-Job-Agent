"""
AI Resume Intelligence Platform with Custom Professional Template
Your specific template structure with categorized skills and contact header
"""

# CRITICAL: Set these BEFORE any other imports
import os
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["PYDANTIC_SKIP_VALIDATING_CORE_SCHEMAS"] = "true"
os.environ["CREWAI_TELEMETRY_ENABLED"] = "false"

import json
import re
import time
import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
import requests
from bs4 import BeautifulSoup
from typing import Dict, Optional, Tuple, List
import logging
import subprocess
from translations import UI_TEXT

# Turnstile support
from turnstile_component import turnstile
from groq import Groq


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
def init_gemini():
    """Configure Gemini API"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
    return True

@st.cache_resource
def get_rate_limiter_store():
    return {} # Maps IP/Session to list of timestamps

def check_rate_limit(client_id: str, limit: int = 10, window_secs: int = 1800) -> bool:
    store = get_rate_limiter_store()
    now = time.time()
    if client_id not in store:
        store[client_id] = []
    
    # Remove old entries
    store[client_id] = [t for t in store[client_id] if now - t < window_secs]
    
    if len(store[client_id]) >= limit:
        return False
    return True

def add_rate_limit_usage(client_id: str):
    store = get_rate_limiter_store()
    if client_id not in store:
         store[client_id] = []
    store[client_id].append(time.time())

def verify_turnstile(token: str) -> bool:
    secret_key = st.secrets.get("TURNSTILE_SECRET_KEY", "")
    if not secret_key:
        return True # Fallback if secret is missing
    try:
        response = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": secret_key, "response": token},
            timeout=5
        )
        return response.json().get("success", False)
    except Exception as e:
        logger.error(f"Turnstile verification failed: {str(e)}")
        return False

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
    def generate_pdf(json_data: dict, theme_color_hex: str = "#2C3E50", profile_photo_bytes: bytes = None) -> bytes:
        from fpdf import FPDF
        from fpdf.enums import XPos, YPos
        import io

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
        
        text_x_start = pdf.l_margin
        text_align = 'C'
        image_size = 30 # 30x30 mm
        
        if profile_photo_bytes:
            img_io = io.BytesIO(profile_photo_bytes)
            # Add image to top left
            pdf.image(img_io, x=pdf.l_margin, y=pdf.t_margin, w=image_size, h=image_size)
            # Offset text over and align left
            text_x_start = pdf.l_margin + image_size + 5
            text_align = 'L'
            
        pdf.set_y(pdf.t_margin)
        pdf.set_font("helvetica", '', 14)
        pdf.set_text_color(127, 140, 141)
        pdf.set_x(text_x_start)
        pdf.cell(0, 8, name, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align=text_align)
        
        if title:
            pdf.set_font("helvetica", 'B', 22)
            pdf.set_text_color(*theme_rgb)
            pdf.set_x(text_x_start)
            pdf.cell(0, 10, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align=text_align)
            
        pdf.set_text_color(0, 0, 0)
        
        contact = json_data.get("contact", {})
        contact_str = " | ".join(filter(None, [
            safe_text(contact.get("email", "")), 
            safe_text(contact.get("phone", "")), 
            safe_text(contact.get("address", ""))
        ]))
        if contact_str:
            pdf.set_font("helvetica", '', 9)
            pdf.set_x(text_x_start)
            pdf.cell(0, 5, contact_str, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align=text_align)
            
        linkedin_url = json_data.get("contact", {}).get("linkedin", "")
        github_url = json_data.get("contact", {}).get("github", "")
        
        socials = []
        if linkedin_url: socials.append(("LinkedIn", linkedin_url))
        if github_url: socials.append(("GitHub", github_url))
        
        if socials:
            pdf.set_font("helvetica", '', 9)
            
            if profile_photo_bytes:
                pdf.set_x(text_x_start)
            else:
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
            
        # Ensure we don't start the summary block over the image if the header text is short!
        if profile_photo_bytes:
            current_y = pdf.get_y()
            min_y = pdf.t_margin + image_size + 2
            if current_y < min_y:
                pdf.set_y(min_y)
                
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
            
            edu_grouped = {}
            for edu in education:
                inst = safe_text(edu.get("institution", ""))
                if inst not in edu_grouped:
                    edu_grouped[inst] = []
                edu_grouped[inst].append(edu)
                
            for inst, degrees in edu_grouped.items():
                for edu in degrees:
                    degree = safe_text(edu.get("degree", ""))
                    dates = safe_text(edu.get("dates", ""))
                    
                    current_y = pdf.get_y()
                    pdf.set_font("helvetica", '', 9)
                    pdf.set_xy(pdf.w - pdf.r_margin - 60, current_y)
                    pdf.cell(60, 5, dates, align='R', new_x=XPos.LMARGIN, new_y=YPos.TOP)
                    
                    pdf.set_xy(pdf.l_margin, current_y)
                    pdf.set_font("helvetica", 'B', 9.5)
                    pdf.multi_cell(pdf.epw - 65, 5, degree, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    
                if inst:
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
        init_gemini()
    
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
                progress_callback("Analyzing resume match...")
            
            kpi_prompt = f"""Analyze resume vs job:

RESUME: {self.resume_text[:3000]}
JOB: {job_description[:2000]}
ROLE: {target_role}

Score (0-100): overall, content, ats, tailoring. Return JSON exactly like: {{"overall": 80, "content": 70, "ats": 60, "tailoring": 80}}"""

            # Try Gemini first, fallback to Groq
            try:
                model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
                kpi_res = model.generate_content(kpi_prompt)
                scores = self._parse_scores(kpi_res.text)
            except Exception as e:
                logger.warning(f"Gemini KPI generation failed, falling back to Groq: {str(e)}")
                if progress_callback: progress_callback("Gemini API overloaded. Switched to Backup LLM (Groq)...")
                try:
                    groq_client = Groq(api_key=st.secrets.get("GROQ_API_KEY", ""))
                    chat_completion = groq_client.chat.completions.create(
                        messages=[{"role": "user", "content": kpi_prompt}],
                        model="llama3-70b-8192",
                    )
                    scores = self._parse_scores(chat_completion.choices[0].message.content)
                except Exception as groq_e:
                    logger.error(f"Groq fallback also failed: {str(groq_e)}")
                    scores = {"overall": 0, "content": 0, "ats": 0, "tailoring": 0}
            
            if progress_callback:
                progress_callback(f"Tailoring resume with native template constraints...")
            
            skills_instruction = f"\nEmphasize: {custom_skills}" if custom_skills else ""
            
            if verbosity == "Compact":
                bullet_instruction = "Extremely compact and meaningful bullets (1 line max)."
            elif verbosity == "Medium":
                bullet_instruction = "Moderately detailed bullets with 1-2 metrics."
            else:
                bullet_instruction = "Highly detailed bullet points exploring context, actions, and results (multiple sentences ok)."
            
            if progress_callback:
                progress_callback(f"Writing ATS-friendly JSON output...")
            
            tailor_prompt = f"""You are an expert ATS resume optimizer and professional career writer.

Your task is to rewrite and optimize the candidate's resume so it aligns strongly with the provided Job Description and maximizes ATS keyword matching while keeping the resume truthful and professional.

INPUTS:
1. Job Description:
{job_description}

2. Candidate Resume:
{self.resume_text}

TARGET ROLE: {target_role}
{skills_instruction}

INSTRUCTIONS:

1. Analyze the Job Description carefully and extract all relevant keywords, including:
   - Technical skills, Tools, Programming languages, Methodologies, Soft skills, Industry terminology, and Role-specific responsibilities

2. Categorize the keywords into: Technical Keywords, Domain/Industry Keywords, Soft Skills / Business Skills, Tools / Technologies, and Languages.

3. Resume Optimization Rules:
TECHNICAL KEYWORDS & LANGUAGES: Add missing technical keywords and explicitly ensure spoken languages are separated into a "Languages" category within the SKILLS section. Group skills logically. You MUST ensure that "Soft Skills" is always the final category in the SKILLS section. Do not invent skills the candidate clearly does not possess.
NON-TECHNICAL / DOMAIN: Integrate them naturally into the EXPERIENCE bullet points. Rewrite bullet points to match the responsibilities and language used in the Job Description.
EXPERIENCE SECTION: Refine bullet points to reflect achievements aligned with the Job Description. Use action verbs and measurable impact. Ensure each bullet includes relevant keywords from the JD.
ATS OPTIMIZATION: Maintain a clean ATS-friendly structure. Ensure keyword density without keyword stuffing.
CONSISTENCY: Preserve truthful experience and do not fabricate roles or companies. Improve clarity, grammar, and professional tone.
FORMATTING: {bullet_instruction} Use exactly MM/YYYY - MM/YYYY format for all dates. Write ENTIRELY in {language}. 
CRITICAL: Count the exact number of bullets for each experience block in the original resume. You MUST output the EXACT SAME NUMBER of bullets for that block in the generated JSON. Do NOT summarize 4 bullets into 2. Output 4 bullets.

OUTPUT FORMAT:
Return ONLY valid JSON. Your response must match this schema exactly:

{{
  "name": "First Last",
  "title": "{target_role}",
  "contact": {{ "email": "user@example.com", "phone": "+1 234 567 8900", "address": "City, Country", "linkedin": "linkedin.com/in/...", "github": "github.com/..." }},
  "personal": {{ "citizenship": "Citizenship", "family": "Status" }},
  "section_headers": {{ "summary": "Translate 'Professional Summary' to {language}", "experience": "Translate 'Professional Experience' to {language}", "education": "Translate 'Education' to {language}", "skills": "Translate 'Skills' to {language}", "certifications": "Translate 'Certifications' to {language}" }},
  "languages": ["English", "French"],
  "summary": "3 impactful sentences summarizing expertise and value proposition",
  "skills": ["Languages: Lang A, Lang B", "Technical: Skill C, Skill D", "Soft Skills: Skill A, Skill B"],
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
    {{ "degree": "Degree", "institution": "University", "dates": "MM/YYYY - MM/YYYY" }}
  ],
  "certifications": ["Cert 1 - Org 1", "Cert 2 - Org 2"],
  "hobbies": ["Hobby 1", "Hobby 2"],
  "extracted_keywords": {{
      "Technical Skills": ["..."],
      "Tools & Technologies": ["..."],
      "Domain Keywords": ["..."],
      "Soft Skills": ["..."]
  }},
  "projected_scores": {{ "overall": 95, "content": 90, "ats": 95, "tailoring": 98 }},
  "ats_summary": "Brief explanation of how the resume was optimized to match the Job Description."
}}

Return valid JSON ONLY. Do not include markdown formatting or explanations outside the JSON."""

            if progress_callback:
                progress_callback("Processing with AI...")
            
            # Primary: Gemini
            raw_output = ""
            try:
                model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
                tailor_res = model.generate_content(tailor_prompt)
                raw_output = str(tailor_res.text)
            except Exception as e:
                logger.error(f"Gemini Tailoring failed: {str(e)}")
                if progress_callback: progress_callback("Gemini API overloaded. Switched to Backup LLM (Groq) to craft resume...")
                try:
                    groq_client = Groq(api_key=st.secrets.get("GROQ_API_KEY", ""))
                    chat_completion = groq_client.chat.completions.create(
                        messages=[{"role": "user", "content": tailor_prompt}],
                        model="llama3-70b-8192",
                    )
                    raw_output = str(chat_completion.choices[0].message.content)
                except Exception as groq_e:
                    raise ValueError(f"Both Primary and Backup AI Models failed. Please try again later. Error: {str(groq_e)}")
            
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
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'current_step' not in st.session_state:
        st.session_state.current_step = 1
    
    if 'uploaded_file' not in st.session_state:
        st.session_state.uploaded_file = None
    if 'theme_color' not in st.session_state:
        st.session_state.theme_color = "#2C3E50"
    if 'out_lang' not in st.session_state:
        st.session_state.out_lang = "English"
    if 'target_role' not in st.session_state:
        st.session_state.target_role = "Data Scientist"
    if 'custom_skills' not in st.session_state:
        st.session_state.custom_skills = ""
    if 'verbosity_level' not in st.session_state:
        st.session_state.verbosity_level = "Compact"
    if 'app_lang' not in st.session_state:
        st.session_state.app_lang = "English"
    if 'include_photo' not in st.session_state:
        st.session_state.include_photo = False
    if 'profile_photo' not in st.session_state:
        st.session_state.profile_photo = None

    # Identify client for rate limiting
    if 'client_id' not in st.session_state:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        ctx = get_script_run_ctx()
        st.session_state.client_id = ctx.session_id if ctx else "unknown_session"

def next_step():
    st.session_state.current_step += 1

def prev_step():
    st.session_state.current_step -= 1

def main():
    st.set_page_config(
        page_title="Intelligence CV Rewriter", 
        layout="wide",
        page_icon="🎯"
    )
    
    init_session_state()
    
    top_col1, top_col2, top_col3 = st.columns([6, 2, 2])
    with top_col2:
        st.session_state.app_lang = st.selectbox(
            "Language", 
            list(SUPPORTED_LANGUAGES.keys()), 
            index=list(SUPPORTED_LANGUAGES.keys()).index(st.session_state.app_lang),
            label_visibility="collapsed"
        )
    
    # Fallback to English if translation is missing
    t = UI_TEXT.get(st.session_state.app_lang, UI_TEXT["English"])
    
    with top_col3:
        if st.button(t["reset_app"], use_container_width=True):
            st.session_state.clear()
            st.rerun()
            
    st.title(t["title"])
    st.markdown(t["subtitle"])
    st.markdown(t["description"])
    st.markdown("---")
    
    # Progress Bar
    progress_cols = st.columns(4)
    steps = [t["step_profile"], t["step_job"], t["step_gen"], t["step_res"]]
    for i, col in enumerate(progress_cols):
        with col:
            if st.session_state.current_step > i + 1:
                st.markdown(f"**✅ {steps[i]}**")
            elif st.session_state.current_step == i + 1:
                st.markdown(f"**🔵 {steps[i]}**")
            else:
                st.markdown(f"<span style='color:gray'>⚪ {steps[i]}</span>", unsafe_allow_html=True)
                
    st.markdown("---")

    # ==========================================
    # STEP 1: Profile & Preferences
    # ==========================================
    if st.session_state.current_step == 1:
        st.header(t["step1_header"])
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader(t["upload_resume"])
            uploaded_file = st.file_uploader(
                t["upload_label"], 
                type="pdf",
                help=t["upload_help"].format(size=MAX_PDF_SIZE_MB)
            )
            if uploaded_file:
                st.session_state.uploaded_file = uploaded_file
                st.success(f"✓ {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)")
            elif st.session_state.uploaded_file is not None:
                st.success(f"✓ {st.session_state.uploaded_file.name} previously uploaded")
                uploaded_file = st.session_state.uploaded_file
                
            st.markdown("---")
            st.subheader(t["styling"])
            st.session_state.theme_color = st.color_picker(
                t["color_picker"], 
                value=st.session_state.theme_color, 
                help=t["color_help"]
            )
            
        with col2:
            st.subheader(t["role_details"])
            
            st.session_state.out_lang = st.selectbox(
                t["out_lang"],
                options=list(SUPPORTED_LANGUAGES.keys()),
                index=list(SUPPORTED_LANGUAGES.keys()).index(st.session_state.out_lang) if st.session_state.out_lang in SUPPORTED_LANGUAGES else 1
            )
            
            role_options = [
                "Data Scientist", "Data Analyst", "Machine Learning Engineer",
                "Data Engineer", "AI Engineer", "Business Intelligence Analyst",
                "Software Engineer", t["other_role"]
            ]
            
            current_role_index = 0
            if st.session_state.target_role in role_options:
                current_role_index = role_options.index(st.session_state.target_role)
            elif st.session_state.target_role != "Data Scientist":
                current_role_index = len(role_options) - 1 # Other
                
            selected_role = st.selectbox(t["target_role"], options=role_options, index=current_role_index)
            
            if selected_role == t["other_role"]:
                st.session_state.target_role = st.text_input(t["specify_role"], value=st.session_state.target_role if current_role_index == len(role_options) - 1 else "")
            else:
                st.session_state.target_role = selected_role
                
            st.session_state.custom_skills = st.text_area(
                t["priority_kw"],
                value=st.session_state.custom_skills,
                placeholder=t["priority_ph"],
                height=100
            )
            
            st.session_state.verbosity_level = st.selectbox(
                t["verbosity"],
                options=["Compact", "Medium", "Detailed"],
                index=["Compact", "Medium", "Detailed"].index(st.session_state.verbosity_level)
            )
            
            st.markdown("---")
            photo_choice = st.radio(
                t.get("photo_toggle", "Include Profile Photo?"),
                [t.get("photo_no", "No photo"), t.get("photo_yes", "Yes, with photo")],
                index=1 if st.session_state.include_photo else 0,
                horizontal=True
            )
            
            st.session_state.include_photo = (photo_choice == t.get("photo_yes", "Yes, with photo"))
            
            if st.session_state.include_photo:
                uploaded_photo = st.file_uploader(
                    t.get("photo_label", "Upload Profile Photo"),
                    type=["png", "jpg", "jpeg"]
                )
                if uploaded_photo:
                    st.session_state.profile_photo = uploaded_photo
                    st.success("✓ Image uploaded")
                elif st.session_state.profile_photo is not None:
                    st.success("✓ Image previously uploaded")
            else:
                st.session_state.profile_photo = None
            
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 1, 1])
        with col3:
            if st.button(t["next_step"], use_container_width=True, type="primary"):
                if not st.session_state.uploaded_file:
                    st.error(t["err_no_resume"])
                elif st.session_state.include_photo and not st.session_state.profile_photo:
                    st.error(t.get("err_no_photo", "Please upload a profile photo or select 'No photo'."))
                elif not st.session_state.target_role:
                    st.error(t["err_no_role"])
                else:
                    next_step()
                    st.rerun()

    # ==========================================
    # STEP 2: Job Description
    # ==========================================
    elif st.session_state.current_step == 2:
        st.header(t["step2_header"])
        st.write(t["jd_info"])
        
        input_method = st.radio(
            "Job description source:",
            ["Paste Job URL", "Paste Job Description"],
            horizontal=True
        )
        
        if input_method == "Paste Job URL":
            job_url = st.text_input("Job Posting URL", placeholder="https://...")
            
            if job_url and st.button("🔍 Fetch Job Description", type="secondary"):
                with st.spinner("Fetching..."):
                    success, content = JobScraper.fetch_job_description(job_url)
                    if success:
                        st.session_state.job_description = content
                        st.success("✓ Fetched successfully!")
                    else:
                        st.error(f"❌ {content}")
        else:
            job_description_input = st.text_area(
                "Job Description",
                value=st.session_state.job_description,
                placeholder="Paste full job description here... (Press Ctrl+Enter to apply)",
                height=300
            )
            if job_description_input:
                st.session_state.job_description = job_description_input
                
        if st.session_state.job_description:
            st.success("✓ Job description loaded.")
            with st.expander("Preview Current Job Description"):
                st.write(st.session_state.job_description[:500] + "...")
                
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.button(t["prev_step"], use_container_width=True):
                prev_step()
                st.rerun()
        with col3:
            if st.button(t["next_step"], use_container_width=True, type="primary"):
                if len(st.session_state.job_description.strip()) < 50:
                    st.error(t["err_no_jd"])
                else:
                    next_step()
                    st.rerun()

    # ==========================================
    # STEP 3: Generation
    # ==========================================
    elif st.session_state.current_step == 3:
        st.header(t["step3_header"])
        
        st.info(t["review_info"])
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### Profile Summary")
            st.write(f"**Target Role:** {st.session_state.target_role}")
            st.write(f"**Output Language:** {st.session_state.out_lang}")
            st.write(f"**Verbosity:** {st.session_state.verbosity_level}")
        with col2:
            st.markdown("### Job Summary")
            st.write(f"**Job Description Length:** {len(st.session_state.job_description)} {t.get('chars', 'characters')}")
            st.write(f"**Priority Keywords:** {st.session_state.custom_skills if st.session_state.custom_skills else 'None specified'}")
            
        st.markdown("---")
        
        # RATE LIMIT CHECK
        can_generate = check_rate_limit(st.session_state.client_id, limit=10, window_secs=1800)
        
        if not can_generate:
            st.error(t.get("rate_limit", "Rate limit exceeded. You can generate a maximum of 10 resumes per 30 minutes."))
        else:
            # CAPTCHA
            site_key = st.secrets.get("TURNSTILE_SITE_KEY", "")
            turnstile_token = None
            if site_key:
                st.markdown(f"**{t.get('captcha_verify', 'Please verify you are human to continue.')}**")
                turnstile_token = turnstile(sitekey=site_key)

        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.button(t["prev_step"], use_container_width=True):
                prev_step()
                st.rerun()
                
        with col2:
            btn_disabled = not can_generate or (bool(st.secrets.get("TURNSTILE_SITE_KEY", "")) and not turnstile_token)
            
            if st.button(
                t["gen_btn"],  
                type="primary", 
                use_container_width=True,
                disabled=btn_disabled
            ):
                if turnstile_token and not verify_turnstile(turnstile_token):
                    st.error("❌ CAPTCHA verification failed. Please try again.")
                    return
                is_valid, error_msg = InputValidator.validate_pdf(st.session_state.uploaded_file)
                if not is_valid:
                    st.error(f"❌ {error_msg}")
                    return
                
                is_valid, error_msg = InputValidator.validate_inputs(
                    st.session_state.target_role, 
                    st.session_state.job_description
                )
                if not is_valid:
                    st.error(f"❌ {error_msg}")
                    return
                
                status_placeholder = st.empty()
                
                try:
                    status_placeholder.info("🔧 Initializing AI Engine...")
                    bot = ResumeIntelligence(st.session_state.uploaded_file)
                    
                    def update_progress(msg):
                        status_placeholder.info(f"⚙️ {msg}")
                    
                    template_info = CV_TEMPLATES[st.session_state.selected_template]
                    
                    result = bot.run_analysis(
                        st.session_state.job_description,
                        st.session_state.target_role,
                        st.session_state.custom_skills,
                        st.session_state.out_lang,
                        template_info['style'],
                        verbosity=st.session_state.verbosity_level,
                        progress_callback=update_progress
                    )
                    
                    if result['success']:
                        add_rate_limit_usage(st.session_state.client_id)
                        st.session_state.result = result
                        st.session_state.analysis_complete = True
                        status_placeholder.success("✅ AI Analysis Complete!")
                        
                        with st.spinner("Compiling Professional PDF..."):
                            try:
                                photo_args = {}
                                if st.session_state.get('include_photo') and st.session_state.get('profile_photo'):
                                    photo_args['profile_photo_bytes'] = st.session_state.profile_photo.getvalue()
                                    
                                pdf_bytes = FpdfGenerator.generate_pdf(
                                    result['tailored_resume'], 
                                    theme_color_hex=st.session_state.theme_color,
                                    **photo_args
                                )
                                if pdf_bytes:
                                    st.session_state.pdf_bytes = pdf_bytes
                                    st.success("✅ PDF generated instantly!")
                                    # Move to results step automatically
                                    next_step()
                                    st.rerun()
                                else:
                                    st.error("❌ Failed to generate PDF.")
                            except Exception as e:
                                st.error(f"❌ Generation failed. Error: {str(e)}")
                    else:
                        st.error(f"❌ Failed: {result.get('error', 'Unknown')}")
                        
                except ValueError as e:
                    st.error(f"❌ {str(e)}")
                except Exception as e:
                    logger.error(f"Error: {str(e)}")
                    st.error(f"❌ Error occurred")
                    
    # ==========================================
    # STEP 4: Results & Refinement
    # ==========================================
    elif st.session_state.current_step == 4:
        st.header(t["step4_header"])
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            if st.button(t["back_gen"], use_container_width=True):
                prev_step()
                st.rerun()
        with col3:
            if st.button(t["start_over"], use_container_width=True):
                st.session_state.clear()
                st.rerun()
                
        if st.session_state.analysis_complete and st.session_state.result:
            st.markdown("---")
            
            result = st.session_state.result
            
            if result['scores']:
                st.subheader(t["kpi_header"])
                st.info(t["kpi_info"])
                
                col1, col2, col3, col4 = st.columns(4)
                old_scores = result['scores']
                new_scores = result['tailored_resume'].get('projected_scores', {})
                
                def get_score_color(score):
                    return "🟢" if int(score) >= 80 else "🟡" if int(score) >= 60 else "🔴"
                
                with col1:
                    o_score = old_scores.get('overall', 0)
                    n_score = new_scores.get('overall', o_score)
                    st.metric(t["overall"], f"{n_score}%", f"{n_score - o_score}%")
                    st.caption(t["orig"].format(score=o_score, color=get_score_color(o_score), n_color=get_score_color(n_score)))
                
                with col2:
                    o_score = old_scores.get('content', 0)
                    n_score = new_scores.get('content', o_score)
                    st.metric(t["content"], f"{n_score}%", f"{n_score - o_score}%")
                    st.caption(t["orig"].format(score=o_score, color=get_score_color(o_score), n_color=get_score_color(n_score)))
                
                with col3:
                    o_score = old_scores.get('ats', 0)
                    n_score = new_scores.get('ats', o_score)
                    st.metric(t["ats_comp"], f"{n_score}%", f"{n_score - o_score}%")
                    st.caption(t["orig"].format(score=o_score, color=get_score_color(o_score), n_color=get_score_color(n_score)))
                
                with col4:
                    o_score = old_scores.get('tailoring', 0)
                    n_score = new_scores.get('tailoring', o_score)
                    st.metric(t["job_tail"], f"{n_score}%", f"{n_score - o_score}%")
                    st.caption(t["orig"].format(score=o_score, color=get_score_color(o_score), n_color=get_score_color(n_score)))
                
                st.markdown("---")
            
            st.subheader(f"{t['gen_out']} ({st.session_state.out_lang})")
            
            tab1, tab2, tab3 = st.tabs([t["tab_pdf"], t["tab_data"], t["tab_dl"]])
            
            with tab1:
                if 'pdf_bytes' in st.session_state and st.session_state.pdf_bytes:
                    try:
                        import pypdfium2 as pdfium
                        pdf = pdfium.PdfDocument(st.session_state.pdf_bytes)
                        page = pdf[0]
                        # Use scale=2 for better resolution
                        pil_image = page.render(scale=2).to_pil()
                        st.image(pil_image, caption=t.get("pdf_preview_caption", "Preview of Page 1 (Download full PDF below)"), use_container_width=True)
                    except Exception as e:
                        logger.error(f"Failed to render PDF preview with pypdfium2: {str(e)}")
                        # Fallback to the old iframe method if pypdfium2 fails
                        import base64
                        base64_pdf = base64.b64encode(st.session_state.pdf_bytes).decode('utf-8')
                        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf"></iframe>'
                        st.markdown(pdf_display, unsafe_allow_html=True)
                        st.caption("Note: PDF preview iframe might be blocked by some browsers due to security policies.")
                else:
                    st.info(t["pdf_unavail"])
                    
            with tab2:
                st.markdown(t["ext_kw"])
                st.json(result['tailored_resume'].get('extracted_keywords', {}))
                st.markdown(t["ats_sum"])
                st.info(result['tailored_resume'].get('ats_summary', t["no_sum"]))
                st.markdown(t["full_cv"])
                st.json({k: v for k, v in result['tailored_resume'].items() if k not in ['extracted_keywords', 'ats_summary', 'projected_scores']})
            
            with tab3:
                st.markdown(t["dl_opt"])
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if 'pdf_bytes' in st.session_state and st.session_state.pdf_bytes:
                        st.download_button(
                            label=t["dl_pdf"],
                            data=st.session_state.pdf_bytes,
                            file_name=f"Resume_{st.session_state.target_role.replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                            type="primary"
                        )
                    else:
                        st.warning(t["pdf_fail"])

                with col2:
                    st.download_button(
                        label=t["dl_json"],
                        data=result['raw_markdown'],
                        file_name=f"Resume_{st.session_state.target_role.replace(' ', '_')}_raw.json",
                        mime="application/json",
                        use_container_width=True
                    )
                
            st.markdown("---")
            st.subheader(t["refine_hdr"])
            st.info(t["refine_info"])
            
            for msg in st.session_state.messages:
                st.chat_message(msg["role"]).write(msg["content"])
            
            if prompt := st.chat_input(t["refine_ph"]):
                st.session_state.messages.append({"role": "user", "content": prompt})
                st.chat_message("user").write(prompt)
                
                with st.spinner(t["refine_wait"]):
                    try:
                        model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
                        refine_prompt = f"""Update the following JSON resume based on the user request.
USER REQUEST: {prompt}

CURRENT RESUME JSON:
{json.dumps(result['tailored_resume'], indent=2)}

Return ONLY the updated valid JSON matching the exact same schema. Do not add markdown blocks or explanations."""

                        res = model.generate_content(refine_prompt)
                        raw_out = res.text
                        
                        if "```json" in raw_out:
                            import re
                            m = re.search(r'```json\s*(\{.*?\})\s*```', raw_out, re.DOTALL)
                            if m: raw_out = m.group(1)
                            
                        updated_json = json.loads(raw_out)
                        
                        st.session_state.result['tailored_resume'] = updated_json
                        st.session_state.pdf_bytes = FpdfGenerator.generate_pdf(updated_json, theme_color_hex=st.session_state.theme_color)
                        
                        st.session_state.messages.append({"role": "assistant", "content": t["refine_success"]})
                        st.rerun()
                    except Exception as e:
                        st.error(f"{t['refine_fail']} {str(e)}")
            
            if st.button(t["new_res"], use_container_width=True):
                st.session_state.clear()
                st.rerun()

    st.markdown("---")
    st.caption(t["footer"])

if __name__ == "__main__":
    main()
