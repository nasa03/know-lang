from typing import List
import chromadb
from chromadb.errors import InvalidCollectionException
from pydantic_ai import Agent
from pydantic import BaseModel, Field
import ollama

from know_lang_bot.config import AppConfig
from know_lang_bot.code_parser.parser import CodeChunk
from know_lang_bot.utils.fancy_log import FancyLogger
from pprint import pformat

LOG = FancyLogger(__name__)

class ChunkMetadata(BaseModel):
    """Model for chunk metadata stored in ChromaDB"""
    file_path: str
    start_line: int
    end_line: int
    type: str
    name: str
    docstring: str = Field(default='')

class CodeSummarizer:
    def __init__(self, config: AppConfig):
        self.config = config
        self._init_agent()
        self._init_db()

    def _init_agent(self):
        """Initialize the LLM agent with configuration"""
        system_prompt = """
        You are an expert code analyzer. Your task is to analyze code chunks and provide clear, 
        concise summaries. Focus on:
        1. The main purpose and functionality
        2. Key implementation details
        3. Important patterns or techniques used
        4. Any notable dependencies or requirements
        
        Provide a concise summary and list key points separately.
        """
        
        self.agent = Agent(
            f"{self.config.llm.model_provider}:{self.config.llm.model_name}",
            system_prompt=system_prompt,
            model_settings=self.config.llm.model_settings
        )

    def _init_db(self):
        """Initialize ChromaDB with configuration"""
        self.db_client = chromadb.PersistentClient(
            path=str(self.config.db.persist_directory)
        )
        
        try:
            self.collection = self.db_client.get_collection(
                name=self.config.db.collection_name
            )
        except InvalidCollectionException:
            LOG.debug(f"Collection {self.config.db.collection_name} not found, creating new collection")
            self.collection = self.db_client.create_collection(
                name=self.config.db.collection_name,
                metadata={"hnsw:space": "cosine"}
            )

    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for text using configured provider"""
        if self.config.llm.embedding_provider == "ollama":
            response = ollama.embed(
                model=self.config.llm.embedding_model,
                input=text
            )
            return response['embeddings']
        else:
            raise ValueError(f"Unsupported embedding provider: {self.config.llm.embedding_provider}")

    async def summarize_chunk(self, chunk: CodeChunk) -> str:
        """Summarize a single code chunk using the LLM"""
        prompt = f"""
        Analyze this {chunk.type.value} code chunk:
        
        {chunk.content}
        
        {f'Docstring: {chunk.docstring}' if chunk.docstring else ''}
        
        Provide a concise summary and key points about its functionality and implementation.
        """
        
        result = await self.agent.run(prompt)
        LOG.debug(f"Summary for chunk {chunk.file_path}:{chunk.start_line}-{chunk.end_line}:\n{pformat(result.data)}")

        return result.data

    async def process_and_store_chunk(self, chunk: CodeChunk):
        """Process a chunk and store it in ChromaDB"""
        summary = await self.summarize_chunk(chunk)
        
        # Create a unique ID for the chunk
        chunk_id = f"{chunk.file_path}:{chunk.start_line}-{chunk.end_line}"
        
        # Create metadata using Pydantic model
        metadata = ChunkMetadata(
            file_path=chunk.file_path,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            type=chunk.type.value,
            name=chunk.name,
            docstring=chunk.docstring if chunk.docstring else ''
        )
        
        # Get embedding for the summary
        embedding = self._get_embedding(summary)
        
        # Store in ChromaDB
        self.collection.add(
            documents=[summary],
            embeddings=embedding,
            metadatas=[metadata.model_dump()],
            ids=[chunk_id]
        )

    async def process_chunks(self, chunks: List[CodeChunk]):
        """Process multiple chunks in parallel"""
        for chunk in chunks:
            await self.process_and_store_chunk(chunk)