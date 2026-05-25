# 🧬 JobGenie AI Backend

> The intelligent, robust power engine driving **JobGenie AI**. Built with FastAPI, PostgreSQL, ChromaDB, and powered by Mistral AI, it handles secure authentication, resume parsing, ATS scoring, vector embeddings, and real-time AI mock interviews.

---

## 🌟 Key Features

*   **🔐 Secure Authentication**: OAuth2, password hashing via bcrypt, and JWT access/refresh token pairs.
*   **📄 Intelligent Resume Processing**: High-fidelity PDF text extraction and advanced AI-driven parser that extracts structured experience, skills, and metrics.
*   **🔍 Vector Search & Embedding**: Resume semantic embedding powered by ChromaDB for fast skill-gap and similarity analysis.
*   **🎙️ AI Mock Interviews**: Starts tailored interview sessions using Mistral LLM that automatically generates targeted technical questions and generates robust performance scorecards.
*   **📂 Resume Storage & Actionability**: Features dedicated endpoints to securely retrieve, download, and request deep career counselor elaborations of candidate resumes.

---

## 🛠️ Technology Stack

*   **Framework**: FastAPI (Asynchronous Python Web Framework)
*   **Database ORM**: SQLAlchemy 2.0 (Async/AioSQLite/PostgreSQL)
*   **Vector DB**: ChromaDB
*   **LLM Provider**: Mistral AI API
*   **Parser & PDF Processing**: pdfplumber
*   **Security & JWT**: python-jose, passlib (with bcrypt)
*   **ASGI Server**: Uvicorn

---

## 📂 Project Structure

```text
JobGenie-AI-main/
│
├── app/
│   ├── models/            # SQLAlchemy Database Models (User, Resume, Job, Interview)
│   ├── routers/           # FastAPI Route Handlers (auth, jobs, resume, interview)
│   ├── services/          # Business Logic (Mistral LLM, resume parser, embedding service)
│   ├── utils/             # Helper Functions (database sessions, utilities)
│   ├── config.py          # Pydantic Settings & Environment Configurations
│   ├── database.py        # Async Engine Setup & Session Maker
│   └── main.py            # FastAPI App Initialization & Middleware
│
├── tests/                 # Unit & Integration Tests
├── uploads/               # Local directory for uploaded resume PDFs
├── requirements.txt       # Python Dependencies
└── docker-compose.yml     # Containerization Configuration
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
Ensure you have **Python 3.10+** and **pip** installed on your machine.

### 2. Set Up Virtual Environment
Clone the repository and initialize a virtual environment:
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# On Windows (CMD):
.\venv\Scripts\activate.bat
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory:
```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/jobgenie
MISTRAL_API_KEY=your_mistral_api_key
SECRET_KEY=your_jwt_secret_key
UPLOAD_DIR=uploads
```

### 5. Launch the Server
Start the development server with hot-reload enabled:
```bash
uvicorn app.main:app --reload --port 8000
```
The backend API documentation will be available at:
*   Interactive Swagger UI: `http://localhost:8000/docs`
*   Redoc UI: `http://localhost:8000/redoc`

---

## 🔌 API Reference Highlights

### 🔐 Authentication (`/api/auth`)
*   `POST /api/auth/register` - Create a new user account.
*   `POST /api/auth/login` - Authenticate credentials and receive JWT tokens.
*   `GET /api/auth/me` - Retrieve current user profile.

### 📄 Resume Management (`/api/resume`)
*   `POST /api/resume/upload` - Upload and parse a new resume PDF.
*   `GET /api/resume/{resume_id}` - Retrieve parsed resume data and ATS scoring metrics.
*   `GET /api/resume/{resume_id}/download` - Download the uploaded original resume PDF file.
*   `POST /api/resume/{resume_id}/elaborate` - Request a comprehensive AI-powered resume summary and career counsel.

### 💼 Jobs & Placement (`/api/jobs`)
*   `POST /api/jobs` - Create a new job description.
*   `GET /api/jobs` - Fetch all available jobs.
*   `GET /api/jobs/{job_id}/gap-analysis/{resume_id}` - Run vector-based skill-gap analysis between a resume and job.

### 🎙️ Interviews (`/api/interview`)
*   `POST /api/interview/start` - Initiate an automated mock interview session.
*   `POST /api/interview/submit-answer` - Submit candidate answer for grading.
*   `GET /api/interview/{session_id}/scorecard` - Fetch final performance grading and structured scorecard feedback.