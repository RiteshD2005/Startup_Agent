# Venture Agent 🚀
Venture Agent is a Streamlit-based AI startup workspace that brings together specialist agents to help plan and manage a startup. It includes strategy, marketing, legal, engineering, and finance agents, coordinated by a task orchestrator.
Features
- User registration and login
- Create and manage startup projects and tasks
- Specialist AI agents for strategy, marketing, legal, engineering, and finance
- Local LLM integration through Ollama
- Retrieval-Augmented Generation (RAG) with ChromaDB
- Web search support, including DuckDuckGo fallback and optional Tavily configuration
- Project dashboard and saved output artifacts
Tech Stack
Python · Streamlit · SQLAlchemy · LangChain · Ollama · ChromaDB · Pandas
Run Locally
1. Install Python (recommended: Python 3.11+).
2. Clone the repository:git clone https://github.com/RiteshD2005/Startup_Agent.git
   cd Startup_Agent
3. Create and activate a virtual environment:python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
4. Install dependencies:pip install -r requirements.txt
5. Install and start Ollama, and pull a model supported by the project's configuration.
6. Start the app:streamlit run app.py
Check utils/config.py for model and environment settings. Optional web search configuration may require a .env file with TAVILY_API_KEY.
Project Structure
- agents/ — specialist agents
- orchestrator/ — task planning and coordination
- pages/ — Streamlit dashboard and project pages
- database/ — database models and data operations
- data/knowledge/ — domain knowledge for agents
- utils/ and tools/ — LLM, retrieval, logging, artifact, and search utilities
Keep API keys and credentials out of source control. Review AI-generated legal and financial content before using it for important decisions.

Repository
GitHub: RiteshD2005/Startup_Agent
