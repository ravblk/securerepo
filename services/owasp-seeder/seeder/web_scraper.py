import logging
import re
from typing import List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs

import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import settings
from .exceptions import ScrapingError, ContentQualityError

logger = logging.getLogger(__name__)


class WebScraper:
    """Скрейпер с извлечением основного контента и фильтрацией UI-хрома."""

    # ---------- 1. Что удаляем из DOM ----------

    BOILERPLATE_TAGS = (
        "script", "style", "noscript", "iframe", "form", "button",
        "select", "option", "template", "dialog", "svg", "canvas",
        "nav", "aside",
    )

    BOILERPLATE_ROLES = (
        "navigation", "banner", "complementary", "search", "menu",
        "menubar", "dialog", "alert", "alertdialog", "contentinfo",
    )

    # Токен в class/id в границах слова: "sidebar" уберёт, "shared" — нет
    _CLASS_NOISE_RE = re.compile(
        r"(?:^|[-_ ])(nav|navbar|sidebar|menu|breadcrumb|cookie|banner|"
        r"modal|popup|skip-?link|widget|social|share|pagination|toolbar|toc)"
        r"(?:$|[-_ ])",
        re.IGNORECASE,
    )

    # Служебные селекторы конкретных движков
    _NOISE_SELECTORS = (
        ".mw-editsection", ".printfooter", "#catlinks", ".mw-jump-link",  # MediaWiki
        "#toc", ".toc", ".headerlink", ".md-skip",                         # MkDocs Material
    )

    # ---------- 2. Где ищем основной контент ----------

    DOMAIN_CONTENT_SELECTORS = {
        "cwe.mitre.org": (".mw-body", "#content", "#mw-content-text"),
        "scs.owasp.org": ("article .md-content", "article"),
        "top10.owasp.org": ("main", "article"),
        "cheatsheetseries.owasp.org": ("article .md-content", "article"),
    }
    GENERIC_CONTENT_SELECTORS = (
        "main", "article", "[role='main']", "#content", ".content", "#main",
    )

    # ---------- 3. Построчный фильтр UI-текста ----------

    _UI_LINE_RES = tuple(
        re.compile(p, re.IGNORECASE) for p in (
            r"^skip to (main )?content$",
            r"^you signed (in|out) in another tab",
            r"^you switched accounts",
            r"^reload to refresh your session\.?$",
            r"^dismiss( this)? alert$",
            r"^(sign in|sign up|sign out|log in|log out)$",
            r"^copy( code)?$",
            r"^(fork|star|watch)(\s+\d+)?$",
            r"^\d+\s*(forks?|stars?|commits?|contributors?|issues?)$",
            r"^(home|about|learn|faqs?|glossary|documents|videos)$",
            r"^common weakness enumeration$",
            r"^a community-developed list of",
            r"^last updated[: ]",
            r"^[▾▸▼►◄▲]+$",
        )
    )

    # 2+ совпадения → страница это UI, а не контент
    _PAGE_SIGNALS = (
        "skip to content", "reload to refresh your session",
        "you signed in", "you signed out", "dismiss alert", "fork", "star",
    )

    _ACRONYMS = {"cwe", "scwe", "owasp", "ssrf", "csrf", "xss", "sql", "api", "tls"}

    _GITHUB_BLOB_RE = re.compile(
        r"^https?://(?:www\.)?github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)"
        r"/blob/(?P<ref>[^/]+)/(?P<path>.+)$"
    )

    def __init__(self):
        self._visited_urls: Set[str] = set()   # храним КАНОНИЧЕСКИЕ url
        self._pages_count: int = 0
        self._session = self._make_session()

    # ---------------------------------------------------------------- HTTP

    @staticmethod
    def _make_session() -> requests.Session:
        retry = Retry(
            total=3, backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        s = requests.Session()
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        return s

    def _headers(self) -> dict:
        return {
            "User-Agent": settings.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    # ------------------------------------------------------------ Публичное

    def get_text_from_url(self, url: str) -> str:
        """Извлечь основной текст страницы без UI-хрома.

        GitHub blob-ссылки автоматически конвертируются в raw.githubusercontent —
        вместо HTML-обвязки («You signed in…», «Fork», «Copy code») получаем
        чистое содержимое файла.
        """
        raw_url = self._github_raw_url(url)
        if raw_url:
            return self._get_raw_text(raw_url)

        try:
            response = self._session.get(
                url, headers=self._headers(), timeout=settings.request_timeout
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")
            self._remove_boilerplate(soup)

            node, used_fallback = self._find_main_content(soup, url)

            # Ни один селектор контента не сработал, а body почти целиком из ссылок
            # → это меню/дашборд, индексировать нечего
            if used_fallback and self._link_density(node) > 0.6:
                raise ContentQualityError(
                    f"No main content on {url} (link density too high)"
                )

            text = self._clean_text(self._drop_ui_lines(node.get_text(separator="\n")))

            if self._is_boilerplate_page(text):
                raise ContentQualityError(f"UI boilerplate detected: {url}")
            if len(text) < 100:
                raise ContentQualityError(f"Too short ({len(text)} chars): {url}")

            logger.info(f"Extracted {len(text)} chars from {url}")
            return text

        except ScrapingError:
            raise
        except Exception as e:
            error_msg = f"Error fetching {url}: {e}"
            logger.error(error_msg)
            raise ScrapingError(error_msg)

    def get_html_content(self, url: str) -> str:
        """Fetch raw HTML."""
        try:
            response = self._session.get(
                url, headers=self._headers(), timeout=settings.request_timeout
            )
            response.raise_for_status()
            logger.info(f"Fetched {len(response.text)} chars of HTML from {url}")
            return response.text
        except Exception as e:
            error_msg = f"Error fetching HTML from {url}: {e}"
            logger.error(error_msg)
            raise ScrapingError(error_msg)

    # ----------------------------------------------------- Очистка DOM

    def _remove_boilerplate(self, soup: BeautifulSoup) -> None:
        for tag in soup.find_all(self.BOILERPLATE_TAGS):
            tag.decompose()

        for tag in soup.find_all(attrs={"role": list(self.BOILERPLATE_ROLES)}):
            tag.decompose()

        for tag in soup.find_all(attrs={"aria-hidden": "true"}):
            tag.decompose()

        for sel in self._NOISE_SELECTORS:
            for tag in soup.select(sel):
                tag.decompose()

        for tag in soup.find_all(class_=self._CLASS_NOISE_RE):
            tag.decompose()
        for tag in soup.find_all(id=self._CLASS_NOISE_RE):
            tag.decompose()

        # <header>/<footer> удаляем только на уровне страницы:
        # <article><header><h1>… — это заголовок правила, его сохраняем
        for name in ("header", "footer"):
            for tag in soup.find_all(name):
                if not tag.find_parent(("article", "main", "section")):
                    tag.decompose()

    def _find_main_content(self, soup: BeautifulSoup, url: str) -> Tuple[Tag, bool]:
        """Вернуть (узел основного контента, использован ли fallback на body)."""
        domain = urlparse(url).netloc.lower()
        selectors = (
            self.DOMAIN_CONTENT_SELECTORS.get(domain, ())
            + self.GENERIC_CONTENT_SELECTORS
        )
        for sel in selectors:
            node = soup.select_one(sel)
            if node is not None and len(node.get_text(strip=True)) >= 200:
                return node, False
        return (soup.body or soup), True

    # ----------------------------------------------------- Фильтры текста

    @staticmethod
    def _link_density(node: Tag) -> float:
        text = node.get_text(strip=True) or ""
        if not text:
            return 1.0
        link_text = "".join(a.get_text(strip=True) for a in node.find_all("a"))
        return len(link_text) / len(text)

    @classmethod
    def _drop_ui_lines(cls, text: str) -> str:
        kept = []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if any(rx.match(s) for rx in cls._UI_LINE_RES):
                continue
            if len(s) <= 2 and not s.isalnum():  # "►", "¶", "—"
                continue
            kept.append(s)
        return "\n".join(kept)

    @staticmethod
    def _clean_text(text: str) -> str:
        text = re.sub(r"[ \t]+", " ", text)
        lines = (line.strip() for line in text.splitlines())
        return re.sub(r"\n{3,}", "\n\n", "\n".join(l for l in lines if l))

    @classmethod
    def _is_boilerplate_page(cls, text: str) -> bool:
        low = text.lower()
        return sum(1 for s in cls._PAGE_SIGNALS if s in low) >= 2

    @staticmethod
    def truncate_at_boundary(text: str, limit: int) -> str:
        """Обрезать по границе предложения/слова, а не посреди слова."""
        if len(text) <= limit:
            return text
        cut = text[:limit]
        for sep in (". ", ".\n", "\n\n", "\n"):
            idx = cut.rfind(sep)
            if idx >= limit // 2:
                return cut[:idx].rstrip()
        return cut[: cut.rfind(" ")].rstrip() + "…"

    # ----------------------------------------------------- GitHub raw

    @classmethod
    def _github_raw_url(cls, url: str) -> Optional[str]:
        """github.com/o/r/blob/branch/path → raw.githubusercontent.com/o/r/branch/path"""
        m = cls._GITHUB_BLOB_RE.match(url)
        if not m:
            return None
        return (
            f"https://raw.githubusercontent.com/"
            f"{m['owner']}/{m['repo']}/{m['ref']}/{m['path']}"
        )

    def _get_raw_text(self, url: str) -> str:
        try:
            response = self._session.get(
                url, headers=self._headers(), timeout=settings.request_timeout
            )
            response.raise_for_status()
            logger.info(f"Fetched raw file ({len(response.text)} chars) from {url}")
            return response.text
        except Exception as e:
            raise ScrapingError(f"Error fetching raw file {url}: {e}")

    # ----------------------------------------------------- Ссылки

    def find_nested_links(self, base_url, html_content, max_depth=1, current_depth=0):
        """Find nested links within a page."""
        if current_depth >= max_depth:
            return []
        if self._pages_count >= settings.max_pages_per_domain:
            logger.warning(f"Page limit reached: {settings.max_pages_per_domain}")
            return []
        if not html_content:
            return []

        try:
            soup = BeautifulSoup(html_content, "lxml")
            all_links = soup.find_all("a", href=True)

            links: List[str] = []
            rejected = duplicates = 0

            for link in all_links:
                href = (link.get("href") or "").strip()
                if not href or href.startswith("#"):
                    continue

                absolute_url = urljoin(base_url, href)
                canonical_url = self._get_canonical_url(absolute_url)

                # Дедуп по каноническому URL — и в рамках страницы, и глобально
                # (раньше _visited_urls хранил точные URL: ?utm=x обходил дедуп)
                if canonical_url in self._visited_urls:
                    duplicates += 1
                    continue
                if not self._is_valid_url(absolute_url, base_url):
                    rejected += 1
                    continue

                self._visited_urls.add(canonical_url)
                self._pages_count += 1
                links.append(absolute_url)

            logger.info(
                f"find_nested_links[{base_url}]: {len(links)} accepted, "
                f"{rejected} rejected, {duplicates} duplicates"
            )
            return links

        except Exception as e:
            logger.error(f"Error finding nested links from {base_url}: {e}")
            return []

    @staticmethod
    def _get_canonical_url(url: str) -> str:
        try:
            parsed = urlparse(url)

            query_params = []
            if parsed.query:
                params = parse_qs(parsed.query)
                unwanted = {"utm_source", "utm_medium", "utm_campaign",
                            "ref", "fbclid", "gclid"}
                filtered = {k: v for k, v in params.items() if k not in unwanted and k}
                query_params = [f"{k}={v[0]}" for k, v in filtered.items()]

            # ФИКС: 'https://site//path' → 'https://site/path'
            path = re.sub(r"/{2,}", "/", parsed.path or "/")

            return urlunparse((
                parsed.scheme,
                parsed.netloc.lower(),
                path,
                parsed.params,
                "&".join(query_params) if query_params else "",
                "",
            ))
        except Exception as e:
            logger.debug(f"Error canonicalizing URL {url}: {e}")
            return url.lower()

    def _is_valid_url(self, url: str, base_url: str) -> bool:
        """Check if URL is valid for scanning. (Без изменений, кроме чистки импортов)"""
        try:
            parsed = urlparse(url)
            base_parsed = urlparse(base_url)

            if parsed.scheme not in ("http", "https"):
                return False
            if "cdn-cgi/l/email-protection" in parsed.path.lower():
                return False

            language_path_patterns = [
                r"/es/", r"/pt/", r"/ru/", r"/de/", r"/fr/", r"/it/", r"/ja/",
                r"/zh/", r"/zh-Hant/", r"/zh-hant/", r"/ko/", r"/ar/", r"/tr/",
                r"/pl/", r"/cs/", r"/nl/",
                r"\.zh-Hant\.", r"\.zh-hant\.",
                r"wiki\.owasp\.org",
            ]
            url_lower = url.lower()
            for pattern in language_path_patterns:
                if re.search(pattern, url_lower):
                    return False

            unwanted_patterns = [
                "email-protection", "mailto:", "tel:", "/cdn-cgi/",
                "/feed", "/rss", "/rss.xml", "*.pdf", "*.docx", "*.xlsx", "*.zip",
            ]
            for pattern in unwanted_patterns:
                if pattern.startswith("*"):
                    if url_lower.endswith(pattern[1:]):
                        return False
                elif pattern in url_lower:
                    return False

            if settings.follow_external_links:
                return True

            base_domain = base_parsed.netloc.lower()
            url_domain = parsed.netloc.lower()
            is_internal = (
                url_domain in settings.allowed_domains
                or any(url_domain.endswith(a) for a in settings.allowed_domains)
                or any(p in url_lower for p in settings.internal_url_patterns)
                or url_domain == base_domain
            )
            return is_internal

        except Exception as e:
            logger.error(f"Error validating URL {url}: {e}")
            return False

    # ----------------------------------------------------- Заголовки/ID

    def get_title_from_url(self, url: str) -> str:
        """Извлечь читаемый заголовок, НЕ ломая ID правил.

        Раньше .title() давал '377.Html' и 'Scwe 025' — источник битых rule_id.
        """
        parsed = urlparse(url)
        path_parts = parsed.path.rstrip("/").split("/")
        title_part = path_parts[-1] if len(path_parts) > 1 else parsed.netloc

        # cwe.mitre.org/.../377.html → 'CWE-377'
        if "cwe.mitre.org" in parsed.netloc.lower():
            m = re.match(r"(\d+)\.s?html?$", title_part, re.IGNORECASE)
            if m:
                return f"CWE-{m.group(1)}"

        # 'SCWE-025' остаётся 'SCWE-025', а не 'Scwe 025'
        m = re.match(r"^(SCWE|CWE)[- _]?(\d+)$", title_part, re.IGNORECASE)
        if m:
            return f"{m.group(1).upper()}-{m.group(2)}"

        return self._smart_title(title_part)

    @classmethod
    def _smart_title(cls, raw: str) -> str:
        s = re.sub(r"\.\w{1,5}$", "", raw)  # убрать расширение файла
        words = [w for w in re.split(r"[-_ ]+", s) if w]
        if not words:
            return raw
        return " ".join(
            w.upper() if w.lower() in cls._ACRONYMS else w.capitalize()
            for w in words
        )

    def reset_counter(self):
        self._visited_urls.clear()
        self._pages_count = 0

    @property
    def pages_count(self) -> int:
        return self._pages_count