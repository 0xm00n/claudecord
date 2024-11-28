from typing import Optional, Dict, Any
import os
from pathlib import Path
import asyncio
from paperqa import Settings, ask, Docs
from paperqa.clients import DocMetadataClient, ALL_CLIENTS
import paperscraper
from dotenv import load_dotenv
import csv

load_dotenv()
CLAUDE_KEY: str = os.getenv('ANTHROPIC_API_KEY')
OPENAI_KEY: str = os.getenv('OPENAI_API_KEY')

BASE_SETTINGS = Settings(
    # paperqa's bundled setting
    settings="high_quality"
)

BASE_SETTINGS.prompts.qa = """
If there is insufficient context to answer the question properly, respond with exactly and only this phrase:
"INSUFFICIENT_CONTEXT"

Context: {context}
"""

class RagProcessor:
    def __init__(self, papers_dir: str = "papers"):
        """Initialize RAG processor with papers directory"""
        self.papers_dir = Path(papers_dir)
        self.papers_dir.mkdir(exist_ok=True)
        self.docs = Docs()
        self.metadata_client = DocMetadataClient(clients=ALL_CLIENTS)
        self.manifest_file = self.papers_dir / "manifest.csv"
        
    async def get_paper_metadata(self, title: str, authors: Optional[list] = None) -> Dict[str, Any]:
        """Get high quality metadata from multiple sources"""
        try:
            details = await self.metadata_client.query(
                title=title,
                authors=authors,
                fields=["title", "doi", "citation_count", "license", "pdf_url", "formatted_citation"]
            )
            return {
                "citation": details.formatted_citation,
                "citation_count": details.citation_count,
                "license": details.license,
                "pdf_url": details.pdf_url,
                "doi": details.doi,
                "title": details.title
            }
        except Exception as e:
            print(f"Error getting metadata: {e}")
            return {}

    async def update_manifest(self, filename: str, metadata: Dict[str, Any]) -> None:
        """Update the manifest CSV file with paper metadata"""
        try:
            # create manifest file if it doesn't exist
            if not self.manifest_file.exists():
                with open(self.manifest_file, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['file_location', 'doi', 'title'])

            # read existing entries
            entries = []
            with open(self.manifest_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                entries = list(reader)

            # update or add new entry
            file_location = str(Path(filename).relative_to(self.papers_dir))
            updated = False
            for entry in entries:
                if entry['file_location'] == file_location:
                    entry['doi'] = metadata.get('doi', '')
                    entry['title'] = metadata.get('title', '')
                    updated = True
                    break

            if not updated:
                entries.append({
                    'file_location': file_location,
                    'doi': metadata.get('doi', ''),
                    'title': metadata.get('title', '')
                })

            # Write back all entries
            with open(self.manifest_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['file_location', 'doi', 'title'])
                writer.writeheader()
                writer.writerows(entries)

        except Exception as e:
            print(f"Error updating manifest: {e}")

    async def extract_paper_title(self, pdf_path: str) -> str:
        """Extract paper title from PDF using paperqa's Docs"""
        try:
            # create a temporary Docs instance to extract title
            temp_docs = Docs()
            await temp_docs.aadd(pdf_path, settings=BASE_SETTINGS)
            # paperqa's Docs will extract the title during add
            return temp_docs.docs[-1].docname
        except Exception as e:
            print(f"Error extracting title: {e}")
            return None

    async def add_paper(self, file_bytes: bytes, filename: str) -> bool:
        """Add a paper to the local papers directory"""
        try:
            # save PDF to papers directory
            pdf_path = self.papers_dir / filename
            with open(pdf_path, 'wb') as f:
                f.write(file_bytes)

            # extract actual paper title from PDF
            paper_title = await self.extract_paper_title(str(pdf_path))
            if not paper_title:
                print("Could not extract paper title")
                return False

            # get metadata using the extracted title
            metadata = await self.get_paper_metadata(paper_title)
            
            # update manifest with metadata
            await self.update_manifest(filename, metadata)
            
            # add to main docs instance
            await self.docs.aadd(str(pdf_path), settings=BASE_SETTINGS)
            
            return True
        except Exception as e:
            print(f"Error adding paper: {e}")
            return False

    async def local_rag(self, query: str) -> Optional[str]:
        """Perform RAG using local papers database"""
        try:
            # use the already loaded docs from add_paper
            if not self.docs.docs:
                # if no papers have been added yet, try to load from papers directory
                for pdf in self.papers_dir.glob("*.pdf"):
                    try:
                        await self.docs.aadd(str(pdf), settings=BASE_SETTINGS)
                    except Exception as e:
                        print(f"Error loading {pdf}: {e}")
                        continue
                
                if not self.docs.docs:
                    return None
            
            # use paperqa's built-in query functionality
            answer = await self.docs.aquery(query, settings=BASE_SETTINGS)
            
            # check for our insufficient context marker
            if answer.answer.strip() == "INSUFFICIENT_CONTEXT":
                return None
                
            return answer.formatted_answer

        except Exception as e:
            print(f"Error in local RAG: {e}")
            return None

    async def search_rag(self, query: str, keyword_search: Optional[str] = None) -> Optional[str]:
        """Perform RAG by searching and downloading papers"""
        try:
            # use query to generate search keywords if not provided
            if not keyword_search:
                # Extract key terms from query
                keyword_search = query.lower().replace("?", "").replace(".", "")
            
            # ssearch and download papers
            papers = await paperscraper.a_search_papers(keyword_search)
            
            # create new docs instance for search results
            search_docs = Docs()
            
            for path, data in papers.items():
                try:
                    # get metadata for high quality citations
                    metadata = await self.get_paper_metadata(data.get("title", ""))
                    await search_docs.aadd(
                        path,
                        citation=metadata.get("citation", path),
                        docname=data.get("title", path),
                        settings=BASE_SETTINGS
                    )
                except ValueError as e:
                    print(f"Could not read {path}: {e}")
                    continue
            
            # use paperqa's built-in query functionality
            answer = await search_docs.aquery(query, settings=BASE_SETTINGS)
            
            # check for our insufficient context marker
            if answer.answer.strip() == "INSUFFICIENT_CONTEXT":
                return None
                
            return answer.formatted_answer

        except Exception as e:
            print(f"Error in search RAG: {e}")
            return None

    async def process_query(self, query: str) -> str:
        """Process query using local RAG first, then fall back to search if needed"""
        
        # try local RAG first
        local_answer = await self.local_rag(query)
        
        # if local RAG found relevant evidence and generated an answer, use it
        if local_answer:
            return local_answer
            
        # if local RAG couldn't find relevant evidence, try search RAG
        print("Local papers insufficient, searching external sources...")
        search_answer = await self.search_rag(query)
        
        if search_answer:
            return search_answer
        else:
            return "Unable to find sufficient information to answer the query in available papers."
