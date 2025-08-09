# Megan Voice Assistant Backend

This repository is one of three components that make up the **Megan Voice Assistant Extension** project:

- **[Landing Page](link-to-landing-repo)** - Project website and documentation
- **[Browser Extension](link-to-extension-repo)** - Chrome extension frontend
- **[Backend API](link-to-this-repo)** - Server-side services and AI integration *(this repository)*

---

A comprehensive backend service for Megan, an intelligent voice assistant that provides browser automation, media control, calendar management, note-taking capabilities, and conversational AI features.

## Overview

This is the server-side component of the Megan Voice Assistant project. The backend provides RESTful API endpoints for voice processing, natural language understanding, and integration with various services including browser automation, media control, calendar management, and note-taking systems.

## Features

- **Voice Processing**: Speech-to-text and text-to-speech capabilities
- **Natural Language Understanding**: Intent recognition and conversational AI
- **Browser Automation**: Web search and browser control functionality
- **Media Management**: Video and audio control capabilities
- **Calendar Integration**: Event management and scheduling
- **Note System**: Digital note-taking and organization
- **Translation Services**: Multi-language text translation
- **Text Summarization**: AI-powered content summarization
- **Email Integration**: SMTP functionality for communication
- **Authentication**: Secure user management and access control

## Technology Stack

- **Framework**: FastAPI (Python)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Cache**: Redis for session management
- **Authentication**: JWT-based security
- **Voice Processing**: Whisper for speech recognition, ElevenLabs for text-to-speech
- **AI Services**: Gemini and OpenAI (Azure), Google Translate
- **Deployment**: Docker containerization

## WebSocket Endpoints

The application provides real-time communication through WebSocket connections:

- **Chat WebSocket**: `/chat/websocket` - Real-time chat functionality
- **Voice WebSocket**: `/websocket-voice` - Voice processing and streaming

Both endpoints require authentication via query parameter `token`.

## Project Structure

```
super-ex-back/
├── app/
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── security.py
│   │   └── dependencies/
│   │       ├── __init__.py
│   │       ├── utils.py
│   │       ├── voice.py
│   │       └── web.py
│   ├── routers/
│   │   ├── auth.py
│   │   ├── calendar.py
│   │   ├── chat.py
│   │   ├── note.py
│   │   ├── smtp.py
│   │   ├── tools.py
│   │   ├── translate.py
│   │   ├── user.py
│   │   └── voice.py
│   ├── services/
│   │   ├── summarize_service.py
│   │   └── voice/
│   │       ├── ai.py
│   │       ├── prompts.py
│   │       ├── speech.py
│   │       ├── web_search.py
│   │       └── agents/
│   │           ├── action_agent.py
│   │           ├── calendar_agent.py
│   │           ├── intent_agent.py
│   │           ├── media_agent.py
│   │           └── text_gen_agent.py
│   ├── main.py
│   ├── models.py
│   ├── schemas.py
│   ├── token_limit.py
│   └── redis_client.py
├── alembic/
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── alembic.ini
```

## Directory Descriptions

### Core Application (`app/`)
Main application package containing all business logic and API endpoints.

#### `app/core/`
Core configuration and infrastructure components:
- **`config.py`** - Application settings and environment configuration
- **`database.py`** - Database connection and session management
- **`security.py`** - Authentication, authorization, and security utilities
- **`dependencies/`** - Dependency injection modules for various services

#### `app/routers/`
API endpoint definitions organized by functionality:
- **`auth.py`** - User authentication and authorization endpoints
- **`calendar.py`** - Calendar management and event operations
- **`chat.py`** - Conversational AI and chat functionality
- **`note.py`** - Note creation, editing, and management
- **`smtp.py`** - Email sending and SMTP operations
- **`tools.py`** - Utility tools and helper functions
- **`translate.py`** - Text translation services
- **`user.py`** - User profile and account management
- **`voice.py`** - Voice processing and speech recognition

#### `app/services/`
Business logic and external service integrations:
- **`summarize_service.py`** - AI-powered text summarization
- **`voice/`** - Voice processing and AI agent services
  - **`ai.py`** - AI service integration and management
  - **`prompts.py`** - Prompt templates and management
  - **`speech.py`** - Speech processing utilities
  - **`web_search.py`** - Web search and information retrieval
  - **`agents/`** - Specialized AI agents for different tasks
    - **`action_agent.py`** - Action execution and automation
    - **`calendar_agent.py`** - Calendar operations and scheduling
    - **`intent_agent.py`** - Natural language intent recognition
    - **`media_agent.py`** - Media control and management
    - **`text_gen_agent.py`** - Text generation and processing

#### `app/` (root level files)
- **`main.py`** - FastAPI application entry point and configuration
- **`models.py`** - SQLAlchemy database models and schemas
- **`schemas.py`** - Pydantic data validation schemas
- **`token_limit.py`** - Token usage tracking and rate limiting
- **`redis_client.py`** - Redis connection and client setup

### Database and Migrations (`alembic/`)
Database schema management and version control:
- **`env.py`** - Alembic environment configuration
- **`versions/`** - Database migration scripts
- **`script.py.mako`** - Migration template file

### Configuration and Deployment
- **`requirements.txt`** - Python package dependencies
- **`Dockerfile`** - Container image configuration
- **`docker-compose.yml`** - Multi-container orchestration
- **`alembic.ini`** - Alembic configuration file

## Prerequisites

- Python 3.8+
- PostgreSQL 12+
- Redis 6+
- Docker (optional)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd super-ex-back
```


2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

## Running the Application

```bash
docker-compose up -d
```

## API Documentation

Once the application is running, access the interactive API documentation at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Configuration

Key configuration options in `app/core/config.py`:
- Database connection settings
- Redis configuration
- JWT secret keys
- CORS origins
- External service API keys

## Development

### Adding New Features
1. Create new router in `app/routers/`
2. Implement business logic in `app/services/`
3. Add database models in `app/models.py`
4. Define Pydantic schemas in `app/schemas.py`
5. Include router in `app/main.py`

### Database Migrations
```bash
# Create new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

## Deployment

The application is containerized using Docker. Production deployment includes:
- PostgreSQL database
- Redis cache
- FastAPI application
- Nginx reverse proxy (optional)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

