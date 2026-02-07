import ads
import arxiv
import os
import time

class PaperMetadata:
    def __init__(self, title, authors, year, doi, arxiv_id, bibcode,
                 openalex_id=None, topics=None, cited_by_count=None, source=None, abstract=None):
        self.title = title
        self.authors = authors # list of strings
        self.year = year
        self.doi = doi
        self.arxiv_id = arxiv_id
        self.bibcode = bibcode
        self.openalex_id = openalex_id  # OpenAlex work ID (e.g., 'https://openalex.org/W...')
        self.topics = topics or []       # List of {'display_name': str, 'score': float}
        self.cited_by_count = cited_by_count  # Total citation count
        self.source = source             # Data source: 'ads', 'openalex', or 'arxiv'
        self.abstract = abstract         # Abstract text

    def __repr__(self):
        return f"<Paper: {self.title} ({self.year})>"

def get_paper_metadata(paper_id_obj):
    """
    Fetches metadata for a given PaperID object.
    Tries to resolve everything to an ADS Bibcode or arXiv ID to get full info.
    """
    
    # Try to use ADS first if possible, as it gives us the Bibcode which is crucial for citations.
    # Even if it's an arXiv ID, ADS can resolve it.
    
    token = os.environ.get("ADS_API_TOKEN") or os.environ.get("ADS_TOKEN")
    if token:
        ads.config.token = token.strip()
        print("Loaded ADS token from environment variable")
    else:
        print("Warning: ADS_API_TOKEN not set. ADS requests may fail.")

    q_str = ""
    if paper_id_obj.type == 'arxiv':
        q_str = f"identifier:arxiv:{paper_id_obj.value}"
    elif paper_id_obj.type == 'doi':
        q_str = f"doi:{paper_id_obj.value}"
    elif paper_id_obj.type == 'ads_bibcode':
        q_str = f"bibcode:{paper_id_obj.value}"
    
    # Try ADS Search with retries
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Rate limit
            time.sleep(1)
            
            # We query for specific fields
            papers = list(ads.SearchQuery(q=q_str, fl=['title', 'author', 'year', 'doi', 'arxiv_class', 'bibcode', 'identifier']))
            
            if papers:
                p = papers[0]
                # extract arxiv id from identifiers if possible
                arxiv_id = None
                if p.identifier:
                    for ident in p.identifier:
                        if ident.startswith("arXiv:"):
                            arxiv_id = ident.replace("arXiv:", "")
                            break
                
                # If we started with an arxiv ID and ADS didn't give one back
                if not arxiv_id and paper_id_obj.type == 'arxiv':
                    arxiv_id = paper_id_obj.value

                return PaperMetadata(
                    title=p.title[0] if p.title else "Unknown Title",
                    authors=p.author if p.author else [],
                    year=p.year,
                    doi=p.doi[0] if p.doi else None,
                    arxiv_id=arxiv_id,
                    bibcode=p.bibcode,
                    source='ads'
                )
            else:
                # No papers found, break loop to fall back
                break
                
        except Exception as e:
            print(f"Warning: ADS query failed ({e}) on attempt {attempt+1}/{max_retries}")
            if "503" in str(e) or "Service Temporarily Unavailable" in str(e):
                time.sleep(2 * (attempt + 1)) # Backoff
            else:
                break # Non-retriable error?

    # Fallback to ArXiv library if ADS failed or didn't find it
    if paper_id_obj.type == 'arxiv':
        search = arxiv.Search(id_list=[paper_id_obj.value])
        try:
            res = next(search.results())
            authors = [a.name for a in res.authors]
            return PaperMetadata(
                title=res.title,
                authors=authors,
                year=res.published.year,
                doi=res.doi,
                arxiv_id=paper_id_obj.value,
                bibcode=None,
                source='arxiv'
            )
        except StopIteration:
            raise ValueError(f"ArXiv ID {paper_id_obj.value} not found in ArXiv either.")
    
    raise ValueError(f"Could not resolve metadata for {paper_id_obj}.")

    # Old code below is removed/replaced
    # ...



