import logging
import re
from typing import List, Optional, Set
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from .config import settings
from .exceptions import ScrapingError

logger = logging.getLogger(__name__)


class WebScraper:
    """Service for scraping web pages and discovering nested links."""

    def __init__(self):
        self._visited_urls: Set[str] = set()
        self._pages_count: int = 0

    def get_text_from_url(self, url: str) -> str:
        """Extract text content from a web page."""
        try:
            headers = {
                "User-Agent": settings.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }

            response = requests.get(url, headers=headers, timeout=settings.request_timeout)
            response.raise_for_status()

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
            raise ScrapingError(error_msg)

    def get_html_content(self, url: str) -> str:
        """Fetch and return raw HTML content from a web page."""
        try:
            headers = {
                "User-Agent": settings.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }

            response = requests.get(url, headers=headers, timeout=settings.request_timeout)
            response.raise_for_status()

            html_content = response.text
            logger.info(f"Fetched {len(html_content)} characters of HTML from {url}")
            return html_content

        except Exception as e:
            error_msg = f"Error fetching HTML from {url}: {e}"
            logger.error(error_msg)
            raise ScrapingError(error_msg)

    def _clean_text(self, text: str) -> str:
        """Clean up extracted text."""
        # Remove excessive whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        cleaned_text = "\n".join(chunk for chunk in chunks if chunk)

        return cleaned_text

    def find_nested_links(
        self,
        base_url: str,
        html_content: str,
        max_depth: int = 1,
        current_depth: int = 0
    ) -> List[str]:
        """Find nested links within a page."""
        logger.debug(f"Starting nested link search from {base_url}, depth {current_depth}/{max_depth}")

        if current_depth >= max_depth:
            logger.debug(f"Skipping nested search: reached max depth {max_depth}")
            return []

        if self._pages_count >= settings.max_pages_per_domain:
            logger.warning(f"Skipping nested search: reached max pages limit {settings.max_pages_per_domain}")
            return []

        try:
            if not html_content:
                logger.warning(f"No HTML content provided for nested link search from {base_url}")
                return []

            soup = BeautifulSoup(html_content, "html.parser")

            # Find all links in the page
            all_links = soup.find_all("a", href=True)
            logger.info(f"Found {len(all_links)} total <a> tags on {base_url}")

            links = []
            rejected_count = 0
            duplicate_count = 0
            internal_count = 0

            # Track canonical URLs to avoid duplicates
            canonical_urls = set()

            for link in all_links:
                href = link.get("href", "").strip()
                if not href or href.startswith(("#")):
                    # Skip anchors and empty hrefs
                    continue

                # Resolve relative URLs
                absolute_url = urljoin(base_url, href)

                # Generate canonical URL to avoid duplicates
                canonical_url = self._get_canonical_url(absolute_url)

                # Avoid duplicates using canonical URL
                if canonical_url in canonical_urls:
                    duplicate_count += 1
                    logger.debug(f"Duplicate URL (canonical): {absolute_url}")
                    continue
                if absolute_url in self._visited_urls:
                    duplicate_count += 1
                    logger.debug(f"Duplicate URL (exact): {absolute_url}")
                    continue

                canonical_urls.add(canonical_url)

                # Filter out invalid URLs
                if not self._is_valid_url(absolute_url, base_url):
                    rejected_count += 1
                    logger.debug(f"Rejected URL: {absolute_url}")
                    continue

                self._visited_urls.add(absolute_url)
                self._pages_count += 1
                links.append(absolute_url)
                internal_count += 1

            logger.info(
                f"Found {len(links)} nested links at depth {current_depth + 1} from {base_url}: "
                f"{internal_count} internal, {rejected_count} rejected, {duplicate_count} duplicates"
            )

            return links

        except Exception as e:
            logger.error(f"Error finding nested links from {base_url}: {e}")
            return []

    def _get_canonical_url(self, url: str) -> str:
        """Generate canonical URL to avoid duplicates."""
        try:
            parsed = urlparse(url)

            # Remove tracking parameters and common query params
            query_params = []
            if parsed.query:
                from urllib.parse import parse_qs
                # Parse and filter query parameters
                params = parse_qs(parsed.query)
                # Remove tracking and duplicate params
                unwanted_params = {'utm_source', 'utm_medium', 'utm_campaign', 'ref', 'fbclid', 'gclid'}
                filtered_params = {k: v for k, v in params.items() if k not in unwanted_params and k}
                query_params = [f"{k}={v[0]}" for k, v in filtered_params.items()]

            # Remove fragments
            clean_url = urlunparse((
                parsed.scheme,
                parsed.netloc.lower(),  # Normalize domain
                parsed.path,  # Keep path as-is
                parsed.params,
                "&".join(query_params) if query_params else "",  # Clean query string
                ""  # Remove fragments
            ))

            return clean_url

        except Exception as e:
            logger.debug(f"Error canonicalizing URL {url}: {e}")
            return url.lower()

    def _is_valid_url(self, url: str, base_url: str) -> bool:
        """Check if URL is valid for scanning."""
        try:
            parsed = urlparse(url)
            base_parsed = urlparse(base_url)

            # Check for valid scheme
            if parsed.scheme not in ("http", "https"):
                return False

            # Filter out Cloudflare email protection URLs
            if "cdn-cgi/l/email-protection" in parsed.path.lower():
                logger.debug(f"URL {url} rejected - email protection")
                return False

            # Filter out language-specific pages (only keep English)
            # Common language codes: es, pt, ru, de, fr, it, ja, zh, ko, ar, tr, pl, cs, nl
            language_path_patterns = [
                r"/es/", r"/pt/", r"/ru/", r"/de/", r"/fr/", r"/it/", r"/ja/",
                r"/zh/", r"/ko/", r"/ar/", r"/tr/", r"/pl/", r"/cs/", r"/nl/",
                r"wiki\.owasp\.org",  # Skip wiki pages
            ]

            import re
            url_lower = url.lower()
            for pattern in language_path_patterns:
                if re.search(pattern, url_lower):
                    logger.debug(f"URL {url} rejected - non-English or wiki page")
                    return False

            # Filter out specific unwanted URLs
            unwanted_patterns = [
                "email-protection",
                "mailto:",
                "tel:",
                "#",  # Anchors
                "/cdn-cgi/",
                "/feed",
                "/rss",
                "/rss.xml",
                "*.pdf",
                "*.docx",
                "*.xlsx",
                "*.zip",
            ]

            for pattern in unwanted_patterns:
                if pattern.startswith("*"):
                    # File extension pattern
                    if url_lower.endswith(pattern[1:]):
                        logger.debug(f"URL {url} rejected - unwanted file type")
                        return False
                elif pattern in url_lower:
                    logger.debug(f"URL {url} rejected - unwanted pattern: {pattern}")
                    return False

            # Check domain restrictions
            if settings.follow_external_links:
                return True

            # Only allow same domain or internal patterns
            base_domain = base_parsed.netloc.lower()
            url_domain = parsed.netloc.lower()

            # Check if URL domain matches any allowed domain or pattern
            is_internal = (
                # Exact domain match
                url_domain in settings.allowed_domains or
                # Domain ends with allowed pattern
                any(url_domain.endswith(allowed) for allowed in settings.allowed_domains) or
                # URL path contains internal patterns
                any(pattern in url.lower() for pattern in settings.internal_url_patterns) or
                # Base domain matches
                url_domain == base_domain
            )

            if not is_internal:
                logger.debug(f"URL {url} rejected - not in internal domains: {url_domain}")

            return is_internal

        except Exception as e:
            logger.error(f"Error validating URL {url}: {e}")
            return False

    def get_title_from_url(self, url: str) -> str:
        """Extract readable title from URL."""
        try:
            # Get the last segment of the path
            path_parts = url.rstrip("/").split("/")

            # Try to use the last meaningful segment
            if len(path_parts) > 1:
                title_part = path_parts[-1]
            else:
                title_part = path_parts[0]

            # Clean up the title
            title = title_part.replace("_", " ").replace("-", " ").title()

            # If title is too short, use the whole URL
            if len(title) < 3:
                return url.replace("https://", "").replace("http://", "")

            return title

        except Exception:
            return url.replace("https://", "").replace("http://", "")

    def reset_counter(self):
        """Reset page counter for new seeding session."""
        self._visited_urls.clear()
        self._pages_count = 0

    @property
    def pages_count(self) -> int:
        """Get total pages processed."""
        return self._pages_count
