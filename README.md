# RAG-Сервис для Работы с Внутренними Документами

## Описание

RAG-сервис (Retrieval-Augmented Generation) представляет собой систему для поиска и генерации ответов на основе внутренних документов организации ВНД Атомстройкомплекс. Система состоит из двух основных компонентов:


**Файл:** `rag-bot/ask_question.py`

Бэкенд-сервис построен на FastAPI и предоставляет API для генерации ответов с использованием LLM моделей.

#### Основные классы и функции:

##### AppConfig (строки 19-60)
Класс для управления конфигурацией приложения:
- `__init__()` - инициализация конфигурации, загрузка переменных окружения
- `_load_config()` - загрузка настроек из config.json
- `_load_system_prompt()` - загрузка системного промпта из system_prompt.txt
- `_setup_openai_client()` - настройка клиента OpenAI
- `_setup_gemini_client()` - настройка клиента Google Gemini

##### AIService (строки 82-146)
Основной класс для работы с AI-моделями:
- `_build_user_prompt()` - формирование пользовательского запроса с контекстом
- `_generate_openai_answer()` - генерация ответа через OpenAI API
- `_generate_gemini_answer()` - генерация ответа через Google Gemini API
- `generate_answer()` - главная функция для выбора провайдера и генерации ответа

##### API-эндпоинты:
- `POST /generate_answer` - основной эндпоинт для получения ответов

#### Модели данных (Pydantic):

```python
class SourceChunk(BaseModel):
    text: str      # Текст фрагмента документа
    file: str      # Имя файла источника

class RAGRequest(BaseModel):
    question: str                    # Вопрос пользователя
    context: List[SourceChunk]       # Контекст из найденных документов
    model_provider: Optional[str]    # Провайдер модели (openai/gemini)

class PlainTextAnswerResponse(BaseModel):
    answer: str      # Сгенерированный ответ
    model_used: str  # Использованная модель
```

### 2. rag-chat (Фронтенд-интерфейс)

**Файл:** `rag-chat/main_app.py`

Фронтенд-сервис на базе Gradio для взаимодействия с пользователем.

#### Основные классы и функции:

##### RAGOrchestrator (строки 7-96)
Главный класс-оркестратор для обработки запросов:

- `__init__(qdrant_client)` - инициализация с клиентом Qdrant
- `get_embedding(text)` - получение эмбеддинга текста от внешнего сервиса
- `query_llm(question, context)` - отправка запроса в LLM-сервис (rag-bot)
- `process_query(question)` - полный цикл обработки вопроса пользователя
- `_search_and_prepare_context(embedding)` - поиск релевантного контекста в Qdrant
- `_make_api_request()` - универсальный метод для HTTP-запросов
- `_log_step()` - логирование шагов обработки

#### Пошаговый процесс обработки запроса:

- Запрет на использование общих знаний
- Краткие и точные ответы
- Обработка случаев отсутствия ответа в документах

## Docker-контейнеризация

### docker-compose.yml

Основной файл для развертывания всей системы:

```yaml
version: '3.8'
services:
  rag-bot:
  rag-chat:
    build: ./rag-chat
    container_name: rag_chat_service  
    restart: unless-stopped
    ports:
      - "7860:7860"
    environment:
      - NO_PROXY=192.168.42.188,192.168.45.64  # Исключения для Qdrant и эмбеддингов
      - PYTHONUNBUFFERED=1
    depends_on:
      - rag-bot
```

### Dockerfile для rag-bot

```dockerfile
FROM mirror.gcr.io/library/python:3.11-slim-bullseye
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "ask_question.py"]
```

## Зависимости

### rag-bot/requirements.txt
- `fastapi` - веб-фреймворк для API
- `uvicorn` - ASGI сервер
- `openai` - клиент для OpenAI API
- `pydantic` - валидация данных
- `python-dotenv` - загрузка переменных окружения
- `google-generativeai` - клиент для Google Gemini
- `httpx[socks]` - HTTP клиент с поддержкой SOCKS прокси

