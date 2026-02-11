# RAG-сервис для работы с внутренними документами

## Описание

RAG-сервис (Retrieval-Augmented Generation) — система для поиска и генерации ответов на основе внутренних документов организации. Проект состоит из:

- `qdrant` — векторная база данных
- `rag-ingest` — загрузка/векторизация документов из папки `data/` в Qdrant (запускается вручную)
- `rag-bot` — FastAPI сервис генерации ответов (LLM), принимает вопрос + контекст
- `rag-yandex-bot` — бот Яндекс.Мессенджера: строит эмбеддинг вопроса → ищет контекст в Qdrant → вызывает `rag-bot`

## Компоненты

### 1) `rag-bot` (FastAPI, LLM)

**Файл:** `rag-bot/ask_question.py`  
FastAPI сервис, предоставляет API для генерации ответов.

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

#### API эндпоинты
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

### 2) `rag-ingest` (векторизация документов в Qdrant)

**Файл:** `rag-ingest/ingest.py`  
Утилита для первичной/инкрементальной загрузки документов из `./data` в Qdrant:
- парсит `.docx` и `.pdf` (если есть оба варианта одного документа — приоритет у `.docx`)
- режет текст на чанки
- запрашивает эмбеддинги через OpenRouter (`OPENROUTER_API_KEY`, `OPENROUTER_EMBEDDING_MODEL`)
- создаёт коллекцию при необходимости и загружает точки в Qdrant
- ведёт состояние обработанных файлов в volume `ingest_state` (SQLite)

## Docker-контейнеризация

### docker-compose.yml

Основной файл для развертывания системы (web UI удалён, остались `qdrant`, `rag-bot`, `rag-yandex-bot`, `rag-ingest`).

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6390:6333"

  rag-bot:
    build: ./rag-bot
    ports:
      - "8090:8000"
    env_file:
      - .env
    environment:
      - PYTHONUNBUFFERED=1
      - HTTP_PROXY=http://host.docker.internal:20172
      - HTTPS_PROXY=http://host.docker.internal:20172
      - NO_PROXY=localhost,127.0.0.1,0.0.0.0,qdrant,rag-bot,rag-yandex-bot,rag-ingest,host.docker.internal,.ai.atomsk.ru,.dom.ru,192.168.42.11
    depends_on:
      - qdrant

  rag-yandex-bot:
    build: ./rag-yandex-bot
    env_file:
      - .env
    environment:
      - QDRANT_HOST=qdrant
      - RAG_BOT_ENDPOINT=http://rag-bot:8000/generate_answer
    depends_on:
      - rag-bot
      - qdrant

  rag-ingest:
    build: ./rag-ingest
    profiles: ["tools"]
    env_file:
      - .env
    environment:
      - QDRANT_HOST=qdrant
      - DOCS_DIR=/app/data
      - HTTP_PROXY=http://host.docker.internal:20172
      - HTTPS_PROXY=http://host.docker.internal:20172
      - NO_PROXY=localhost,127.0.0.1,0.0.0.0,qdrant,rag-bot,rag-yandex-bot,rag-ingest,host.docker.internal,.ai.atomsk.ru,.dom.ru,192.168.42.11
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

## Быстрый старт

1. **Создать `.env`** (можно на основе `.env.example`) и заполнить минимум:
   - `OPENROUTER_API_KEY=...`
   - `YANDEX_BOT_TOKEN=...`

2. **Запустить сервисы:**
   ```bash
   docker-compose up -d
   ```

3. **Векторизовать документы из `./data` в Qdrant (вручную):**
   ```bash
   docker-compose --profile tools run --rm rag-ingest python ingest.py
   ```

4. **Проверка статуса контейнеров:**
   ```bash
   docker-compose ps
   ```

### Доступ к сервисам

- **FastAPI документация (`rag-bot`)**: http://localhost:8090/docs
- **Qdrant**: http://localhost:6390 (HTTP API на порту 6333 внутри контейнера)

## Сетевая архитектура

### Прокси-настройки

`rag-bot` и `rag-ingest` используют HTTP(S) прокси, если он необходим для доступа к внешним API (OpenRouter/OpenAI/Gemini).

Критично, чтобы `NO_PROXY` включал все внутренние имена Docker-сервисов (`qdrant`, `rag-bot`, `rag-yandex-bot`, `rag-ingest`) и `host.docker.internal`, чтобы внутренние запросы не уходили в прокси.

### Внешние зависимости

1. **OpenRouter/OpenAI API** (для LLM и/или эмбеддингов)
2. **Google Gemini API** (опционально, если используется)
3. **Yandex Messenger Bot API** (для `rag-yandex-bot`)

## Мониторинг и логирование

### Логи сервисов
```bash
# Просмотр логов всех сервисов
docker-compose logs -f

# Логи конкретного сервиса
docker-compose logs -f rag-bot
docker-compose logs -f rag-yandex-bot
```

## Безопасность

### Переменные окружения
- API ключи хранятся в `.env` файлах
- Прокси-настройки для безопасного доступа к внешним API

### Сетевая безопасность
- Контейнеры изолированы в Docker сети
- Настроены исключения прокси для внутренних сервисов
- Использование HTTP(S) прокси для внешних запросов (если требуется)

## Устранение неисправностей

### Частые проблемы

1. **Ошибка подключения к Qdrant:**
   - Проверьте, что контейнер `qdrant` запущен
   - Убедитесь, что коллекция `internal_regulations_v2` создана (создаётся автоматически при первом `ingest.py`)

2. **Ошибка получения эмбеддингов:**
   - Проверьте `OPENROUTER_API_KEY`
   - Проверьте `HTTP_PROXY/HTTPS_PROXY/NO_PROXY` (если сеть требует прокси)

3. **Ошибки API ключей:**
   - Убедитесь в корректности файла `.env`
   - Проверьте права доступа к API ключам

4. **Прокси-проблемы:**
   - Убедитесь что прокси доступен на `host.docker.internal:20172`
   - Проверьте, что внутренние хосты (`qdrant`, `rag-bot`, …) добавлены в `NO_PROXY`

### Команды диагностики

```bash
# Проверка состояния контейнеров
docker-compose ps

# Проверка доступности эндпоинтов
curl http://localhost:8090/docs

# Тест API
curl -X POST http://localhost:8090/generate_answer \
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
ASK-Yandex-RAG-VND-Bot/
├── docker-compose.yml
├── data/                     # документы для индексации
├── qdrant_data/               # данные Qdrant (volume bind)
├── rag-bot/
│   ├── ask_question.py
│   ├── config.json
│   ├── system_prompt.txt
│   ├── requirements.txt
│   ├── Dockerfile
├── rag-ingest/
│   ├── ingest.py
│   ├── clear_data.py
│   ├── requirements.txt
│   └── Dockerfile
├── rag-yandex-bot/
│   ├── bot.py
│   ├── yandex_api.py
│   ├── health_server.py
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
```

Этот RAG-сервис предоставляет надежную и масштабируемую платформу для работы с внутренними документами, обеспечивая точные ответы на основе корпоративной базы знаний с использованием современных LLM технологий.