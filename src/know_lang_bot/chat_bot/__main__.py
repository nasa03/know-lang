from know_lang_bot.config import AppConfig
from know_lang_bot.chat_bot.chat_graph import process_chat
import chromadb
import asyncio

async def test_chat_processing():
    config = AppConfig()
    db_client = chromadb.PersistentClient(
        path=str(config.db.persist_directory)
    )
    collection = db_client.get_collection(
        name=config.db.collection_name
    )
    
    result = await process_chat(
        "How does the parser handle nested classes?",
        collection,
        config
    )
    
    print(f"Answer: {result.answer}")

if __name__ == "__main__":
    asyncio.run(test_chat_processing())