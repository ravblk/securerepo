import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from qdrant_client.models import PointStruct

from .config import settings
from .models import SeedStatus, SeedRequest
from .web_scraper import WebScraper
from .embedding_service import EmbeddingService
from .qdrant_service import QdrantService
from .exceptions import ScrapingError

logger = logging.getLogger(__name__)


class SeedController:
    """Controller for OWASP seeding operations."""

    def __init__(self, scraper: WebScraper, embedding_service: EmbeddingService, qdrant_service: QdrantService):
        self._scraper = scraper
        self._embedding_service = embedding_service
        self._qdrant_service = qdrant_service
        self._seed_status: dict = {}

    def get_pages(self) -> list:
        """Parse PAGES_JSON environment variable into list of URLs."""
        try:
            # Try to parse as JSON
            if settings.pages_json.startswith("["):
                return json.loads(settings.pages_json)
            # Try to parse as comma-separated list
            elif settings.pages_json:
                return [url.strip() for url in settings.pages_json.split(",") if url.strip()]
            else:
                logger.warning("PAGES_JSON is empty, using default OWASP Top 10 URLs")
                return self._get_default_pages()

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse PAGES_JSON: {e}, using default OWASP Top 10 URLs")
            return self._get_default_pages()

    def _get_default_pages(self) -> list:
        """Get default OWASP Top 10 pages."""
        return [
            "https://owasp.org/www-project-top-ten/",
        ]

    def start_seed(self, request: SeedRequest) -> str:
        """Start the seeding process."""
        seed_id = str(uuid.uuid4())
        pages = self.get_pages()
        max_depth = request.max_depth or settings.max_depth

        logger.info(f"Starting seed {seed_id} with {len(pages)} base pages, max depth: {max_depth}")

        self._seed_status[seed_id] = {
            "seed_id": seed_id,
            "status": "running",
            "pages_processed": 0,
            "pages_failed": 0,
            "nested_pages_found": 0,
            "started_at": datetime.utcnow().isoformat(),
            "current_url": None,
        }

        try:
            self._process_seed(seed_id, pages, max_depth)

            self._seed_status[seed_id]["status"] = "completed"
            self._seed_status[seed_id]["completed_at"] = datetime.utcnow().isoformat()

            processed = self._seed_status[seed_id]["pages_processed"]
            failed = self._seed_status[seed_id]["pages_failed"]
            nested = self._seed_status[seed_id]["nested_pages_found"]

            logger.info(f"Seed {seed_id} completed: {processed} processed, {failed} failed, {nested} nested pages")

        except Exception as e:
            self._seed_status[seed_id]["status"] = "failed"
            self._seed_status[seed_id]["error"] = str(e)
            logger.error(f"Seed {seed_id} failed: {e}")
            raise

        return seed_id

    def _process_seed(self, seed_id: str, pages: list, max_depth: int) -> None:
        """Process seed for all pages including nested pages."""
        self._scraper.reset_counter()
        all_urls = set()  # Use set to avoid duplicates

        # Add initial pages
        all_urls.update(pages)

        # If nested scanning is enabled, discover nested pages
        if settings.enable_nested_scanning and max_depth > 0:
            logger.info(f"Nested scanning enabled with max depth: {max_depth}")
            logger.info(f"Processing {len(pages)} base pages for nested link discovery")

            # First pass: discover nested links from initial pages
            pages_copy = pages.copy()  # Don't modify the original list
            for base_url in pages_copy:
                try:
                    logger.info(f"Fetching page for nested links: {base_url}")
                    html_content = self._scraper.get_html_content(base_url)

                    # Log details about the HTML content
                    if html_content:
                        html_lines = len(html_content.splitlines())
                        link_count = html_content.count('<a href=')
                        logger.info(f"HTML content received: {len(html_content)} chars, {html_lines} lines, {link_count} <a> tags")

                        nested_links = self._scraper.find_nested_links(
                            base_url,
                            html_content,
                            max_depth=max_depth
                        )

                        if nested_links:
                            all_urls.update(nested_links)
                            self._seed_status[seed_id]["nested_pages_found"] += len(nested_links)
                            logger.info(f"Found {len(nested_links)} new links from {base_url}")
                        else:
                            logger.warning(f"No nested links found on {base_url}")
                    else:
                        logger.warning(f"Empty HTML content from {base_url}")

                except Exception as e:
                    logger.warning(f"Failed to discover nested links from {base_url}: {e}")
                    self._seed_status[seed_id]["pages_failed"] += 1

            logger.info(f"Total URLs to process: {len(all_urls)} (including {self._seed_status[seed_id]['nested_pages_found']} nested pages)")
        else:
            logger.info("Nested scanning disabled or max_depth is 0 - processing only specified pages")

        # Process all URLs
        points = []
        for idx, url in enumerate(list(all_urls)):
            self._seed_status[seed_id]["current_url"] = url

            try:
                point = self._process_url(url, idx)
                if point:
                    points.append(point)
                    self._seed_status[seed_id]["pages_processed"] += 1

            except Exception as e:
                logger.error(f"Failed to process URL {url}: {e}")
                self._seed_status[seed_id]["pages_failed"] += 1

        # Upsert all points to Qdrant
        if points:
            self._qdrant_service.upsert_points(points)
            logger.info(f"Successfully seeded {len(points)} points to Qdrant")
        else:
            logger.warning("No points were seeded to Qdrant")

    def _process_url(self, url: str, idx: int) -> Optional[PointStruct]:
        """Process a single URL and create a Qdrant point."""
        logger.info(f"Processing URL {idx}: {url}")

        try:
            # Get text content
            text = self._scraper.get_text_from_url(url)
            if not text:
                logger.warning(f"Failed to extract text from {url}")
                return None

            # Get embedding
            embedding = self._embedding_service.get_embedding(text)
            if not embedding:
                logger.warning(f"Failed to get embedding for {url}")
                return None

            # Get title
            title = self._scraper.get_title_from_url(url)

            # Create point
            point = PointStruct(
                id=idx,
                vector=embedding,
                payload={
                    "title": title,
                    "url": url,
                    "text": text[:settings.max_text_length],
                    "source": "owasp-top-10",
                    "lang": "general",  # General security rules applicable to all languages
                    "ingested_at": datetime.utcnow().isoformat(),
                }
            )

            logger.info(f"Successfully processed: {title[:50]}")
            return point

        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            raise ScrapingError(f"Failed to process {url}: {str(e)}")

    def get_seed_status(self, seed_id: str) -> Optional[dict]:
        """Get status of a seed operation."""
        return self._seed_status.get(seed_id)

    def get_seed_history(self, limit: int = 10) -> list:
        """Get seed operation history."""
        items = list(self._seed_status.values())
        items.sort(key=lambda x: x.get("started_at", ""), reverse=True)
        return items[:limit]
