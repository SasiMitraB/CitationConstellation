from pylatexenc.latexwalker import LatexWalker, LatexMacroNode, LatexEnvironmentNode, LatexGroupNode, LatexCharsNode
import re
import os
import bibtexparser

class CitationContext:
    def __init__(self, section=None, subsection=None, subsubsection=None):
        self.section = section
        self.subsection = subsection
        self.subsubsection = subsubsection

    def __repr__(self):
        parts = []
        if self.section: parts.append(self.section)
        if self.subsection: parts.append(self.subsection)
        if self.subsubsection: parts.append(self.subsubsection)
        return " > ".join(parts) if parts else "Unknown Section"

def resolve_latex_inclusions(base_dir, tex_content, depth=0, max_depth=10):
    """
    Recursively resolves \\input{} and \\include{} commands by inlining the file content.
    """
    if depth > max_depth:
        return tex_content + f"\n% Max recursion depth reached\n"

    # Regex for \input{filename} or \include{filename}
    # Filenames might have .tex extension or not
    include_pattern = re.compile(r'\\(?:input|include)\{([^}]+)\}')
    
    def replace_match(match):
        filename = match.group(1).strip()
        if not filename.endswith('.tex'):
            filename += '.tex'
            
        file_path = os.path.join(base_dir, filename)
        
        # Security/Sanity check: ensure we stay within the source directory (roughly)
        # and that the file exists
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', errors='replace') as f:
                    included_content = f.read()
                # Recurse
                return resolve_latex_inclusions(base_dir, included_content, depth + 1, max_depth)
            except Exception as e:
                return f"% Error including {filename}: {e}"
        else:
            return f"% File not found: {filename}"

    return include_pattern.sub(replace_match, tex_content)

def get_ast(tex_content):
    """
    Parses LaTeX content into an AST using pylatexenc.
    """
    walker = LatexWalker(tex_content)
    (nodelist, pos, len_) = walker.get_latex_nodes()
    return nodelist

def _node_to_text(nodelist):
    # Simplistic text extraction from nodes
    text = ""
    # nodelist can be a list or a single node sometimes if we are not careful
    if not isinstance(nodelist, list):
        nodelist = [nodelist]
        
    for n in nodelist:
        if isinstance(n, LatexCharsNode):
            text += n.chars
        elif isinstance(n, LatexGroupNode):
            text += _node_to_text(n.nodelist)
        elif isinstance(n, LatexMacroNode):
            pass 
        elif hasattr(n, 'nodelist'):
             text += _node_to_text(n.nodelist)
    return text.strip()

def _extract_text_from_args(node):
    # node.nodeargs is a list of nodes (likely GroupNodes) or None
    if not node.nodeargs:
        return None
        
    # Pylatexenc parsing might return [None, None, GroupNode] for optional args.
    # We prioritize the last GroupNode as it usually contains the mandatory argument (title, keys).
    for arg in reversed(node.nodeargs):
        if arg is None:
            continue
        if isinstance(arg, LatexGroupNode):
            return _node_to_text(arg.nodelist)
        if isinstance(arg, LatexCharsNode):
             return arg.chars
    return None

def _extract_keys_from_cite(node):
    # node.nodeargs[0] contains the keys csv usually (or whichever arg has the keys)
    keys_str = _extract_text_from_args(node)
    if not keys_str:
        return []
    return [k.strip() for k in keys_str.split(',')]

def find_citations(nodelist, target_keys):
    """
    Walks the AST to find occurrences of \\cite{target_keys}.
    Returns a list of CitationContext objects.
    """
    citations_found = []
    
    # State tracking
    state = {
        'section': None,
        'subsection': None,
        'subsubsection': None
    }
    
    def _walk(nodes):
        for node in nodes:
            if isinstance(node, LatexMacroNode):
                # Check for section headers
                if node.macroname == 'section':
                    state['section'] = _extract_text_from_args(node)
                    state['subsection'] = None
                    state['subsubsection'] = None
                elif node.macroname == 'subsection':
                    state['subsection'] = _extract_text_from_args(node)
                    state['subsubsection'] = None
                elif node.macroname == 'subsubsection':
                    state['subsubsection'] = _extract_text_from_args(node)
                
                # Check for citations
                if 'cite' in node.macroname:
                    # Extract keys from arguments
                    cited_keys = _extract_keys_from_cite(node)
                    # Check intersection
                    if any(k in target_keys for k in cited_keys):
                        # Capture simplified context
                        citations_found.append(CitationContext(
                            section=state['section'],
                            subsection=state['subsection'],
                            subsubsection=state['subsubsection']
                        ))
            
            # Recurse
            if hasattr(node, 'nodelist') and node.nodelist:
                _walk(node.nodelist)
    
    _walk(nodelist)
    return citations_found

