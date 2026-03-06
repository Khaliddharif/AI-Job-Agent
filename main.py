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

# CV TEMPLATE - Using your custom structure
CV_TEMPLATES = {
    "Professional Data/AI": {
        "description": "Clean format with categorized skills - Data & AI, Analytics, Business Intelligence",
        "color": "#2E5090",
        "style": "data_professional",
        "icon": "💼",
        "best_for": "Data Science, AI, Analytics roles"
    },
    "Executive Technical": {
        "description": "Senior leadership template with technical expertise emphasis",
        "color": "#1A1A1A",
        "style": "executive_tech", 
        "icon": "👔",
        "best_for": "CTO, VP Engineering, Technical Director"
    },
    "Modern Technical": {
        "description": "Contemporary design for technical professionals",
        "color": "#27AE60",
        "style": "modern_tech",
        "icon": "💻",
        "best_for": "Software Engineers, DevOps, Cloud Architects"
    },
    "Compact Custom": {
        "description": "One-Page compact layout based on clean center-aligned header and inline skills",
        "color": "#333333",
        "style": "compact_custom", 
        "icon": "📄",
        "best_for": "Consultants, Analysts, 1-page limits"
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
    """Generates professional CV documents using docx-js with custom template"""
    
    @staticmethod
    def create_docx_from_markdown(markdown_content: str, template_style: str, 
                                   template_color: str) -> Optional[bytes]:
        """
        Convert markdown resume to professionally formatted DOCX with custom template
        Returns DOCX binary data
        """
        try:
            sections = TemplateGenerator._parse_markdown_resume(markdown_content)
            
            with tempfile.TemporaryDirectory() as temp_dir:
                js_code = TemplateGenerator._generate_custom_template_js(
                    sections, template_style, template_color, temp_dir
                )
                
                js_path = os.path.join(temp_dir, "generate_resume.js")
                with open(js_path, 'w', encoding='utf-8') as f:
                    f.write(js_code)
                
                env = os.environ.copy()
                env['NODE_PATH'] = os.path.join(os.getcwd(), 'node_modules')
                
                result = subprocess.run(
                    ['node', js_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=env,
                    cwd=os.getcwd()
                )
                
                if result.returncode != 0:
                    logger.error(f"Node.js error: {result.stderr}")
                    raise Exception(f"Node.js error: {result.stderr}")
                
                docx_output_path = os.path.join(temp_dir, "resume.docx")
                if os.path.exists(docx_output_path):
                    with open(docx_output_path, "rb") as f:
                        return f.read()
                
                raise Exception("resume.docx was not generated by Node.js script.")
            
        except Exception as e:
            logger.error(f"DOCX generation error: {str(e)}")
            raise e
    
    @staticmethod
    def _parse_markdown_resume(markdown: str) -> Dict:
        """Parse markdown resume into structured sections"""
        sections = {
            'name': '',
            'title': '',
            'contact': {
                'email': '',
                'phone': '',
                'city': '',
                'country': '',
                'linkedin': '',
                'portfolio': ''
            },
            'summary': '',
            'skills': {
                'data_ai': [],
                'analytics': [],
                'bi': [],
                'tech_stack': []
            },
            'languages': [],
            'experience': [],
            'education': [],
            'certifications': []
        }
        
        lines = markdown.split('\n')
        current_section = None
        current_item = {}
        skill_category = 'general'
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Detect email, phone, linkedin from text
            if '@' in line and not sections['contact']['email']:
                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', line)
                if email_match:
                    sections['contact']['email'] = email_match.group()
            
            if 'linkedin.com' in line.lower():
                linkedin_match = re.search(r'linkedin\.com/[\w/-]+', line, re.IGNORECASE)
                if linkedin_match:
                    sections['contact']['linkedin'] = linkedin_match.group()
            
            phone_patterns = [r'\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}', 
                            r'\d{3}[-.\s]?\d{3}[-.\s]?\d{4}']
            for pattern in phone_patterns:
                phone_match = re.search(pattern, line)
                if phone_match and not sections['contact']['phone']:
                    sections['contact']['phone'] = phone_match.group()
                    break
            
            # Detect sections
            if line.startswith('# ') or line.startswith('## '):
                section_title = line.lstrip('#').strip().lower()
                
                if any(x in section_title for x in ['summary', 'profile', 'about']):
                    current_section = 'summary'
                elif 'data' in section_title and 'ai' in section_title:
                    current_section = 'skills'
                    skill_category = 'data_ai'
                elif 'analytics' in section_title or 'engineering' in section_title:
                    current_section = 'skills'
                    skill_category = 'analytics'
                elif 'business' in section_title and 'intelligence' in section_title:
                    current_section = 'skills'
                    skill_category = 'bi'
                elif 'tech' in section_title and 'stack' in section_title:
                    current_section = 'skills'
                    skill_category = 'tech_stack'
                elif any(x in section_title for x in ['skill', 'competenc']):
                    current_section = 'skills'
                    skill_category = 'general'
                elif 'language' in section_title and 'programming' not in section_title:
                    current_section = 'languages'
                elif any(x in section_title for x in ['experience', 'employment', 'work']):
                    current_section = 'experience'
                elif any(x in section_title for x in ['education', 'academic']):
                    current_section = 'education'
                elif any(x in section_title for x in ['certification', 'certificate']):
                    current_section = 'certifications'
            
            # Extract name (usually first heading)
            elif line.startswith('#') and not sections['name']:
                sections['name'] = line.lstrip('#').strip()
            
            # Parse content
            elif current_section == 'summary':
                if not line.startswith('#'):
                    sections['summary'] += line + ' '
            
            elif current_section == 'skills':
                if line.startswith('-') or line.startswith('•') or line.startswith('*'):
                    skill = line.lstrip('-•*').strip()
                    if skill:
                        if skill_category == 'data_ai':
                            sections['skills']['data_ai'].append(skill)
                        elif skill_category == 'analytics':
                            sections['skills']['analytics'].append(skill)
                        elif skill_category == 'bi':
                            sections['skills']['bi'].append(skill)
                        elif skill_category == 'tech_stack':
                            sections['skills']['tech_stack'].append(skill)
            
            elif current_section == 'languages':
                if line.startswith('-') or line.startswith('•') or line.startswith('*'):
                    lang = line.lstrip('-•*').strip()
                    if lang:
                        sections['languages'].append(lang)
            
            elif current_section == 'experience':
                if line.startswith('###') or line.startswith('**'):
                    if current_item:
                        sections['experience'].append(current_item)
                    current_item = {'title': line.lstrip('#*').strip(), 'details': []}
                elif line.startswith('-') or line.startswith('•') or line.startswith('*'):
                    if current_item:
                        current_item['details'].append(line.lstrip('-•*').strip())
            
            elif current_section == 'education':
                if line.startswith('###') or line.startswith('**') or line.startswith('-') or line.startswith('*'):
                    edu = line.lstrip('#*-•').strip()
                    if edu:
                        sections['education'].append(edu)
            
            elif current_section == 'certifications':
                if line.startswith('-') or line.startswith('•') or line.startswith('*'):
                    cert = line.lstrip('-•*').strip()
                    if cert:
                        sections['certifications'].append(cert)
        
        # Add last experience item
        if current_item and current_section == 'experience':
            sections['experience'].append(current_item)
        
        return sections
    
    @staticmethod
    def _generate_custom_template_js(sections: Dict, style: str, color: str, temp_dir: str) -> str:
        """Generate JavaScript code using YOUR custom template structure"""
        
        color = color.lstrip('#')
        
        def js_escape(text):
            if not text:
                return ''
            return text.replace('\\', '\\\\').replace("'", "\\'").replace('\n', ' ').replace('"', '\\"')
        
        # Extract data
        name = js_escape(sections.get('name', 'Professional'))
        title = js_escape(sections.get('title', ''))
        contact = sections.get('contact', {})
        summary = js_escape(sections.get('summary', '').strip())
        
        # Skills
        skills = sections.get('skills', {})
        data_ai = [js_escape(s) for s in skills.get('data_ai', [])]
        analytics = [js_escape(s) for s in skills.get('analytics', [])]
        bi = [js_escape(s) for s in skills.get('bi', [])]
        tech_stack = [js_escape(s) for s in skills.get('tech_stack', [])]
        
        # If no categorized skills, distribute general skills
        if not data_ai and not analytics and not bi:
            all_skills = skills.get('general', [])
            if all_skills:
                third = len(all_skills) // 3
                data_ai = [js_escape(s) for s in all_skills[:third]]
                analytics = [js_escape(s) for s in all_skills[third:2*third]]
                bi = [js_escape(s) for s in all_skills[2*third:]]
        
        data_ai_js = ', '.join([f"'{s}'" for s in data_ai])
        analytics_js = ', '.join([f"'{s}'" for s in analytics])
        bi_js = ', '.join([f"'{s}'" for s in bi])
        tech_stack_js = ', '.join([f"'{s}'" for s in tech_stack])
        
        # Languages
        languages_js = ', '.join([f"'{js_escape(l)}'" for l in sections.get('languages', [])])
        
        # Experience
        experience_items = []
        for exp in sections.get('experience', []):
            title_text = js_escape(exp.get('title', ''))
            details = [js_escape(d) for d in exp.get('details', [])]
            details_js = ', '.join([f"'{d}'" for d in details])
            experience_items.append(f"{{'title': '{title_text}', 'details': [{details_js}]}}")
        experience_js = ', '.join(experience_items)
        
        # Education
        education_js = ', '.join([f"'{js_escape(e)}'" for e in sections.get('education', [])])
        
        # Certifications
        certs_js = ', '.join([f"'{js_escape(c)}'" for c in sections.get('certifications', [])])
        
        # Contact info
        email = js_escape(contact.get('email', ''))
        phone = js_escape(contact.get('phone', ''))
        city = js_escape(contact.get('city', ''))
        country = js_escape(contact.get('country', ''))
        linkedin = js_escape(contact.get('linkedin', ''))
        portfolio = js_escape(contact.get('portfolio', ''))
        
        docx_temp_js = os.path.join(temp_dir, "resume.docx").replace('\\', '\\\\')
        
        is_compact = style == 'compact_custom'
        
        # Adjust styles based on template
        # Base font sizes
        header1_size = 40 if is_compact else 52
        header2_size = 24 if is_compact else 28
        header3_size = 20 if is_compact else 24
        contact_size = 18 if is_compact else 20
        body_size = 20 if is_compact else 22
        
        # Spacing
        h1_after = 60 if is_compact else 100
        h2_before = 120 if is_compact else 240
        h2_after = 60 if is_compact else 120
        h3_before = 80 if is_compact else 120
        h3_after = 40 if is_compact else 60
        section_space = 120 if is_compact else 200
        item_space = 60 if is_compact else 120
        
        js_code = f'''
const {{ Document, Packer, Paragraph, TextRun, AlignmentType, HeadingLevel, LevelFormat }} = require('docx');
const fs = require('fs');

const primaryColor = '{color}';

const resumeData = {{
    name: '{name}',
    title: '{title}',
    contact: {{
        email: '{email}',
        phone: '{phone}',
        city: '{city}',
        country: '{country}',
        linkedin: '{linkedin}',
        portfolio: '{portfolio}'
    }},
    summary: '{summary}',
    skills: {{
        dataAI: [{data_ai_js}],
        analytics: [{analytics_js}],
        bi: [{bi_js}],
        techStack: [{tech_stack_js}]
    }},
    languages: [{languages_js}],
    experience: [{experience_js}],
    education: [{education_js}],
    certifications: [{certs_js}]
}};

const doc = new Document({{
    styles: {{
        default: {{
            document: {{ run: {{ font: "Arial", size: {body_size} }} }}
        }},
        paragraphStyles: [
            {{
                id: "Heading1",
                name: "Heading 1",
                run: {{ size: {header1_size}, bold: true, color: primaryColor, font: "Arial" }},
                paragraph: {{ spacing: {{ before: 0, after: {h1_after} }}, outlineLevel: 0, alignment: AlignmentType.CENTER }}
            }},
            {{
                id: "Heading2",
                name: "Heading 2",
                run: {{ size: {header2_size}, bold: true, color: primaryColor, font: "Arial" }},
                paragraph: {{ spacing: {{ before: {h2_before}, after: {h2_after} }}, outlineLevel: 1 }}
            }},
            {{
                id: "Heading3",
                name: "Heading 3",
                run: {{ size: {header3_size}, bold: true, font: "Arial" }},
                paragraph: {{ spacing: {{ before: {h3_before}, after: {h3_after} }}, outlineLevel: 2 }}
            }},
            {{
                id: "SubHeading",
                name: "Sub Heading",
                run: {{ size: {body_size}, bold: true, color: "111111", font: "Arial", italics: true }},
                paragraph: {{ spacing: {{ before: 60, after: 40 }} }}
            }}
        ]
    }},
    numbering: {{
        config: [
            {{
                reference: "bullets",
                levels: [
                    {{
                        level: 0,
                        format: LevelFormat.BULLET,
                        text: "•",
                        alignment: AlignmentType.LEFT,
                        style: {{ paragraph: {{ indent: {{ left: 720, hanging: 360 }} }} }}
                    }}
                ]
            }}
        ]
    }},
    sections: [{{
        properties: {{
            page: {{
                size: {{ width: 12240, height: 15840 }},
                margin: {{ top: 1000, right: 1000, bottom: 1000, left: 1000 }} // Narrower margins for compact
            }}
        }},
        children: [
            // NAME
            new Paragraph({{
                heading: HeadingLevel.HEADING_1,
                children: [new TextRun(resumeData.name)]
            }}),
            
            // CONTACT LINE
            new Paragraph({{
                alignment: AlignmentType.CENTER,
                spacing: {{ after: 120 }},
                children: [
                    new TextRun({{
                        text: [
                            resumeData.contact.city && resumeData.contact.country ? 
                                `${{resumeData.contact.city}}, ${{resumeData.contact.country}}` : '',
                            resumeData.contact.phone ? `📞 ${{resumeData.contact.phone}}` : '',
                            resumeData.contact.email ? `✉️ ${{resumeData.contact.email}}` : '',
                            resumeData.contact.portfolio ? `🔗 ${{resumeData.contact.portfolio}}` : '',
                            resumeData.contact.linkedin ? `🔗 ${{resumeData.contact.linkedin}}` : ''
                        ].filter(x => x).join(' | '),
                        size: {contact_size}
                    }})
                ]
            }}),
            
            // JOB TITLE (if available)
            ...(resumeData.title ? [
                new Paragraph({{
                    alignment: AlignmentType.CENTER,
                    spacing: {{ after: 240 }},
                    children: [
                        new TextRun({{
                            text: resumeData.title,
                            bold: true,
                            size: {header3_size},
                            color: primaryColor
                        }})
                    ]
                }})
            ] : []),
            
            // PROFESSIONAL SUMMARY
            new Paragraph({{
                heading: HeadingLevel.HEADING_2,
                children: [new TextRun("Professional Summary")]
            }}),
            new Paragraph({{
                children: [new TextRun(resumeData.summary)],
                spacing: {{ after: section_space }}
            }}),
            
            // CORE SKILLS SECTION
            new Paragraph({{
                heading: HeadingLevel.HEADING_2,
                children: [new TextRun("Core Skills")]
            }}),
            
            // Data & AI Skills
            ...(resumeData.skills.dataAI.length > 0 ? [
                new Paragraph({{
                    children: [
                        new TextRun({{ text: "Data & AI : ", bold: true }}),
                        new TextRun(resumeData.skills.dataAI.join(', '))
                    ],
                    spacing: {{ after: 60 }}
                }})
            ] : []),
            
            // Analytics & Engineering Skills
            ...(resumeData.skills.analytics.length > 0 ? [
                new Paragraph({{
                    children: [
                        new TextRun({{ text: "Analytics & Engineering : ", bold: true }}),
                        new TextRun(resumeData.skills.analytics.join(', '))
                    ],
                    spacing: {{ after: 60 }}
                }})
            ] : []),
            
            // Business Intelligence Skills
            ...(resumeData.skills.bi.length > 0 ? [
                new Paragraph({{
                    children: [
                        new TextRun({{ text: "Business Intelligence : ", bold: true }}),
                        new TextRun(resumeData.skills.bi.join(', '))
                    ],
                    spacing: {{ after: 60 }}
                }})
            ] : []),
            
            // Technical Stack
            ...(resumeData.skills.techStack.length > 0 ? [
                new Paragraph({{
                    children: [
                        new TextRun({{ text: "Technical Stack : ", bold: true }}),
                        new TextRun(resumeData.skills.techStack.join(', '))
                    ],
                    spacing: {{ after: 60 }}
                }})
            ] : []),
            
            // Languages
            ...(resumeData.languages.length > 0 ? [
                new Paragraph({{
                    children: [
                        new TextRun({{ text: "Languages : ", bold: true }}),
                        new TextRun(resumeData.languages.join(' | '))
                    ],
                    spacing: {{ after: section_space }}
                }})
            ] : []),
            
            // PROFESSIONAL EXPERIENCE
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
                            numbering: {{ reference: "bullets", level: 0 }},
                            children: [new TextRun(detail)]
                        }})
                    ),
                    new Paragraph({{ text: "", spacing: {{ after: item_space }} }})
                ]),
                new Paragraph({{ text: "", spacing: {{ after: section_space - item_space }} }})
            ] : []),
            
            // EDUCATION
            ...(resumeData.education.length > 0 ? [
                new Paragraph({{
                    heading: HeadingLevel.HEADING_2,
                    children: [new TextRun("Education")]
                }}),
                ...resumeData.education.map(edu =>
                    new Paragraph({{
                        children: [new TextRun({{ text: "• ", bold: true }}), new TextRun(edu)]
                    }})
                ),
                new Paragraph({{ text: "", spacing: {{ after: section_space }} }})
            ] : []),
            
            // CERTIFICATIONS
            ...(resumeData.certifications.length > 0 ? [
                new Paragraph({{
                    heading: HeadingLevel.HEADING_2,
                    children: [new TextRun("Certifications")]
                }}),
                ...resumeData.certifications.map(cert =>
                    new Paragraph({{
                        numbering: {{ reference: "bullets", level: 0 }},
                        children: [new TextRun(cert)]
                    }})
                )
            ] : [])
        ]
    }}]
}});

Packer.toBuffer(doc).then(buffer => {{
    fs.writeFileSync("{docx_temp_js}", buffer);
    console.log("Resume generated successfully!");
}}).catch(err => {{
    console.error("Error:", err);
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
            
            # Template specific prompt constraints
            is_compact = template_style == 'compact_custom'
            summary_instructions = "[MAXIMUM 3 short impactful sentences summarizing expertise and value proposition]" if is_compact else "[2-3 impactful sentences summarizing expertise and value proposition]"
            exp_instructions = "Limit to MAXIMUM 2-3 most critical achievements. KEEP THEM SHORT AND PUNCHY." if is_compact else "Include key achievements."
            
            task_tailor = Task(
                description=f"""Create tailored resume using this EXACT structure:

ORIGINAL: {self.resume_text}
JOB: {job_description}
ROLE: {target_role}
{skills_instruction}

CRITICAL STRUCTURE - Follow this template EXACTLY:

# [FULL NAME]
[City], [Country] 📞 [Phone] | ✉️ [Email] 🔗 [Portfolio] | 🔗 [LinkedIn]

[JOB TITLE]

## Professional Summary
{summary_instructions}

## Core Skills

### Data & AI
- [Skill 1]
- [Skill 2]

### Analytics & Engineering
- [Skill related to Analytics, Data Engineering]
- [Skill related to Analytics, Data Engineering]
- [Skill related to Analytics, Data Engineering]

### Business Intelligence
- [Skill related to BI, Reporting, Visualization]
- [Skill related to BI, Reporting, Visualization]
- [Skill related to BI, Reporting, Visualization]

### Technical Stack
- [Technology, Tool, Framework]
- [Technology, Tool, Framework]

### Languages
- [Language] ([Level])
- [Language] ([Level])

## Professional Experience

### [Company Name] — [Location]
[Job Title] | [Start Date] - [End Date]
- [Achievement with quantifiable metric showing impact]
- [Achievement with quantifiable metric showing impact]
({exp_instructions})

### [Company Name] — [Location]
[Job Title] | [Start Date] - [End Date]
- [Achievement with quantifiable result]
- [Achievement with quantifiable result]

## Education
- [Degree] — [Institution] ([Year] or [Start]-[End])
- [Degree] — [Institution] ([Year] or [Start]-[End])

## Certifications
- [Certification Name] - [Issuing Organization] ([Year])
- [Certification Name] - [Issuing Organization] ([Year])

Write ENTIRELY in {language}. Use professional {language} terminology. Include metrics and achievements. Match job keywords naturally.""",
                expected_output=f"Complete resume in Markdown following the EXACT template structure above, in {language}.",
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
    
    def save_pdf(self, markdown_content: str) -> Optional[bytes]:
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_path = os.path.join(temp_dir, "tailored_resume.pdf")
                pdf = MarkdownPdf(toc_level=2)
                pdf.add_section(Section(markdown_content, toc=False))
                pdf.save(output_path)
                with open(output_path, "rb") as f:
                    return f.read()
        except Exception as e:
            logger.error(f"PDF save error: {str(e)}")
            return None

# --- SECTION 4: STREAMLIT UI ---
def init_session_state():
    if 'analysis_complete' not in st.session_state:
        st.session_state.analysis_complete = False
    if 'result' not in st.session_state:
        st.session_state.result = None
    if 'job_description' not in st.session_state:
        st.session_state.job_description = ""
    if 'selected_template' not in st.session_state:
        st.session_state.selected_template = "Professional Data/AI"
    if 'pdf_bytes' not in st.session_state:
        st.session_state.pdf_bytes = None
    if 'docx_bytes' not in st.session_state:
        st.session_state.docx_bytes = None

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
        st.subheader("🎨 Template Style")
        
        for template_name, template_info in CV_TEMPLATES.items():
            is_selected = st.session_state.selected_template == template_name
            
            if st.button(
                f"{template_info['icon']} {template_name}",
                key=f"template_{template_name}",
                use_container_width=True,
                type="primary" if is_selected else "secondary"
            ):
                st.session_state.selected_template = template_name
            
            if is_selected:
                st.info(f"✓ {template_info['description']}")
        
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
                    progress_callback=update_progress
                )
                
                if result['success']:
                    st.session_state.result = result
                    st.session_state.analysis_complete = True
                    status_placeholder.success("✅ Complete!")
                    
                    with st.spinner("Generating PDF..."):
                        pdf_bytes = bot.save_pdf(
                            result['tailored_resume']
                        )
                        if pdf_bytes:
                            st.session_state.pdf_bytes = pdf_bytes
                            st.success("✅ Professional PDF created!")
                        else:
                            st.warning("⚠️ PDF generation failed")
                            
                    with st.spinner("Generating DOCX..."):
                        try:
                            docx_bytes = TemplateGenerator.create_docx_from_markdown(
                                result['tailored_resume'],
                                template_info['style'],
                                template_info['color']
                            )
                            if docx_bytes:
                                st.session_state.docx_bytes = docx_bytes
                                st.success("✅ Professional DOCX created!")
                        except Exception as e:
                            st.error(f"❌ DOCX generation failed: {str(e)}")
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
        
        template_name = st.session_state.selected_template
        st.subheader(f"📄 Your Resume ({out_lang})")
        
        tab1, tab2 = st.tabs(["📝 Preview", "📥 Download"])
        
        with tab1:
            st.markdown(result['tailored_resume'])
        
        with tab2:
            st.markdown("### Download Options")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if 'docx_bytes' in st.session_state and st.session_state.docx_bytes:
                    st.download_button(
                        label="📥 DOCX (Recommended)",
                        data=st.session_state.docx_bytes,
                        file_name=f"Resume_{target_role.replace(' ', '_')}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                        type="primary"
                    )
                    st.caption("✨ Custom template")
            
            with col2:
                if 'pdf_bytes' in st.session_state and st.session_state.pdf_bytes:
                    st.download_button(
                        label="📥 PDF",
                        data=st.session_state.pdf_bytes,
                        file_name=f"Resume_{target_role.replace(' ', '_')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                    st.caption("📄 Standard")
                else:
                    st.warning("PDF unavailable")
            
            with col3:
                st.download_button(
                    label="📥 Markdown",
                    data=result['tailored_resume'],
                    file_name=f"Resume_{target_role.replace(' ', '_')}.md",
                    mime="text/markdown",
                    use_container_width=True
                )
                st.caption("📝 Editable")
            
            st.success("✅ Resume ready!")
            st.info(f"💡 Template: {template_name} | Language: {out_lang}")
        
        if st.button("🔄 New Resume", use_container_width=True):
            st.session_state.analysis_complete = False
            st.session_state.result = None
            st.session_state.job_description = ""
            st.session_state.pdf_bytes = None
            st.session_state.docx_bytes = None
            st.rerun()

    st.markdown("---")
    st.caption("🤖 AI-Powered Resume Intelligence")

if __name__ == "__main__":
    main()