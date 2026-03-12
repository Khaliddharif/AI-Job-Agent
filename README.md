# AI CV Tailor & Optimizer

**AI CV Tailor & Optimizer** is a fast, AI-powered application built with **Python** and **Streamlit** that helps job seekers automatically transform their existing resume into an **ATS-optimized CV tailored to a specific job description**.

The application analyzes your resume, compares it with the requirements of a target job, and generates a **professionally formatted 1-page PDF resume** designed to pass **Applicant Tracking Systems (ATS)** and attract recruiters.

Powered by the **Google Gemini API**, the system uses structured prompt engineering to intelligently match job keywords, reorganize skills, and rewrite experience into **concise, results-driven bullet points**.

---

# Features

### Intelligent Resume Analysis
Upload your existing resume (PDF) and provide a job description.  
The AI identifies gaps between your profile and the role requirements.

### Automatic CV Tailoring
Generates a **job-specific resume** optimized for ATS systems by aligning keywords, skills, and experience with the job description.

### Native PDF Generation
Uses the lightweight Python library **fpdf2** to generate clean, single-column resumes without relying on heavy LaTeX compilers.

### Custom Resume Styling
Customize the generated resume directly from the UI:

- Bullet verbosity levels: **Compact / Medium / Detailed**
- Custom **header color selection** for branding

### Multi-Language Support
Instantly translate your resume headers, keywords, and content into **9+ languages** directly from the Streamlit interface.

### Secure Zero-Footprint Generation
All documents are generated **in temporary memory** and streamed directly to your browser.  
No files are stored on disk.

### Application Security
Includes:

- **Cloudflare Turnstile** protection to prevent automated abuse
- Rate limiting: **10 resume generations per user every 30 minutes**

---

# Getting Started

## Prerequisites

- Python **3.9+**
- API keys for:
  - Google Gemini
  - Groq (backup inference provider)

---

# Installation

### 1. Clone the repository

```bash
git clone https://github.com/Khaliddharif/AI-Job-Agent.git
cd AI-Job-Agent
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

Activate the environment:

**Windows (PowerShell)**

```powershell
.\venv\Scripts\Activate.ps1
```

**Mac/Linux**

```bash
source venv/bin/activate
```

---

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

### 4. Configure API Keys

Create the following file:

```
.streamlit/secrets.toml
```

Add your API keys:

```toml
GEMINI_API_KEY = "your_google_gemini_api_key_here"
GROQ_API_KEY = "your_groq_api_key_here"
```

---

# Usage

Run the Streamlit application:

```bash
streamlit run main.py
```

Then:

1. Open the generated **localhost URL** in your browser
2. Select your **target language**
3. Choose **header color and bullet verbosity**
4. Upload your **current resume (PDF)**
5. Paste the **job description**
6. Click **"Generate ATS Native (FPDF) Resume"**
7. Download your **optimized PDF resume**

---

# 🛠 Technology Stack

### Frontend / UI
- Streamlit

### AI & NLP
- Google Gemini API
- Groq (fallback inference)

### Document Processing
- PyPDF2 — resume parsing
- fpdf2 — PDF generation

### Data Processing & Scraping
- BeautifulSoup4
- Requests

---

# Project Goal

The goal of **AI Job Agent** is to help job seekers **increase their chances of passing ATS filters** by automatically adapting resumes to match job descriptions.

Instead of manually rewriting resumes for every application, users can generate **optimized resumes in seconds**.

---

# Contributions

Contributions, ideas, and improvements are welcome!

If you'd like to contribute:

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

---

# 📄 License

This project is released under the **MIT License**.
