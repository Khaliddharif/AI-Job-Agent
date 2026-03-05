# AI Job Agent

AI Job Agent is a powerful, AI-driven application built with Python and Streamlit that automatically parses your resume, compares it against a target job description, and generates a highly tailored, ATS-optimized version of your CV in both PDF and DOCX formats. 

Powered by **CrewAI** and the **Google Gemini API**, it utilizes specialized AI agents to rewrite, format, and enhance your resume based on modern hiring standards.

## ✨ Features
* **Intelligent Parsing:** Upload your existing resume (PDF) and provide a job description. The AI analyzes the gap between your current skills and the job requirements.
* **Auto-Tailoring:** Generates a completely rewritten, targeted resume designed to pass Applicant Tracking Systems (ATS).
* **Custom Layouts:** Includes custom formatting options like a condensed **Compact Custom (One-Page)** template for roles where brevity is key.
* **Multi-Format Export:** Downloads the generated resume instantly as an editable `DOCX`, a formatted standard `PDF`, or raw `Markdown`.
* **Zero-Footprint Generation:** Documents are generated securely in temporary memory and streamed directly to your browser—no leftover files cluttering your system.
* **Smart Scoring:** Provides a 0-100 score on your resume's Overall match, Content quality, ATS readiness, and Tailoring.

## 🚀 Getting Started

### Prerequisites
* Python 3.12 or newer (Note: Python 3.13+ may have compatibility issues with `crewai`)
* Node.js (Required for `docx-js` document generation)
* Google Gemini API Key

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Khaliddharif/AI-Job-Agent.git
   cd AI-Job-Agent
   ```

2. **Set up the virtual environment:**
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   npm install docx
   ```

4. **Configure API Keys:**
   Create a `.streamlit/secrets.toml` file in the root directory and add your Google API key:
   ```toml
   GEMINI_API_KEY = "your_google_gemini_api_key_here"
   ```

## 💻 Usage

Run the Streamlit application:
```bash
streamlit run main.py
```

1. Open the provided `localhost` URL in your browser.
2. Select your target language and desired CV template style.
3. Upload your current resume PDF.
4. Paste the job description you are applying for.
5. Click **"Analyze & Tailor Resume"** and let the AI agents do the work!

## 🛠️ Technology Stack
- **Frontend/UI:** Streamlit
- **AI Framework:** CrewAI, Google GenAI (Gemini)
- **Document Processing:** PyPDF2, docx (Node.js), markdown-pdf
- **Web Scraping (Optional parsing):** BeautifulSoup4, Requests
