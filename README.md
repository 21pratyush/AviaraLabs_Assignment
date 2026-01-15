# 📜 Contract Intelligence API

An AI-powered system for contract ingestion, risk auditing, and RAG-based querying. Built with **FastAPI**, **Google Gemini**, and **Qdrant Vector Database**.


## 🏗 Project Overview
This platform automates the analysis of legal documents. It converts raw PDFs into structured data, identifies risky legal clauses with AI, and provides a conversational interface to "ask" questions about contract terms.

### Key Technical Features:
* **Docling Integration**: High-fidelity PDF parsing that preserves document structure.
* **Modular Webhook System**: Asynchronous callbacks with exponential backoff and database tracing.
* **SQLAlchemy 2.0**: Type-safe ORM utilizing the latest Python patterns.
* **Multi-Stage Docker**: Optimized production-ready containerization.

---

## 🚀 Quick Start

### 1. Clone & Navigate
```bash
git clone [https://github.com/21pratyush/AviaraLabs_Assignment.git](https://github.com/21pratyush/AviaraLabs_Assignment.git)
cd AviaraLabs_Assignment
```

### 2. Configure Environment
Create a .env file in the root directory and add your keys:
```bash
GEMINI_API_KEY=your_gemini_api_key_here
DATABASE_URL=sqlite:///./contracts.db
```

### 3. Launch Services
```bash
docker-compose up -d --build
```

## 🛠 Service Dashboard
```bash
API Docs: http://0.0.0.0:8000/docs#/
Qdrant Dashboard: http://localhost:6333/dashboard#/collections
```