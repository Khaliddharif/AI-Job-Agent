# AI Job Agent

AI Job Agent is a lightning-fast, AI-driven application built with Python and Streamlit that automatically parses your resume, compares it against a target job description, and instantly generates a highly tailored, ATS-optimized version of your CV natively in a professional 1-page PDF format.

Powered directly by the **Google Gemini API**, it utilizes structured prompt engineering to logically categorize your skills, match job keywords, format dates precisely, and rewrite your experience into compact, metrics-driven bullet points for maximal recruiter success.

## ✨ Features
* **Intelligent Parsing:** Upload your existing resume (PDF) and provide a job description. The AI analyzes the gap between your current skills and the job requirements.
* **Auto-Tailoring:** Generates a completely targeted resume designed to pass Applicant Tracking Systems (ATS).
* **Native PDF Engine:** Uses lightweight Python library `fpdf2` to instantly generate single-column, strictly-formatted PDFs offline without the need for bloated LaTeX compilers.
* **Custom Styling:** Features UI dropdowns to choose exact bullet verbosity levels (Compact, Medium, Detailed) and an integrated color picker to perfectly match your brand aesthetic.
* **Automated Translations:** Instantly translate your dynamic CV headers, keywords, and body into 9+ distinct languages directly from the Streamlit UI.
* **Zero-Footprint Generation:** Documents are generated securely in temporary memory and streamed directly to your browser—no leftover files cluttering your system.

## 🚀 Getting Started

### Prerequisites
* Python 3.9+
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
2. Select your target language, header color, and bullet block verbosity.
3. Upload your current resume PDF.
4. Paste the job description you are applying for.
5. Click **"Generate ATS Native (FPDF) Resume"** and instantly download your PDF!

## 🛠️ Technology Stack
- **Frontend/UI:** Streamlit
- **AI Framework:** Google GenAI (Gemini / gemini-flash)
- **Document Processing:** PyPDF2 (Reading), fpdf2 (Writing)
- **Web Scraping:** BeautifulSoup4, Requests
