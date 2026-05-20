"""RAG Engine — orchestrates chunking, embedding, storage, and retrieval."""

from rag_mcp.engine.chunker import Chunker
from rag_mcp.engine.embedder import Embedder
from rag_mcp.engine.metadata_store import MetadataStore
from rag_mcp.engine.vector_store import VectorStore
from rag_mcp.log import get_logger
from rag_mcp.models import (
    Document, DocumentStatus, IngestionResult,
    SearchResult, SourceType,
)

logger = get_logger(__name__)


class RAGEngine:
    """Core orchestrator: ingest content → chunk → embed → store → retrieve."""

    def __init__(self) -> None:
        logger.info("Initializing RAG engine...")
        self.chunker = Chunker()
        self.embedder = Embedder()
        self.vector_store = VectorStore()
        self.metadata_store = MetadataStore()
        logger.info("RAG engine ready")

    def ingest(
        self,
        text: str,
        source_type: SourceType | str,
        title: str = "Untitled",
        namespace: str = "default",
        source_url: str | None = None,
        filename: str | None = None,
        tags: list[str] | None = None,
    ) -> IngestionResult:
        """Ingest text content into the knowledge base.

        Args:
            text: Raw text content to ingest.
            source_type: Origin type (text, url, youtube, file).
            title: Human-readable document title.
            namespace: Namespace for isolation.
            source_url: Original source URL if applicable.
            filename: Original filename if applicable.
            tags: Optional tags for categorization.

        Returns:
            IngestionResult with document_id and chunk_count.
        """
        if isinstance(source_type, str):
            source_type = SourceType(source_type)

        # Create document record
        doc = Document(
            namespace=namespace,
            source_type=source_type,
            source_url=source_url,
            title=title,
            filename=filename,
            tags=tags or [],
            status=DocumentStatus.PROCESSING,
        )
        self.metadata_store.save_document(doc)
        logger.info("Ingestion started", document_id=doc.id, title=title)

        try:
            # Chunk
            chunks = self.chunker.chunk(text, document_id=doc.id)
            if not chunks:
                self.metadata_store.update_document_status(
                    doc.id, DocumentStatus.INDEXED, chunk_count=0,
                )
                return IngestionResult(
                    document_id=doc.id, title=title,
                    chunk_count=0, namespace=namespace,
                    message="Document was empty, no chunks created.",
                )

            # Embed
            chunk_texts = [c.text for c in chunks]
            embeddings = self.embedder.embed_texts(chunk_texts)

            # Store vectors in ChromaDB
            chunk_ids = [c.id for c in chunks]
            metadatas = [
                {
                    "document_id": doc.id,
                    "document_title": title,
                    "source_type": source_type.value,
                    "source_url": source_url or "",
                    "chunk_index": c.chunk_index,
                    "namespace": namespace,
                }
                for c in chunks
            ]
            self.vector_store.upsert(
                namespace=namespace,
                ids=chunk_ids,
                embeddings=embeddings,
                documents=chunk_texts,
                metadatas=metadatas,
            )

            # Store chunk metadata in SQLite
            self.metadata_store.save_chunks(chunks)

            # Update document status
            self.metadata_store.update_document_status(
                doc.id, DocumentStatus.INDEXED, chunk_count=len(chunks),
            )

            logger.info(
                "Ingestion complete",
                document_id=doc.id, chunks=len(chunks),
            )
            return IngestionResult(
                document_id=doc.id, title=title,
                chunk_count=len(chunks), namespace=namespace,
            )

        except Exception as e:
            logger.error("Ingestion failed", document_id=doc.id, error=str(e))
            self.metadata_store.update_document_status(
                doc.id, DocumentStatus.FAILED, error_message=str(e),
            )
            raise

    def search(
        self,
        query: str,
        namespace: str = "default",
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Semantic search across the knowledge base.

        Args:
            query: Natural language search query.
            namespace: Namespace to search within.
            top_k: Maximum number of results.

        Returns:
            List of SearchResult sorted by relevance.
        """
        query_embedding = self.embedder.embed_query(query)

        results = self.vector_store.query(
            namespace=namespace,
            query_embedding=query_embedding,
            n_results=top_k,
        )

        search_results: list[SearchResult] = []
        if results and results.get("ids") and results["ids"][0]:
            ids = results["ids"][0]
            documents = results["documents"][0]
            metadatas = results["metadatas"][0]
            distances = results["distances"][0]

            for i, doc_id in enumerate(ids):
                meta = metadatas[i]
                # ChromaDB returns distance; convert to similarity score
                score = 1.0 - distances[i]
                search_results.append(
                    SearchResult(
                        text=documents[i],
                        score=round(score, 4),
                        document_id=meta.get("document_id", ""),
                        document_title=meta.get("document_title", ""),
                        source_type=meta.get("source_type", "text"),
                        source_url=meta.get("source_url") or None,
                        chunk_index=meta.get("chunk_index", 0),
                        namespace=namespace,
                    )
                )

        logger.debug("Search complete", query=query[:50], results=len(search_results))
        return search_results

    def delete_document(self, document_id: str) -> bool:
        """Delete a document and all its vectors/metadata.

        Returns:
            True if the document was found and deleted.
        """
        doc = self.metadata_store.get_document(document_id)
        if not doc:
            return False

        # Get chunk IDs to delete from vector store
        chunks = self.metadata_store.get_chunks_by_document(document_id)
        if chunks:
            chunk_ids = [c.id for c in chunks]
            self.vector_store.delete(doc.namespace, chunk_ids)

        # Delete from metadata store
        self.metadata_store.delete_document(document_id)
        logger.info("Document deleted", document_id=document_id)
        return True

    def list_documents(
        self, namespace: str | None = None,
        source_type: str | None = None, limit: int = 100,
    ) -> list[Document]:
        """List documents with optional filtering."""
        return self.metadata_store.list_documents(namespace, source_type, limit)

    def get_document(self, document_id: str) -> Document | None:
        """Get a single document by ID."""
        return self.metadata_store.get_document(document_id)

    def search_documents(self, **kwargs) -> list[Document]:
        """Search documents by metadata."""
        return self.metadata_store.search_documents(**kwargs)
