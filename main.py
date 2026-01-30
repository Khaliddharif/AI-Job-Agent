"""
AI Resume Intelligence Platform with Professional CV Templates
Improved UI with prominent template selection
"""

# CRITICAL: Set these BEFORE any other imports
import os
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["PYDANTIC_SKIP_VALIDATING_CORE_SCHEMAS"] = "true"
os.environ["CREWAI_TELEMETRY_ENABLED"] = "false"

import json
import re
import streamlit as st
from crewai import Agent, Task, Crew, LLM
from PyPDF2 import PdfReader
from markdown_pdf import MarkdownPdf, Section
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

# CV TEMPLATE DEFINITIONS
CV_TEMPLATES = {
    "Modern Professional": {
        "description": "Clean, ATS-friendly format with clear sections and professional styling",
        "color": "#2E5090",
        "style": "modern",
        "icon": "💼",
        "best_for": "Most corporate roles"
    },
    "Executive": {
        "description": "Sophisticated design for senior roles with emphasis on leadership",
        "color": "#1A1A1A",
        "style": "executive", 
        "icon": "👔",
        "best_for": "C-level, VP positions"
    },
    "Creative": {
        "description": "Eye-catching design for creative industries with visual impact",
        "color": "#E74C3C",
        "style": "creative",
        "icon": "🎨",
        "best_for": "Design, Marketing, Media"
    },
    "Technical": {
        "description": "Data-focused layout ideal for tech roles with skills emphasis",
        "color": "#27AE60",
        "style": "technical",
        "icon": "💻",
        "best_for": "Engineering, IT, Data"
    },
    "Minimalist": {
        "description": "Simple, elegant design focusing on content clarity",
        "color": "#34495E",
        "style": "minimalist",
        "icon": "📄",
        "best_for": "Academic, Research, Finance"
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

class TemplateGenerator:
    """Generates professional CV documents using docx-js"""
    
    @staticmethod
    def create_docx_from_markdown(markdown_content: str, template_style: str, 
                                   template_color: str, output_path: str = "resume.docx") -> bool:
        """
        Convert markdown resume to professionally formatted DOCX
        """
        try:
            # Parse markdown into structured data
            sections = TemplateGenerator._parse_markdown_resume(markdown_content)
            
# Create JavaScript file that generates the DOCX
            js_code = TemplateGenerator._generate_docx_js_code(
                sections, template_style, template_color
            )
            
            # Write JavaScript file - DYNAMIC PATH FIX
            js_path = os.path.join(os.getcwd(), "generate_resume.js") 
            with open(js_path, 'w', encoding='utf-8') as f:
                f.write(js_code)
            
            # Execute with Node.js
            result = subprocess.run(
                ['node', js_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"Node.js error: {result.stderr}")
                return False
            
            # Move generated file to output path - DYNAMIC PATH FIX
            generated_file = os.path.join(os.getcwd(), "resume.docx")
            if os.path.exists(generated_file):
                # If a file already exists at output_path, remove it first to avoid error
                if os.path.exists(output_path):
                    os.remove(output_path)
                os.rename(generated_file, output_path)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"DOCX generation error: {str(e)}")
            return False
    
    @staticmethod
    def _parse_markdown_resume(markdown: str) -> Dict:
        """Parse markdown resume into structured sections"""
        sections = {
            'name': '',
            'contact': {},
            'summary': '',
            'skills': [],
            'experience': [],
            'education': [],
            'certifications': []
        }
        
        lines = markdown.split('\n')
        current_section = None
        current_item = {}
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Detect sections
            if line.startswith('# ') or line.startswith('## '):
                section_title = line.lstrip('#').strip().lower()
                
                if any(x in section_title for x in ['summary', 'profile', 'about']):
                    current_section = 'summary'
                elif any(x in section_title for x in ['skill', 'competenc']):
                    current_section = 'skills'
                elif any(x in section_title for x in ['experience', 'employment', 'work']):
                    current_section = 'experience'
                elif any(x in section_title for x in ['education', 'academic']):
                    current_section = 'education'
                elif any(x in section_title for x in ['certification', 'certificate']):
                    current_section = 'certifications'
            
            # Extract name (usually first heading)
            elif line.startswith('#') and not sections['name']:
                sections['name'] = line.lstrip('#').strip()
            
            # Parse content based on current section
            elif current_section == 'summary':
                if not line.startswith('#'):
                    sections['summary'] += line + ' '
            
            elif current_section == 'skills':
                if line.startswith('-') or line.startswith('•'):
                    skill = line.lstrip('-•').strip()
                    if skill:
                        sections['skills'].append(skill)
            
            elif current_section == 'experience':
                if line.startswith('###') or line.startswith('**'):
                    if current_item:
                        sections['experience'].append(current_item)
                    current_item = {'title': line.lstrip('#*').strip(), 'details': []}
                elif line.startswith('-') or line.startswith('•'):
                    if current_item:
                        current_item['details'].append(line.lstrip('-•').strip())
            
            elif current_section == 'education':
                if line.startswith('###') or line.startswith('**'):
                    sections['education'].append(line.lstrip('#*').strip())
        
        # Add last item
        if current_item and current_section == 'experience':
            sections['experience'].append(current_item)
        
        return sections
    
    @staticmethod
    def _generate_docx_js_code(sections: Dict, style: str, color: str) -> str:
        """Generate JavaScript code to create DOCX file"""
        
        # Convert color hex to RGB
        color = color.lstrip('#')
        
        # Escape strings for JavaScript
        def js_escape(text):
            if not text:
                return ''
            return text.replace('\\', '\\\\').replace("'", "\\'").replace('\n', ' ')
        
        name = js_escape(sections.get('name', 'Professional Resume'))
        summary = js_escape(sections.get('summary', '').strip())
        
        # Build skills list
        skills_js = ', '.join([f"'{js_escape(s)}'" for s in sections.get('skills', [])])
        
        # Build experience items
        experience_items = []
        for exp in sections.get('experience', []):
            title = js_escape(exp.get('title', ''))
            details = [js_escape(d) for d in exp.get('details', [])]
            details_js = ', '.join([f"'{d}'" for d in details])
            experience_items.append(f"{{'title': '{title}', 'details': [{details_js}]}}")
        experience_js = ', '.join(experience_items)
        
        # Build education items
        education_js = ', '.join([f"'{js_escape(e)}'" for e in sections.get('education', [])])
        
        # Template-specific styling
        header_size = 52 if style == 'executive' else 48 if style == 'modern' else 44
        accent_used = style in ['modern', 'creative', 'technical']
        
        js_code = f'''
const {{ Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        AlignmentType, WidthType, BorderStyle, HeadingLevel, LevelFormat }} = require('docx');
const fs = require('fs');

const primaryColor = '{color}';

// Resume data
const resumeData = {{
    name: '{name}',
    summary: '{summary}',
    skills: [{skills_js}],
    experience: [{experience_js}],
    education: [{education_js}]
}};

const doc = new Document({{
    styles: {{
        default: {{
            document: {{ run: {{ font: "Arial", size: 22 }} }}
        }},
        paragraphStyles: [
            {{
                id: "Heading1",
                name: "Heading 1",
                basedOn: "Normal",
                next: "Normal",
                run: {{ size: {header_size}, bold: true, color: primaryColor, font: "Arial" }},
                paragraph: {{ spacing: {{ before: 240, after: 120 }}, outlineLevel: 0 }}
            }},
            {{
                id: "Heading2",
                name: "Heading 2",
                basedOn: "Normal",
                next: "Normal",
                run: {{ size: 28, bold: true, color: "{color if accent_used else '000000'}", font: "Arial" }},
                paragraph: {{ spacing: {{ before: 200, after: 100 }}, outlineLevel: 1 }}
            }},
            {{
                id: "Heading3",
                name: "Heading 3",
                basedOn: "Normal",
                next: "Normal",
                run: {{ size: 24, bold: true, font: "Arial" }},
                paragraph: {{ spacing: {{ before: 120, after: 60 }}, outlineLevel: 2 }}
            }}
        ]
    }},
    numbering: {{
        config: [
            {{
                reference: "resume-bullets",
                levels: [
                    {{
                        level: 0,
                        format: LevelFormat.BULLET,
                        text: "•",
                        alignment: AlignmentType.LEFT,
                        style: {{
                            paragraph: {{
                                indent: {{ left: 720, hanging: 360 }}
                            }}
                        }}
                    }}
                ]
            }}
        ]
    }},
    sections: [{{
        properties: {{
            page: {{
                size: {{
                    width: 12240,
                    height: 15840
                }},
                margin: {{
                    top: 1440,
                    right: 1440,
                    bottom: 1440,
                    left: 1440
                }}
            }}
        }},
        children: [
            new Paragraph({{
                heading: HeadingLevel.HEADING_1,
                alignment: AlignmentType.CENTER,
                children: [
                    new TextRun(resumeData.name)
                ]
            }}),
            
            new Paragraph({{ text: "", spacing: {{ after: 120 }} }}),
            
            new Paragraph({{
                heading: HeadingLevel.HEADING_2,
                children: [new TextRun("Professional Summary")]
            }}),
            
            new Paragraph({{
                children: [new TextRun(resumeData.summary)],
                spacing: {{ after: 200 }}
            }}),
            
            ...(resumeData.skills.length > 0 ? [
                new Paragraph({{
                    heading: HeadingLevel.HEADING_2,
                    children: [new TextRun("Core Competencies")]
                }}),
                ...resumeData.skills.map(skill => 
                    new Paragraph({{
                        numbering: {{ reference: "resume-bullets", level: 0 }},
                        children: [new TextRun(skill)]
                    }})
                ),
                new Paragraph({{ text: "", spacing: {{ after: 200 }} }})
            ] : []),
            
            ...(resumeData.experience.length > 0 ? [
                new Paragraph({{
                    heading: HeadingLevel.HEADING_2,
                    children: [new TextRun("Professional Experience")]
                }}),
                ...resumeData.experience.flatMap(exp => [
                    new Paragraph({{
                        heading: HeadingLevel.HEADING_3,
                        children: [new TextRun(exp.title)]
                    }}),
                    ...exp.details.map(detail =>
                        new Paragraph({{
                            numbering: {{ reference: "resume-bullets", level: 0 }},
                            children: [new TextRun(detail)]
                        }})
                    ),
                    new Paragraph({{ text: "", spacing: {{ after: 120 }} }})
                ]),
                new Paragraph({{ text: "", spacing: {{ after: 200 }} }})
            ] : []),
            
            ...(resumeData.education.length > 0 ? [
                new Paragraph({{
                    heading: HeadingLevel.HEADING_2,
                    children: [new TextRun("Education")]
                }}),
                ...resumeData.education.map(edu =>
                    new Paragraph({{
                        numbering: {{ reference: "resume-bullets", level: 0 }},
                        children: [new TextRun(edu)]
                    }})
                )
            ] : [])
        ]
    }}]
}});

Packer.toBuffer(doc).then(buffer => {{
    fs.writeFileSync("resume.docx", buffer);
    console.log("Resume generated successfully!");
}}).catch(err => {{
    console.error("Error generating resume:", err);
    process.exit(1);
}});
'''
        
        return js_code

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
                    progress_callback=None) -> Dict:
        try:
            target_role = InputValidator.sanitize_text(target_role, 200)
            custom_skills = InputValidator.sanitize_text(custom_skills, 500)
            
            if progress_callback:
                progress_callback("Creating AI agents...")
            
            analyzer = Agent(
                role='ATS Resume Scorer',
                goal=f'Evaluate resume against job description for {target_role}.',
                backstory='Expert in ATS systems and recruitment analytics.',
                llm=self.llm,
                verbose=False
            )
            
            writer = Agent(
                role=f'Professional Resume Writer',
                goal=f'Create ATS-optimized resume in {language} for {target_role} with {template_style} style.',
                backstory=f'Award-winning resume writer expert in {language} and {template_style} design.',
                llm=self.llm,
                verbose=False
            )
            
            if progress_callback:
                progress_callback("Analyzing resume...")
            
            task_kpi = Task(
                description=f"""Analyze resume vs job requirements:

RESUME: {self.resume_text[:3000]}
JOB: {job_description[:2000]}
ROLE: {target_role}

Score (0-100): overall, content, ats, tailoring. Return JSON only.""",
                expected_output='JSON: overall, content, ats, tailoring (0-100)',
                agent=analyzer
            )
            
            if progress_callback:
                progress_callback(f"Tailoring resume with {template_style} template...")
            
            skills_instruction = f"\nPrioritize: {custom_skills}" if custom_skills else ""
            
            task_tailor = Task(
                description=f"""Create tailored resume:

ORIGINAL: {self.resume_text}
JOB: {job_description}
ROLE: {target_role}
TEMPLATE: {template_style}
{skills_instruction}

Requirements:
1. Write in {language}
2. Professional {language} terminology
3. {template_style} template style
4. ATS compatible
5. Quantified achievements
6. Natural keywords

Structure:
- Professional Summary
- Core Competencies
- Professional Experience
- Education
- Certifications

Return clean Markdown with ## headers.""",
                expected_output=f"Complete resume in Markdown, {language}, {template_style} optimized.",
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
            
            tailored_resume = result.raw if hasattr(result, 'raw') else str(result)
            
            return {
                'scores': scores,
                'tailored_resume': tailored_resume,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Analysis error: {str(e)}")
            return {
                'scores': None,
                'tailored_resume': None,
                'success': False,
                'error': str(e)
            }
    
    def save_pdf(self, markdown_content: str, output_path: str = "tailored_resume.pdf") -> bool:
        try:
            pdf = MarkdownPdf(toc_level=2)
            pdf.add_section(Section(markdown_content, toc=False))
            pdf.save(output_path)
            return True
        except Exception as e:
            logger.error(f"PDF save error: {str(e)}")
            return False

# --- SECTION 4: STREAMLIT UI ---
def init_session_state():
    if 'analysis_complete' not in st.session_state:
        st.session_state.analysis_complete = False
    if 'result' not in st.session_state:
        st.session_state.result = None
    if 'job_description' not in st.session_state:
        st.session_state.job_description = ""
    if 'selected_template' not in st.session_state:
        st.session_state.selected_template = "Modern Professional"

def main():
    st.set_page_config(
        page_title="AI Resume Intelligence", 
        layout="wide",
        page_icon="🎯"
    )
    
    init_session_state()
    
    # Header
    st.title("🎯 AI Resume Intelligence Platform")
    st.markdown("*Professional resume optimization with customizable templates*")
    
    # Sidebar Configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
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
        st.subheader("🌍 Language & Role")
        
        out_lang = st.selectbox(
            "Output Language",
            options=list(SUPPORTED_LANGUAGES.keys()),
            index=1,
            help="Language for your resume"
        )
        
        target_role = st.text_input(
            "Target Role",
            placeholder="e.g., Senior Data Analyst",
            help="Job title you're applying for"
        )
        
        custom_skills = st.text_area(
            "Priority Keywords (Optional)",
            placeholder="e.g., Python, SQL, Tableau",
            help="Skills to emphasize",
            height=100
        )
    
    # MAIN AREA - Template Selection (PROMINENT)
    st.markdown("---")
    st.header("🎨 Choose Your Resume Template")
    st.markdown("*Select a professional template that matches your industry and role*")
    
    # Display templates in grid
    cols = st.columns(5)
    
    for idx, (template_name, template_info) in enumerate(CV_TEMPLATES.items()):
        with cols[idx]:
            is_selected = st.session_state.selected_template == template_name
            
            # Create card-like button
            button_type = "primary" if is_selected else "secondary"
            
            if st.button(
                f"{template_info['icon']}\n\n**{template_name}**",
                key=f"btn_{template_name}",
                use_container_width=True,
                type=button_type
            ):
                st.session_state.selected_template = template_name
                st.rerun()
            
            # Show details for selected template
            if is_selected:
                st.success("✓ Selected")
                
            # Show color indicator
            st.markdown(
                f"<div style='background-color: {template_info['color']}; "
                f"height: 20px; border-radius: 5px; margin: 5px 0;'></div>",
                unsafe_allow_html=True
            )
            
            st.caption(f"**Best for:** {template_info['best_for']}")
            st.caption(template_info['description'][:60] + "...")
    
    # Show selected template details
    if st.session_state.selected_template:
        selected = CV_TEMPLATES[st.session_state.selected_template]
        st.info(f"**Selected Template:** {selected['icon']} {st.session_state.selected_template} - {selected['description']}")
    
    st.markdown("---")
    
    # Job Information and Actions
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("🔗 Job Information")
        
        input_method = st.radio(
            "How would you like to provide the job description?",
            ["Paste Job URL", "Paste Job Description"],
            horizontal=True
        )
        
        if input_method == "Paste Job URL":
            job_url = st.text_input(
                "Job Posting URL",
                placeholder="https://example.com/job-posting"
            )
            
            if job_url and st.button("🔍 Fetch Job Description", type="secondary"):
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
                placeholder="Paste the complete job description here...",
                height=300
            )
            if job_description_input:
                st.session_state.job_description = job_description_input
    
    with col2:
        st.subheader("🚀 Actions")
        
        # Validation status
        if uploaded_file and target_role and st.session_state.job_description:
            st.success("✓ All required fields completed")
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
        
        # Process button
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
                    progress_callback=update_progress
                )
                
                if result['success']:
                    st.session_state.result = result
                    st.session_state.analysis_complete = True
                    status_placeholder.success("✅ Complete!")
                    
                    with st.spinner("Generating documents..."):
                        pdf_success = bot.save_pdf(
                            result['tailored_resume'], 
                            "tailored_resume.pdf"
                        )
                        
                        docx_success = TemplateGenerator.create_docx_from_markdown(
                            result['tailored_resume'],
                            template_info['style'],
                            template_info['color'],
                            "tailored_resume.docx"
                        )
                        
                        if docx_success:
                            st.success("✅ Professional DOCX generated!")
                        elif not pdf_success:
                            st.warning("⚠️ Document generation had issues")
                else:
                    st.error(f"❌ Failed: {result.get('error', 'Unknown error')}")
                    
            except ValueError as e:
                st.error(f"❌ {str(e)}")
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
                st.error(f"❌ Error occurred")
    
    # Results Section
    if st.session_state.analysis_complete and st.session_state.result:
        st.markdown("---")
        st.header("📊 Results")
        
        result = st.session_state.result
        
        # Display scores
        if result['scores']:
            st.subheader("📈 Resume Analysis Scores")
            
            col1, col2, col3, col4 = st.columns(4)
            scores = result['scores']
            
            def get_score_color(score):
                return "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
            
            with col1:
                score = scores.get('overall', 0)
                st.metric("Overall Match", f"{score}%")
                st.caption(f"{get_score_color(score)} Quality")
            
            with col2:
                score = scores.get('content', 0)
                st.metric("Content Quality", f"{score}%")
                st.caption(f"{get_score_color(score)} Rating")
            
            with col3:
                score = scores.get('ats', 0)
                st.metric("ATS Compatible", f"{score}%")
                st.caption(f"{get_score_color(score)} ATS")
            
            with col4:
                score = scores.get('tailoring', 0)
                st.metric("Job Alignment", f"{score}%")
                st.caption(f"{get_score_color(score)} Match")
            
            st.markdown("---")
        
        # Display resume
        template_name = st.session_state.selected_template
        st.subheader(f"📄 Your {template_name} Resume ({out_lang})")
        
        tab1, tab2 = st.tabs(["📝 Preview", "📥 Download"])
        
        with tab1:
            st.markdown(result['tailored_resume'])
        
        with tab2:
            st.markdown("### Download Your Professional Resume")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if os.path.exists("tailored_resume.docx"):
                    with open("tailored_resume.docx", "rb") as f:
                        st.download_button(
                            label="📥 Download DOCX (Recommended)",
                            data=f,
                            file_name=f"Resume_{target_role.replace(' ', '_')}_{template_name.replace(' ', '_')}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True,
                            type="primary"
                        )
                    st.caption("✨ Professional template")
            
            with col2:
                try:
                    with open("tailored_resume.pdf", "rb") as f:
                        st.download_button(
                            label="📥 Download PDF",
                            data=f,
                            file_name=f"Resume_{target_role.replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                    st.caption("📄 Standard format")
                except FileNotFoundError:
                    st.warning("PDF not available")
            
            with col3:
                st.download_button(
                    label="📥 Download Markdown",
                    data=result['tailored_resume'],
                    file_name=f"Resume_{target_role.replace(' ', '_')}.md",
                    mime="text/markdown",
                    use_container_width=True
                )
                st.caption("📝 Editable")
            
            st.success("✅ Your professional resume is ready!")
            st.info(f"💡 **Template:** {template_name} | **Language:** {out_lang}")
        
        if st.button("🔄 Create Another Resume", use_container_width=True):
            st.session_state.analysis_complete = False
            st.session_state.result = None
            st.session_state.job_description = ""
            st.rerun()

    st.markdown("---")
    st.caption("🤖 Powered by AI | CrewAI & Google Gemini")

if __name__ == "__main__":
    main()