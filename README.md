# ServiceNow AI Agent

A Proof-of-Concept AI-powered chatbot that interacts with ServiceNow through natural language commands. Built with Python (FastAPI, LangChain) and a React frontend.

![ServiceNow AI Agent](https://github.com/user-attachments/assets/7abdffb0-b5a0-49a4-b52d-5600bc24f093)

## 🚀 Features

- **Natural Language Interface**: Interact with ServiceNow using conversational language
- **Multi-Tool Agent**: Perform various ServiceNow operations through specialized tools
- **Real-time Processing**: Stream responses for better user experience
- **Session-based Memory**: Maintains conversation context within a session
- **ServiceNow Integration**: Full CRUD operations on incidents and knowledge base

## 🛠️ Supported Operations

- Get incident details with multiple output formats
- Search and create incidents
- Update incidents with work notes
- Resolve and close incidents
- Assign incidents to users or groups
- Search knowledge base articles
- Get metrics and analytics for assignment groups
- List incidents for users or groups
- Bulk operations on multiple incidents

## 🏗️ Architecture

### Backend (Python/FastAPI)
- **Framework**: FastAPI with async support
- **AI Engine**: LangChain with Azure OpenAI GPT-4o-mini
- **ServiceNow Integration**: REST API integration with custom tools
- **Authentication**: Environment-based credentials (.env)

### Frontend (React/Vite)
- **Framework**: React with Vite
- **UI**: Modern responsive interface
- **Real-time**: Server-Sent Events (SSE) for streaming responses

## 📦 Installation

### Prerequisites
- Python 3.8+
- Node.js 14+
- ServiceNow instance with API access
- Azure OpenAI API access

### Backend Setup

1. Clone the repository:
```bash
git clone https://github.com/vinay682000/service-now-langchain.git
cd servicenow-ai-agent
```

2. Set up Python environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Configure environment variables:
```bash
cp .env.example .env
```
Edit `.env` with your credentials:
```env
SERVICENOW_INSTANCE=https://your-instance.service-now.com
SERVICENOW_USERNAME=your_username
SERVICENOW_PASSWORD=your_password
AZURE_OPENAI_ENDPOINT=your_azure_openai_endpoint
AZURE_OPENAI_API_KEY=your_azure_openai_key
```

4. Run the backend:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

1. Navigate to frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Run the development server:
```bash
npm run dev
```

## 🐳 Docker Deployment

The project is Docker-ready. To build and run:

```bash
# Build the image
docker build -t servicenow-ai-agent .

# Run the container
docker run -p 8000:8000 --env-file .env servicenow-ai-agent
```

## 🧪 Testing

The project uses Pylint for code quality:

```bash
# Run pylint manually
pylint $(git ls-files '*.py')
```

GitHub Actions workflow is configured to run pylint on push.

## 📋 API Endpoints

- `POST /api/chat` - Main chat endpoint
- `POST /api/chat-stream` - Streaming chat endpoint
- Static file serving for the React frontend

## 🔧 Configuration

The agent supports various configuration options through environment variables and tool parameters:

- ServiceNow instance URL and credentials
- Azure OpenAI endpoint and API key
- Response formatting options
- Search limits and filters
- Session management settings

## 🤝 Contributing

This is a personal portfolio project. While not actively seeking contributions, feedback and suggestions are welcome through GitHub Issues.

### Code Quality
- Follow PEP 8 guidelines for Python code
- Use meaningful variable and function names
- Include comments for complex logic
- Ensure proper error handling

## 📄 License

This project is available for review as part of a professional portfolio. For usage rights, please contact the repository owner.

## ⚠️ Limitations

- Session data is not persisted (lost on refresh)
- No user authentication system
- Designed as a Proof-of-Concept
- Limited error handling for edge cases
- ServiceNow API rate limits may apply

## 🎯 Target Audience

This project is designed for:
- Potential employers reviewing my GitHub portfolio
- Developers interested in AI-agent implementations
- ServiceNow administrators exploring automation options
- AI enthusiasts learning about LangChain and tool-calling models

## 🔮 Future Enhancements

Potential improvements for a production version:
- Database persistence for chat history
- User authentication and authorization
- Enhanced error handling and retry mechanisms
- Additional ServiceNow table integrations
- Advanced analytics and reporting
- Mobile application version

## 📞 Support

For questions about this project, please open an issue in the GitHub repository or contact me through my GitHub profile.

---

**Note**: This is a portfolio project demonstrating integration of AI agents with enterprise systems. Not intended for production use without significant additional development.
