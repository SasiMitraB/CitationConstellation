"""
OpenAlex citation data source implementation.

Provides metadata and citation fetching using the OpenAlex API.
https://docs.openalex.org/
"""

import requests
import time
import urllib.parse
from core.fetcher import PaperMetadata


class OpenAlexError(Exception):
    """Raised when OpenAlex API operations fail."""
    pass


# Track last request time for rate limiting
_last_request_time = 0


def get_openalex_metadata(paper_id_obj, config):
    """
    Fetch metadata from OpenAlex for a given paper identifier.

    Args:
        paper_id_obj: PaperID instance (preferably DOI or ArXiv)
        config: OpenAlex source configuration dict

    Returns:
        PaperMetadata instance with OpenAlex data including topics

    Raises:
        OpenAlexError: If paper not found or API fails
    """
    base_url = config.get('base_url', 'https://api.openalex.org')

    # Build query URL based on identifier type
    if paper_id_obj.type == 'doi':
        # OpenAlex accepts DOI in URL path
        doi = paper_id_obj.value
        if doi.startswith('https://doi.org/'):
            doi = doi.replace('https://doi.org/', '')
        url = f"{base_url}/works/doi:{doi}"

    elif paper_id_obj.type == 'openalex':
        # Direct OpenAlex ID lookup
        openalex_id = paper_id_obj.value
        # Ensure it has the W prefix and uppercase it
        if not openalex_id.upper().startswith('W'):
            raise OpenAlexError(f"Invalid OpenAlex ID format: {openalex_id}. Should start with 'W'")
        openalex_id = openalex_id.upper()  # OpenAlex IDs are case-insensitive but uppercase is standard
        url = f"{base_url}/works/{openalex_id}"

    elif paper_id_obj.type == 'arxiv':
        # OpenAlex doesn't have a direct arXiv ID filter
        # ArXiv papers need to be looked up by DOI (if published) or searched by title
        # Better to fall back to ADS which can resolve arXiv IDs directly
        raise OpenAlexError("OpenAlex doesn't support direct arXiv ID lookup. Use DOI or try ADS fallback.")

    elif paper_id_obj.type == 'ads_bibcode':
        # OpenAlex doesn't support ADS bibcodes
        raise OpenAlexError(f"OpenAlex doesn't support ADS bibcodes. Paper needs DOI or ArXiv ID.")

    else:
        raise OpenAlexError(f"Unsupported identifier type for OpenAlex: {paper_id_obj.type}")

    # Make request
    try:
        work_json = _make_openalex_request(url, config)

        # Handle filter query response (returns results array)
        if 'results' in work_json:
            if not work_json['results']:
                raise OpenAlexError(f"No results found in OpenAlex for {paper_id_obj.type}:{paper_id_obj.value}")
            work_json = work_json['results'][0]

        # Parse into PaperMetadata
        return _parse_openalex_work(work_json, config)

    except OpenAlexError:
        raise
    except Exception as e:
        raise OpenAlexError(f"Error fetching metadata from OpenAlex: {e}")


def get_openalex_citations(metadata, config):
    """
    Fetch papers citing the given paper from OpenAlex.

    Args:
        metadata: PaperMetadata object (needs DOI or openalex_id)
        config: OpenAlex source configuration dict

    Returns:
        List of PaperMetadata objects representing citing papers

    Raises:
        OpenAlexError: If paper lacks required identifiers or API fails
    """
    base_url = config.get('base_url', 'https://api.openalex.org')
    max_results = config.get('max_results', 25)

    # Get OpenAlex ID
    openalex_id = None

    if hasattr(metadata, 'openalex_id') and metadata.openalex_id:
        openalex_id = metadata.openalex_id
    elif metadata.doi:
        # Query OpenAlex to get the OpenAlex ID from DOI
        doi = metadata.doi
        if doi.startswith('https://doi.org/'):
            doi = doi.replace('https://doi.org/', '')

        try:
            url = f"{base_url}/works/doi:{doi}"
            work_json = _make_openalex_request(url, config)
            openalex_id = work_json.get('id')
        except Exception as e:
            raise OpenAlexError(f"Failed to resolve DOI to OpenAlex ID: {e}")

    elif metadata.arxiv_id:
        # OpenAlex doesn't support direct arXiv lookups
        # If the paper only has arXiv ID, try to fall back to ADS
        raise OpenAlexError("Paper only has arXiv ID. OpenAlex requires DOI. Try ADS fallback.")

    if not openalex_id:
        raise OpenAlexError("Paper lacks DOI/arXiv ID/OpenAlex ID needed for OpenAlex citation search")

    # Extract just the ID part (e.g., "W1234567890" from "https://openalex.org/W1234567890")
    if openalex_id.startswith('https://openalex.org/'):
        openalex_id = openalex_id.replace('https://openalex.org/', '')

    # Query for citing papers
    try:
        url = f"{base_url}/works?filter=cites:{openalex_id}&per_page={max_results}&sort=publication_date:desc"
        response_json = _make_openalex_request(url, config)

        results = response_json.get('results', [])
        citing_papers = []

        for work in results:
            try:
                paper = _parse_openalex_work(work, config)
                citing_papers.append(paper)
            except Exception as e:
                print(f"Warning: Failed to parse citing paper: {e}")
                continue

        return citing_papers

    except OpenAlexError:
        raise
    except Exception as e:
        raise OpenAlexError(f"Error fetching citations from OpenAlex: {e}")


