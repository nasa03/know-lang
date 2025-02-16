from pathlib import Path
from typing import List
import chromadb
from chromadb.errors import InvalidCollectionException
from pydantic_ai import Agent
from pydantic import BaseModel, Field
from pprint import pformat
from rich.progress import Progress

from knowlang.configs.config import AppConfig
from knowlang.core.types import CodeChunk, DatabaseChunkMetadata
from knowlang.utils.chunking_util import format_code_summary
from knowlang.utils.fancy_log import FancyLogger
from knowlang.utils.model_provider import create_pydantic_model
from knowlang.models.embeddings import generate_embedding
from knowlang.vector_stores.base import VectorStore
from knowlang.vector_stores.factory import VectorStoreFactory

LOG = FancyLogger(__name__)


class CodeSummarizer:
    def __init__(
        self, 
        config: AppConfig,
    ):
        """
        Initialize CodeSummarizer with config and optional vector store.
        If vector store is not provided, creates one based on config.
        """
        self.config = config
        self.vector_store = VectorStoreFactory.get(config.db)
        self._init_agent()

    def _init_agent(self):
        """Initialize the LLM agent with configuration"""
        system_prompt = """
You are an expert code analyzer specializing in creating searchable and contextual code summaries. 
Your summaries will be used in a RAG system to help developers understand complex codebases.
Focus on following points:
1. The main purpose and functionality
- Use precise technical terms
- Preserve class/function/variable names exactly
- State the primary purpose
2. Narrow down key implementation details
- Focus on key algorithms, patterns, or design choices
- Highlight important method signatures and interfaces
3. Any notable dependencies or requirements
- Reference related classes/functions by exact name
- List external dependencies
- Note any inherited or implemented interfaces
        
Provide a clean, concise and focused summary. Don't include unnecessary nor generic details.
"""
        
        self.agent = Agent(
            create_pydantic_model(
                model_provider=self.config.llm.model_provider,
                model_name=self.config.llm.model_name
            ),
            system_prompt=system_prompt,
            model_settings=self.config.llm.model_settings
        )

    async def summarize_chunk(self, chunk: CodeChunk) -> str:
        """Summarize a single code chunk using the LLM"""
        prompt = f"""
        Analyze this {chunk.type.value} code chunk:
        
        {chunk.content}
        
        {f'Docstring: {chunk.docstring}' if chunk.docstring else ''}
        
        Provide a concise summary.
        """
        
        result = await self.agent.run(prompt)

        return format_code_summary(chunk.content, result.data)
    
    async def process_and_store_chunk(self, chunk: CodeChunk):
        """Process a chunk and store it in vector store"""
        summary = await self.summarize_chunk(chunk)
        
        # Create metadata using Pydantic model
        metadata = DatabaseChunkMetadata.from_code_chunk(chunk)
    
        # Get embedding for the summary
        embedding = generate_embedding(summary, self.config.embedding)
        
        await self.vector_store.add_documents(
            documents=[summary],
            embeddings=embedding,
            metadatas=[metadata.model_dump()],
            # Create a unique ID for the chunk
            ids=[chunk.location.to_single_line()]
        )

    async def process_chunks(self, chunks: List[CodeChunk]):
        """Process multiple chunks in parallel"""
        with Progress() as progress:
            task = progress.add_task("Summarizing chunks into vector database...", total=len(chunks))
            
            for chunk in chunks:
                try:
                    await self.process_and_store_chunk(chunk)
                    progress.advance(task)
                except Exception as e:
                    LOG.error(f"Error processing chunk {chunk.location}: {e}")
                    # Continue processing other chunks even if one fails
                    continue