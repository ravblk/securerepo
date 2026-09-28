import logging
from typing import Optional, List

import requests
from bs4 import BeautifulSoup

from .config import settings
from .retry_service import RetryService
from .exceptions import ContentFetchError

logger = logging.getLogger(__name__)


class ContentService:
    """Service for fetching and processing web content."""

    def __init__(self):
        self._retry_service = RetryService()
        self._user_agent = "Mozilla/5.0 (compatible; Internal-Rules-Ingestion/2.0)"

    def convert_github_to_raw(self, url: str) -> str:
        """Convert GitHub blob URL to raw URL."""
        if 'github.com' in url and '/blob/' in url:
            return url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
        return url

    def split_content_by_headers(self, content: str, base_id: str) -> List[dict]:
        """
        Split content into logical chunks by headers.

        This function handles:
        - Markdown headers: ##, ###
        - ALL CAPS lines
        - Keywords: Chapter, Раздел, Section, Глава, Chapter
        - Structured format: 1., 1.1, -, *, lines ending with colon

        Args:
            content: The content to split
            base_id: Base ID for generating chunk IDs (e.g., "doc-100")

        Returns:
            List of dictionaries with 'header', 'content', 'id' keys
        """
        if not content or not content.strip():
            return []

        import re

        lines = content.split('\n')
        chunks = []
        current_chunk = {"header": "", "content": [], "id": ""}

        # More specific header patterns - avoid markdown lists etc.
        markdown_pattern = re.compile(r'^(#{2,3})\s+(.+)')  ##, ### (not # main title)
        all_caps_pattern = re.compile(r'^[A-ZА-ЯЁ][A-ZА-ЯЁ0-9\s]+$')  # ALL CAPS
        keyword_pattern = re.compile(r'^(Chapter|Раздел|Section|Глава|Chapter)\s+\d+[:.]')  # Keywords
        numbered_pattern = re.compile(r'^(\d+\.\d+)\s+')  # 1.1, 2.3, etc.
        single_digit_pattern = re.compile(r'^(\d+)\.\s+\d+')  # "1. Introduction" style

        for line in lines:
            stripped_line = line.strip()
            if not stripped_line:
                continue

            # Skip main document title (# Header level 1)
            if stripped_line.startswith('# '):
                continue

            # Check if line is a header
            is_header = False
            header_match = None

            # Check markdown headers (##, ###)
            if markdown_pattern.match(stripped_line):
                is_header = True
                header_match = stripped_line

            # Check ALL CAPS (must be short, not content)
            elif all_caps_pattern.match(stripped_line) and len(stripped_line) < 60:
                is_header = True
                header_match = stripped_line

            # Check keyword patterns
            elif keyword_pattern.match(stripped_line):
                is_header = True
                header_match = stripped_line

            # Check numbered patterns like "1.2" but not markdown lists like "- item"
            elif numbered_pattern.match(stripped_line):
                is_header = True
                header_match = stripped_line

            # Check single digit like "1. Introduction" (not markdown "1. item")
            elif single_digit_pattern.match(stripped_line):
                is_header = True
                header_match = stripped_line

            if is_header:
                # Save previous chunk if exists
                if current_chunk["header"] or current_chunk["content"]:
                    chunk_id = f"{base_id}-{len(chunks)}"
                    current_chunk["id"] = chunk_id
                    current_chunk["content"] = '\n'.join(current_chunk["content"]).strip()
                    chunks.append(current_chunk)

                # Start new chunk
                current_chunk = {
                    "header": header_match,
                    "content": [],
                    "id": ""
                }
            else:
                current_chunk["content"].append(line)

        # Add final chunk
        if current_chunk["header"] or current_chunk["content"]:
            chunk_id = f"{base_id}-{len(chunks)}"
            current_chunk["id"] = chunk_id
            current_chunk["content"] = '\n'.join(current_chunk["content"]).strip()
            chunks.append(current_chunk)

        # Filter out chunks that have header but empty content
        valid_chunks = [chunk for chunk in chunks
                        if not chunk['header'] or len(chunk['content']) > 10]

        return valid_chunks

    def get_text_from_url(self, url: str) -> str:
        """Extract text content from a web page."""
        # Convert GitHub blob URLs to raw URLs for proper content extraction
        url = self.convert_github_to_raw(url)

        def fetch_func():
            headers = {
                "User-Agent": self._user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }

            response = requests.get(url, headers=headers, timeout=settings.request_timeout)
            response.raise_for_status()
            return response

        try:
            response = self._retry_service.execute_with_retry(
                fetch_func,
                name=f"GET {url[:80]}"
            )

            # Check if the response is raw markdown (GitHub raw URLs)
            if 'raw.githubusercontent.com' in url or url.endswith('.md'):
                # Raw markdown content - return directly
                text = response.text
                logger.info(f"Extracted {len(text)} characters from raw markdown: {url}")

                # Clean up text
                text = self._clean_text(text)
                return text
            else:
                # HTML content - use BeautifulSoup
                soup = BeautifulSoup(response.content, "lxml")

                # Remove scripts and styles
                for element in soup(["script", "style", "nav", "footer", "header"]):
                    element.decompose()

                # Extract text
                text = soup.get_text(separator="\n")

                # Clean up text
                text = self._clean_text(text)

                logger.info(f"Extracted {len(text)} characters from HTML: {url}")
                return text

        except Exception as e:
            error_msg = f"Error fetching {url}: {e}"
            logger.error(error_msg)
            raise ContentFetchError(error_msg)

    def _clean_text(self, text: str) -> str:
        """Clean up extracted text."""
        # Remove excessive whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        cleaned_text = "\n".join(chunk for chunk in chunks if chunk)

        return cleaned_text

    def get_pages_from_json(self, pages_json: str) -> List[dict]:
        """Parse pages from JSON configuration."""
        import json
        try:
            # Try to parse as JSON
            if pages_json.startswith("["):
                pages = json.loads(pages_json)
            else:
                # Try to parse as comma-separated list (URLs only)
                urls = [url.strip() for url in pages_json.split(",") if url.strip()]
                pages = [
                    {"id": i, "title": f"Page {i}", "url": url}
                    for i, url in enumerate(urls, 1)
                ]
            return pages
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse PAGES_JSON: {e}")
            return []

    def test_url(self, url: str) -> tuple[bool, str]:
        """Test if URL is accessible."""
        try:
            text = self.get_text_from_url(url)
            if text and len(text) > 0:
                return True, f"URL accessible, {len(text)} characters extracted"
            return False, "URL accessible but returned empty content"
        except Exception as e:
            message = f"URL test failed: {str(e)}"
            logger.warning(message)
            return False, message
