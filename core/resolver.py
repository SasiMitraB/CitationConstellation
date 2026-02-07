import re
import urllib.parse

class PaperID:
    def __init__(self, id_type, id_value):
        self.type = id_type  # 'arxiv', 'doi', 'ads_bibcode', 'openalex'
        self.value = id_value

    def __repr__(self):
        return f"PaperID(type='{self.type}', value='{self.value}')"

def resolve_paper_id(input_str):
    """
    Parses an input string to identify if it is an arXiv ID, DOI, ADS URL, or OpenAlex URL/ID.
    Returns a PaperID object or raises ValueError.
    """
    input_str = input_str.strip()

    # defined regex patterns
    arxiv_pattern = r'(\d{4}\.\d{4,5}(v\d+)?)'
    doi_pattern = r'(10\.\d{4,9}/[-._;()/:A-Z0-9]+)'
    ads_url_pattern = r'ui\.adsabs\.harvard\.edu/abs/([^/\s]+)'
    openalex_url_pattern = r'openalex\.org/(?:works/)?(W\d+)'
    openalex_id_pattern = r'^(W\d+)$'

    # Check for OpenAlex URL first
    openalex_url_match = re.search(openalex_url_pattern, input_str, re.IGNORECASE)
    if openalex_url_match:
        openalex_id = openalex_url_match.group(1)
        return PaperID('openalex', openalex_id)

    # Check for ADS URL
    ads_match = re.search(ads_url_pattern, input_str, re.IGNORECASE)
    if ads_match:
        bibcode = urllib.parse.unquote(ads_match.group(1))
        return PaperID('ads_bibcode', bibcode)

    # Check for DOI
    # Handles pure DOI or URL-based DOI (doi.org/...)
    doi_match = re.search(doi_pattern, input_str, re.IGNORECASE)
    if doi_match:
        return PaperID('doi', doi_match.group(1))

    # Check for ArXiv ID
    # Handles pure ID or arxiv.org/abs/...
    arxiv_match = re.search(arxiv_pattern, input_str)
    if arxiv_match:
        return PaperID('arxiv', arxiv_match.group(1))

    # Check for standalone OpenAlex ID (e.g., W4391876328)
    openalex_id_match = re.match(openalex_id_pattern, input_str)
    if openalex_id_match:
        return PaperID('openalex', openalex_id_match.group(1))

    raise ValueError(f"Could not resolve input '{input_str}' to a known paper identifier (DOI, arXiv, ADS, OpenAlex).")

if __name__ == "__main__":
    # Simple manual test
    inputs = [
        "2103.02607",
        "https://arxiv.org/abs/2103.02607",
        "doi:10.1093/mnras/stab1234",
        "https://doi.org/10.1093/mnras/stab1234",
        "https://ui.adsabs.harvard.edu/abs/2021MNRAS.505.5686B/abstract"
    ]
    for i in inputs:
        try:
            print(f"'{i}' -> {resolve_paper_id(i)}")
        except ValueError as e:
            print(e)
