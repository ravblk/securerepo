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

    def get_text_from_url(self, url: str) -> str:
        """Extract text content from a web page."""
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

            soup = BeautifulSoup(response.content, "lxml")

            # Remove scripts and styles
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            # Extract text
            text = soup.get_text(separator="\n")

            # Clean up text
            text = self._clean_text(text)

            logger.info(f"Extracted {len(text)} characters from {url}")
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
