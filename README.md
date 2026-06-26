# Contract Intelligence AI

An AI-powered contract analysis and management backend system. This project automates the tedious process of reviewing legal documents by extracting key metadata, identifying potential compliance risks, summarizing obligations, and providing an interactive chat interface to interrogate the contract using LLMs.

Built with a modern, asynchronous Python stack, this repository serves as a production-ready showcase of clean architecture, robust database management, and AI integration.

---

## Key Features

- **Automated Metadata Extraction:** Extracts titles, vendor names, values, currencies, and expiration dates from unstructured text.
- **Deep AI Analysis:** Leverages LLMs to generate structured data such as **Risk Assessments** and **Obligations Lists** stored directly as PostgreSQL JSON types.
- **Interactive Contract Chat:** Full conversational history tracking per contract, allowing users to ask context-aware questions about legal clauses.
- **Production-Ready DB Management:** Managed via SQLAlchemy (Declarative Base) and Alembic for seamless, automated database migrations.
- **Fully Dockerized:** Single-command local environment setup combining the API and PostgreSQL.

---

## Tech Stack

| Category | Technology |
| :--- | :--- |
| **Language** | Python 3.11+ |
| **Framework** | [FastAPI / Django - *Choose yours*] |
| **Database** | PostgreSQL |
| **ORM** | SQLAlchemy (Async) |
| **Migrations**| Alembic |
| **AI / LLM** | OpenAI API / LangChain |
| **DevOps** | Docker / Docker Compose |

---

## Core Architecture & Database Schema

The system uses a highly relational, optimized schema designed for historical persistence:

* **`Contract` Model:** Stores extracted parameters, full-text contents, and complex structures (Risks/Obligations) utilizing PostgreSQL's native `JSON` type for high-performance querying.
* **`ChatMessage` Model:** Handles full context retention with a `CASCADE` delete relationship tied back to parent contracts.

## ⚡ Getting Started (Local Development)

### Prerequisites
Make sure you have **Docker** and **Docker Compose** installed.

### 1. Environment Variables
Create a `.env` file in the root directory:
```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/contract_db
OPENAI_API_KEY=your_openai_api_key_here

## Technical Challenges Faced & Solved
The Alembic Auto-generation Metadata Desync
Challenge: During the iteration phase of adding JSON fields and contract text attributes, the Alembic migration environment failed to reflect local code changes, incorrectly issuing destructive drop_table operations on the production-ready schemas.

Solution: Diagnosed a metadata lifecycle bug inside env.py where SQLModel/SQLAlchemy core boundaries were conflicting. Re-architected the migration configuration to dynamically inspect and append the correct project PYTHONPATH and hook directly into the real Base.metadata registry. This ensured safe, incremental, and completely automated column-level updates (add_column).

## Author
Erfan Molaei

GitHub: @erfmollaey

LinkedIn: erfmollaey