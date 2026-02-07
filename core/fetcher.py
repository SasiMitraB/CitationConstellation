import ads
import arxiv
import os
import time

class PaperMetadata:
    def __init__(self, title, authors, year, doi, arxiv_id, bibcode):
        self.title = title
        self.authors = authors # list of strings
        self.year = year
        self.doi = doi
        self.arxiv_id = arxiv_id
        self.bibcode = bibcode

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
                    bibcode=p.bibcode
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
                bibcode=None 
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
                    bibcode=p.bibcode
                ))
            return citation_list
        except Exception as e:
            print(f"Warning: ADS citations query failed ({e}) on attempt {attempt+1}/{max_retries}")
            if "503" in str(e) or "Service Temporarily Unavailable" in str(e):
                 time.sleep(2 * (attempt + 1))
            else:
                 raise RuntimeError(f"Failed to fetch citations from ADS: {e}")
    
    raise RuntimeError("Failed to fetch citations from ADS after retries.")