def parse_bib_file(bib_path):
    """
    Parses a .bib file and returns a dictionary of key -> title/doi.
    """
    with open(bib_path, 'r') as bibtex_file:
        bib_database = bibtexparser.load(bibtex_file)
    return bib_database.entries

def parse_bbl_file(bbl_path):
    """
    Parses a .bbl file to extract keys and text content.
    """
    entries = []
    try:
        with open(bbl_path, 'r', errors='ignore') as f:
            content = f.read()
            
        # Regex to find bibitems
        item_pattern = re.compile(r'\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}(.*?)(?=\\bibitem|\Z)', re.DOTALL)
        
        for match in item_pattern.finditer(content):
            key = match.group(1).strip()
            entry_content = match.group(2).strip()
            # Clean up LaTeX commands but keep content
            # e.g. \dodoi{10.123} -> 10.123
            # Just remove command names start with \
            entry_text = re.sub(r'\\[a-zA-Z]+', ' ', entry_content) 
            entry_text = re.sub(r'\{|\}', '', entry_text)
            entry_text = ' '.join(entry_text.split()) # normalize whitespace
            
            entries.append({'ID': key, 'text': entry_text.lower()})
            
    except Exception as e:
        print(f"Error parsing .bbl {bbl_path}: {e}")
        
    return entries

def find_key_for_paper(source_dir, target_doi=None, target_title=None, target_authors=None, target_year=None):
    """
    Scans for .bib or .bbl files in source_dir and tries to find the citation key 
    that matches the target paper's DOI, Title, or Author+Year.
    """
    target_doi_clean = target_doi.lower() if target_doi else None
    target_title_clean = target_title.lower()[:50] if target_title else None
    
    first_author_last_name = None
    if target_authors and len(target_authors) > 0:
        # Assuming format "Lastname, Firstname" or just "Lastname"
        first_author_last_name = target_authors[0].split(',')[0].strip().lower()
        
    target_year_str = str(target_year) if target_year else None
    
    def is_match(entry_text, entry_doi=None, entry_title=None):
        entry_text_lower = entry_text.lower()
        
        # 1. Strongest Match: DOI
        if target_doi_clean:
            if entry_doi and target_doi_clean in entry_doi.lower():
                return True
            if target_doi_clean in entry_text_lower:
                return True
                
        # 2. Strong Match: Title
        if target_title_clean:
            if entry_title:
                 clean_entry_title = entry_title.lower().replace('{','').replace('}','')
                 if target_title_clean in clean_entry_title:
                     return True
            if target_title_clean in entry_text_lower:
                return True
                
        # 3. Fuzzy Match: First Author + Year
        if first_author_last_name and target_year_str:
            if first_author_last_name in entry_text_lower and target_year_str in entry_text_lower:
                return True
                
        return False

    # Strategy 1: Look for .bib files
    bib_files = [f for f in os.listdir(source_dir) if f.endswith('.bib')]
    if bib_files:
        for bib in bib_files:
            try:
                entries = parse_bib_file(os.path.join(source_dir, bib))
                for entry in entries:
                    e_doi = entry.get('doi', '')
                    e_title = entry.get('title', '')
                    e_author = entry.get('author', '')
                    e_year = entry.get('year', '')
                    
                    full_text = f"{e_title} {e_author} {e_year} {e_doi}"
                    
                    if is_match(full_text, entry_doi=e_doi, entry_title=e_title):
                        return entry['ID']
            except Exception as e:
                # print(f"Error parsing {bib}: {e}") # Suppress noise if needed, or keep for debug
                pass

    # Strategy 2: Look for .bbl files
    bbl_files = [f for f in os.listdir(source_dir) if f.endswith('.bbl')]
    if bbl_files:
        for bbl in bbl_files:
            entries = parse_bbl_file(os.path.join(source_dir, bbl))
            for entry in entries:
                if is_match(entry['text']):
                    return entry['ID']
                    
    return None