def _make_openalex_request(url, config, attempt=0):
    """
    Make rate-limited HTTP request to OpenAlex API with retry logic.

    Args:
        url: OpenAlex API URL
        config: OpenAlex source configuration
        attempt: Current retry attempt number

    Returns:
        dict: Parsed JSON response

    Raises:
        OpenAlexError: On persistent failures or non-retriable errors
    """
    global _last_request_time

    max_retries = config.get('max_retries', 3)
    rate_limit_seconds = config.get('rate_limit_seconds', 0.1)
    backoff_multiplier = config.get('backoff_multiplier', 2)
    email = config.get('polite_pool_email', 'user@example.com')

    # Rate limiting
    current_time = time.time()
    time_since_last = current_time - _last_request_time
    if time_since_last < rate_limit_seconds:
        time.sleep(rate_limit_seconds - time_since_last)

    # Set User-Agent for polite pool
    headers = {
        'User-Agent': f'CitationConstellation (mailto:{email})',
        'Accept': 'application/json'
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        _last_request_time = time.time()

        # Handle HTTP errors
        if response.status_code == 404:
            raise OpenAlexError(f"Paper not found in OpenAlex (404)")

        elif response.status_code == 429:
            # Rate limited
            if attempt < max_retries:
                wait_time = rate_limit_seconds * (backoff_multiplier ** attempt)
                print(f"Rate limited by OpenAlex, waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
                return _make_openalex_request(url, config, attempt + 1)
            else:
                raise OpenAlexError(f"Rate limited after {max_retries} retries")

        elif response.status_code >= 500:
            # Server error - retry
            if attempt < max_retries:
                wait_time = rate_limit_seconds * (backoff_multiplier ** attempt)
                print(f"OpenAlex server error ({response.status_code}), retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)
                return _make_openalex_request(url, config, attempt + 1)
            else:
                raise OpenAlexError(f"Server error after {max_retries} retries: {response.status_code}")

        elif response.status_code != 200:
            raise OpenAlexError(f"HTTP {response.status_code}: {response.text[:200]}")

        # Parse JSON
        return response.json()

    except requests.exceptions.RequestException as e:
        if attempt < max_retries:
            wait_time = rate_limit_seconds * (backoff_multiplier ** attempt)
            print(f"Request error: {e}, retrying in {wait_time:.1f}s...")
            time.sleep(wait_time)
            return _make_openalex_request(url, config, attempt + 1)
        else:
            raise OpenAlexError(f"Request failed after {max_retries} retries: {e}")


def _resolve_arxiv_id(work_json, config):
    """
    Attempt to find arXiv ID for a work using multiple strategies.

    Strategy 1: Check work's ids field
    Strategy 2: Check locations for arXiv URLs
    Strategy 3: Title search to find split records (works with same title)

    Args:
        work_json: OpenAlex work object (dict)
        config: OpenAlex config dict

    Returns:
        str: arXiv ID if found, None otherwise
    """
    # Strategy 1: Direct IDs field
    ids = work_json.get('ids', {})
    if 'arxiv' in ids and ids['arxiv']:
        arxiv_url = ids['arxiv']
        return arxiv_url.replace('https://arxiv.org/abs/', '')

    # Strategy 2: Check locations for arXiv URLs
    for loc in work_json.get('locations', []):
        if not loc:
            continue
        pdf_url = loc.get('pdf_url', '')
        landing_url = loc.get('landing_page_url', '')

        # Check if either URL contains arxiv.org
        for url in [pdf_url, landing_url]:
            if url and 'arxiv.org' in url:
                # Extract arXiv ID from URL
                # Handles: https://arxiv.org/abs/2103.12345 or https://arxiv.org/pdf/2103.12345.pdf
                import re
                match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)', url)
                if match:
                    return match.group(1)

    # Strategy 3: Title search for split records
    # This is more expensive, so only do it if we have a DOI and title
    title = work_json.get('title')
    doi = work_json.get('doi')

    if title and doi:
        try:
            base_url = config.get('base_url', 'https://api.openalex.org')
            email = config.get('polite_pool_email', 'user@example.com')

            # Search for works with same title
            search_param = urllib.parse.quote(f'"{title}"')
            search_url = f"{base_url}/works?filter=title.search:{search_param}"

            # Make a quick search request
            headers = {
                'User-Agent': f'CitationConstellation (mailto:{email})',
                'Accept': 'application/json'
            }

            response = requests.get(search_url, headers=headers, timeout=10)
            if response.status_code == 200:
                results = response.json().get('results', [])

                # Look through results for one with arXiv ID
                for res in results:
                    # Skip if it's the same work we already have
                    if res.get('id') == work_json.get('id'):
                        continue

                    # Check if this result has arXiv ID
                    res_ids = res.get('ids', {})
                    if 'arxiv' in res_ids and res_ids['arxiv']:
                        arxiv_url = res_ids['arxiv']
                        return arxiv_url.replace('https://arxiv.org/abs/', '')

                    # Check locations of this result
                    for loc in res.get('locations', []):
                        if not loc:
                            continue
                        url = loc.get('pdf_url') or loc.get('landing_page_url')
                        if url and 'arxiv.org' in url:
                            import re
                            match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)', url)
                            if match:
                                return match.group(1)

        except Exception as e:
            # Don't fail the whole parsing if title search fails
            pass

    return None


def _parse_openalex_work(work_json, config=None):
    """
    Convert OpenAlex work JSON to PaperMetadata object.

    Args:
        work_json: OpenAlex work object (dict)

    Returns:
        PaperMetadata instance with extended fields
    """
    # Extract basic fields
    title = work_json.get('title', 'Unknown Title')

    # Authors
    authorships = work_json.get('authorships', [])
    authors = []
    for authorship in authorships:
        author = authorship.get('author', {})
        display_name = author.get('display_name')
        if display_name:
            authors.append(display_name)

    # Year
    year = work_json.get('publication_year')

    # DOI - clean it
    doi = work_json.get('doi')
    if doi and doi.startswith('https://doi.org/'):
        doi = doi.replace('https://doi.org/', '')

    # ArXiv ID - use advanced resolver if config provided
    arxiv_id = None
    if config:
        arxiv_id = _resolve_arxiv_id(work_json, config)
    else:
        # Fallback to simple extraction if no config
        ids = work_json.get('ids', {})
        if 'arxiv' in ids and ids['arxiv']:
            arxiv_id = ids['arxiv'].replace('https://arxiv.org/abs/', '')

    # Bibcode - not available in OpenAlex
    bibcode = None

    # OpenAlex ID
    openalex_id = work_json.get('id')

    # Topics (new field)
    topics_raw = work_json.get('topics', [])
    topics = []
    for topic in topics_raw:
        topics.append({
            'display_name': topic.get('display_name', ''),
            'score': topic.get('score', 0.0)
        })

    # Citation count
    cited_by_count = work_json.get('cited_by_count', 0)

    # Abstract - reconstruct from inverted index
    abstract = None
    abstract_inverted_index = work_json.get('abstract_inverted_index')
    if abstract_inverted_index:
        # Reconstruct abstract from inverted index
        # Format: {"word": [position1, position2], ...}
        word_positions = []
        for word, positions in abstract_inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))

        # Sort by position and join
        word_positions.sort(key=lambda x: x[0])
        abstract = ' '.join([word for pos, word in word_positions])

    # Create extended PaperMetadata
    # We'll need to update PaperMetadata class to accept these fields
    metadata = PaperMetadata(
        title=title,
        authors=authors,
        year=year,
        doi=doi,
        arxiv_id=arxiv_id,
        bibcode=bibcode,
        abstract=abstract
    )

    # Add extended fields (these will be added to PaperMetadata class)
    metadata.openalex_id = openalex_id
    metadata.topics = topics
    metadata.cited_by_count = cited_by_count
    metadata.source = 'openalex'

    return metadata