def get_citations(bibcode):
    """
    Finds papers citing the given bibcode using ADS.
    Returns a list of PaperMetadata objects (up to 25).
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            time.sleep(1) # Rate limit
            q = ads.SearchQuery(q=f"citations(bibcode:{bibcode})", fl=['title', 'author', 'year', 'doi', 'bibcode', 'identifier'], rows=25, sort="date desc")
            citation_list = []
            for p in q:
                arxiv_id = None
                if p.identifier:
                    for ident in p.identifier:
                        if ident.startswith("arXiv:"):
                            arxiv_id = ident.replace("arXiv:", "")
                            break
                
                citation_list.append(PaperMetadata(
                    title=p.title[0] if p.title else "Unknown Title",
                    authors=p.author if p.author else [],
                    year=p.year,
                    doi=p.doi[0] if p.doi else None,
                    arxiv_id=arxiv_id,
                    bibcode=p.bibcode,
                    source='ads'
                ))
            return citation_list
        except Exception as e:
            print(f"Warning: ADS citations query failed ({e}) on attempt {attempt+1}/{max_retries}")
            if "503" in str(e) or "Service Temporarily Unavailable" in str(e):
                 time.sleep(2 * (attempt + 1))
            else:
                 raise RuntimeError(f"Failed to fetch citations from ADS: {e}")
    
    raise RuntimeError("Failed to fetch citations from ADS after retries.")


def get_paper_metadata_multi_source(paper_id_obj, preferred_source=None):
    """
    Fetch metadata using configured or specified source.

    Args:
        paper_id_obj: PaperID instance
        preferred_source: 'ads' or 'openalex' (overrides config)

    Returns:
        PaperMetadata instance

    Raises:
        ValueError: If paper cannot be found in any source
    """
    from core.config import load_config, get_default_source
    from core.openalex_fetcher import get_openalex_metadata, OpenAlexError

    config = load_config()
    source = preferred_source or get_default_source(config)

    if source == 'ads':
        try:
            return get_paper_metadata(paper_id_obj)
        except Exception as e:
            print(f"ADS failed: {e}")
            print("Trying OpenAlex fallback...")
            try:
                source_config = config['sources']['openalex']
                return get_openalex_metadata(paper_id_obj, source_config)
            except Exception as e2:
                raise ValueError(f"Both ADS and OpenAlex failed. ADS: {e}, OpenAlex: {e2}")

    elif source == 'openalex':
        try:
            source_config = config['sources']['openalex']
            return get_openalex_metadata(paper_id_obj, source_config)
        except OpenAlexError as e:
            print(f"OpenAlex failed: {e}")
            print("Trying ADS fallback...")
            try:
                return get_paper_metadata(paper_id_obj)
            except Exception as e2:
                raise ValueError(f"Both OpenAlex and ADS failed. OpenAlex: {e}, ADS: {e2}")
    else:
        raise ValueError(f"Unknown source: {source}")


def get_citations_multi_source(metadata, preferred_source=None):
    """
    Fetch citations using configured or specified source.

    Intelligently routes based on available identifiers:
    - ADS requires bibcode
    - OpenAlex requires DOI or openalex_id

    Args:
        metadata: PaperMetadata object
        preferred_source: 'ads' or 'openalex' (overrides config)

    Returns:
        List of PaperMetadata objects

    Raises:
        RuntimeError: If citation fetching fails
    """
    from core.config import load_config, get_default_source
    from core.openalex_fetcher import get_openalex_citations, OpenAlexError

    config = load_config()
    source = preferred_source or get_default_source(config)

    if source == 'ads':
        if not metadata.bibcode:
            print("No bibcode available for ADS, using OpenAlex...")
            try:
                source_config = config['sources']['openalex']
                return get_openalex_citations(metadata, source_config)
            except Exception as e:
                print(f"OpenAlex fallback failed: {e}")
                return []
        try:
            return get_citations(metadata.bibcode)
        except Exception as e:
            print(f"ADS citations failed: {e}")
            print("Trying OpenAlex fallback...")
            try:
                source_config = config['sources']['openalex']
                return get_openalex_citations(metadata, source_config)
            except Exception as e2:
                raise RuntimeError(f"Both ADS and OpenAlex failed for citations. ADS: {e}, OpenAlex: {e2}")

    elif source == 'openalex':
        if not metadata.doi and not metadata.openalex_id and not metadata.arxiv_id:
            print("No DOI/OpenAlex ID/ArXiv ID available for OpenAlex, using ADS...")
            if metadata.bibcode:
                try:
                    return get_citations(metadata.bibcode)
                except Exception as e:
                    print(f"ADS fallback failed: {e}")
                    return []
            else:
                print("No bibcode either, cannot fetch citations.")
                return []

        try:
            source_config = config['sources']['openalex']
            return get_openalex_citations(metadata, source_config)
        except OpenAlexError as e:
            print(f"OpenAlex citations failed: {e}")
            if metadata.bibcode:
                print("Trying ADS fallback...")
                try:
                    return get_citations(metadata.bibcode)
                except Exception as e2:
                    raise RuntimeError(f"Both OpenAlex and ADS failed for citations. OpenAlex: {e}, ADS: {e2}")
            else:
                raise RuntimeError(f"OpenAlex failed and no bibcode for ADS fallback: {e}")
    else:
        raise ValueError(f"Unknown source: {source}")