4. **Проверка статуса:**
   ```bash
   docker-compose ps
   ```

### Доступ к сервисам

- **FastAPI документация:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/generate_answer

## Сетевая архитектура

### Прокси-настройки

**rag-bot сервис** использует SOCKS5 прокси для доступа к внешним API:
- Прокси: `socks5://172.17.0.1:10808`
- Исключения: `localhost,127.0.0.1,rag-chat`

**rag-chat сервис** исключает из прокси внутренние сервисы:
- Исключения: `192.168.42.188,192.168.45.64`

### Внешние зависимости

1. **Qdrant Vector Database:** `192.168.42.188:6333`
2. **Embedding Service:** `192.168.45.55:8001`
3. **OpenAI API** (через VPN/прокси)
4. **Google Gemini API** (через VPN/прокси)

## Мониторинг и логирование

### Логи сервисов
```bash
# Просмотр логов всех сервисов
docker-compose logs -f

# Логи конкретного сервиса
docker-compose logs -f rag-bot
docker-compose logs -f rag-chat
```

### Отладочная информация

**rag-chat** выводит пошаговую информацию:
- Получение эмбеддинга для вопроса
- Поиск релевантного контекста в Qdrant
- Отправка запроса на LLM-сервис
- Количество найденных источников

## Безопасность

### Переменные окружения
- API ключи хранятся в `.env` файлах
- Файл `.env` монтируется как read-only том
- Прокси-настройки для безопасного доступа к внешним API

### Сетевая безопасность
- Контейнеры изолированы в Docker сети
- Настроены исключения прокси для внутренних сервисов
- Использование SOCKS5 прокси для внешних запросов

## Устранение неисправностей

### Частые проблемы

1. **Ошибка подключения к Qdrant:**
   - Проверьте доступность `192.168.42.188:6333`
   - Убедитесь, что коллекция `internal_regulations_v2` существует

2. **Ошибка получения эмбеддингов:**
   - Проверьте доступность `192.168.45.55:8001`
   - Проверьте сетевые настройки прокси

3. **Ошибки API ключей:**
   - Убедитесь в корректности файла `.env`
   - Проверьте права доступа к API ключам

4. **Прокси-проблемы:**
   - Убедитесь что SOCKS5 прокси доступен на `172.17.0.1:10808`
   - Проверьте настройки NO_PROXY

### Команды диагностики

```bash
# Проверка состояния контейнеров
docker-compose ps

# Проверка доступности эндпоинтов
curl http://localhost:8000/docs
curl http://localhost:7860

# Тест API
curl -X POST http://localhost:8000/generate_answer \
  -H "Content-Type: application/json" \
  -d '{"question":"тест","context":[{"text":"тестовый контекст","file":"test.txt"}]}'
```

## Масштабирование

Для масштабирования системы можно:

1. **Горизонтальное масштабирование rag-bot:**
   ```yaml
   rag-bot:
     deploy:
       replicas: 3
   ```

2. **Настройка load balancer** для распределения нагрузки
3. **Кэширование** часто запрашиваемых ответов
4. **Оптимизация** параметров поиска в Qdrant

## Разработка

### Структура проекта
```
rag-service/
├── docker-compose.yml
├── rag-bot/
│   ├── ask_question.py
│   ├── config.json
│   ├── system_prompt.txt
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env (не включен в git)
├── rag-chat/
│   ├── main_app.py
│   ├── config.py
│   ├── requirements.txt
│   └── Dockerfile
└── README.md
```

### Локальная разработка

Для локальной разработки без Docker:

```bash
# rag-bot
cd rag-bot
pip install -r requirements.txt
python ask_question.py

# rag-chat  
cd rag-chat
pip install -r requirements.txt
python main_app.py
```

Этот RAG-сервис предоставляет надежную и масштабируемую платформу для работы с внутренними документами, обеспечивая точные ответы на основе корпоративной базы знаний с использованием современных LLM технологий.