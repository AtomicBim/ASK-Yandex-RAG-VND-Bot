"""
Yandex Messenger Bot
Main bot entry point with polling and file processing
"""
import os
import sys
import asyncio
import logging
import aiohttp
from dotenv import load_dotenv

from yandex_api import YandexMessengerClient
from health_server import start_health_server

from qdrant_client import QdrantClient
from openai import AsyncOpenAI

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Start health check server
start_health_server(port=8003)
logger.info("Health check server started on port 8003")

# Configuration
YANDEX_BOT_TOKEN = os.getenv("YANDEX_BOT_TOKEN")
if not YANDEX_BOT_TOKEN:
    logger.error("YANDEX_BOT_TOKEN not set")
    sys.exit(1)

# RAG Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "internal_regulations_v2")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_EMBEDDING_MODEL = os.getenv("OPENROUTER_EMBEDDING_MODEL", "google/gemini-embedding-001")
RAG_BOT_ENDPOINT = os.getenv("RAG_BOT_ENDPOINT", "http://rag-bot:8000/generate_answer")
SEARCH_LIMIT = int(os.getenv("SEARCH_LIMIT", 5))

# Clients
qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
openai_client = AsyncOpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
) if OPENROUTER_API_KEY else None


async def handle_callback_query(client: YandexMessengerClient, callback_query: dict):
    """
    Handle inline keyboard button callback (Stub for RAG bot)
    """
    chat_id = callback_query.get("from", {}).get("login")
    if chat_id:
        await client.send_message(chat_id, "⚠️ Эта функция временно недоступна в режиме RAG-бота.")


async def handle_text_message(client: YandexMessengerClient, message: dict):
    """
    Handle incoming text message from user (RAG Chat)
    """
    # Yandex API: chat_id can be in different places depending on API response structure
    chat_info = message.get("chat", {})
    chat_id = chat_info.get("chat_id") if isinstance(chat_info, dict) else None

    # For private chats, use login from 'from' field
    if not chat_id and "from" in message and chat_info.get("type") == "private":
        chat_id = message.get("from", {}).get("login")

    text = message.get("text", "")

    if not chat_id:
        return

    # Handle commands
    if text.startswith("/start") or text.startswith("/help"):
        await client.send_message(
            chat_id,
            "👋 Привет! Я RAG-бот для поиска по ВНД.\n\n"
            "❓ Задайте мне любой вопрос по внутренним документам, и я найду ответ.\n"
            "📂 База знаний обновляется автоматически."
        )
        return

    # RAG Logic
    try:
        await client.send_message(chat_id, "🔍 Ищу информацию...")
        
        # 1. Get Embedding
        if not openai_client:
            await client.send_message(chat_id, "❌ Ошибка: OpenAI клиент не настроен.")
            return

        embedding_resp = await openai_client.embeddings.create(
            model=OPENROUTER_EMBEDDING_MODEL,
            input=text
        )
        question_embedding = embedding_resp.data[0].embedding

        # 2. Search Qdrant
        search_results = qdrant_client.search(
            collection_name=QDRANT_COLLECTION_NAME,
            query_vector=question_embedding,
            limit=SEARCH_LIMIT,
            with_payload=True
        )

        if not search_results:
            await client.send_message(chat_id, "⚠️ К сожалению, я не нашел информации по вашему вопросу в базе знаний.")
            return

        # Prepare context
        context = [
            {"text": result.payload['text'], "file": result.payload.get('source_file', 'unknown')}
            for result in search_results
        ]
        
        # 3. Call RAG-Bot (LLM)
        payload = {
            "question": text,
            "context": context,
            "model_provider": "openai"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(RAG_BOT_ENDPOINT, json=payload, timeout=60) as response:
                if response.status == 200:
                    result = await response.json()
                    answer = result.get("answer", "Пустой ответ от LLM")
                    
                    # 4. Send Answer
                    final_message = answer
                    await client.send_message(chat_id, final_message)
                else:
                    error_text = await response.text()
                    logger.error(f"RAG-Bot error: {error_text}")
                    await client.send_message(chat_id, "❌ Ошибка при генерации ответа.")

    except Exception as e:
        logger.error(f"Error in RAG flow: {e}", exc_info=True)
        await client.send_message(chat_id, "❌ Произошла внутренняя ошибка.")


async def main():
    """
    Main bot loop with polling
    """
    logger.info("Starting Yandex Messenger Bot (RAG Mode)...")
    logger.info(f"RAG Endpoint: {RAG_BOT_ENDPOINT}")
    logger.info(f"Qdrant: {QDRANT_HOST}:{QDRANT_PORT}")

    # Initialize client
    client = YandexMessengerClient(YANDEX_BOT_TOKEN)

    # Test connection
    if not await client.test_connection():
        logger.error("Failed to connect to Yandex Messenger API")
        return

    logger.info("Bot started successfully. Polling for updates...")

    offset = 0

    try:
        while True:
            try:
                # Get updates
                updates = await client.get_updates(offset=offset, limit=10)

                if not updates:
                    await asyncio.sleep(1)
                    continue

                for update in updates:
                    # Log raw update for debugging
                    logger.info(f"Raw update received: {update}")

                    # Update offset
                    update_id = update.get("update_id", 0)
                    offset = max(offset, update_id + 1)

                    message = update.get("message", update)

                    # Check for text message
                    if "text" in message:
                        asyncio.create_task(handle_text_message(client, message))
                    elif "callback_data" in message:
                        asyncio.create_task(handle_callback_query(client, message))

            except Exception as e:
                logger.error(f"Error in polling loop: {e}", exc_info=True)
                await asyncio.sleep(5)

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")


if __name__ == "__main__":
    asyncio.run(main())