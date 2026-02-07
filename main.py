import argparse
import sys
import shutil
import os

from core.resolver import resolve_paper_id
from core.fetcher import get_paper_metadata, get_citations
from core.downloader import download_source, extract_source, find_main_tex
from core.parser import get_ast, find_citations, find_key_for_paper, resolve_latex_inclusions
from core.tree_view import print_tree

def main():
    parser = argparse.ArgumentParser(description="Citation Constellation")
    parser.add_argument("input", help="DOI, ArXiv ID, or ADS URL of the paper")
    parser.add_argument("--keep-sources", action="store_true", help="Keep downloaded sources (default: delete)")
    args = parser.parse_args()

    print(f"Resolving input: {args.input}...")
    try:
        paper_id = resolve_paper_id(args.input)
        print(f"Resolved to: {paper_id}")
        
        print("Fetching metadata...")
        root_metadata = get_paper_metadata(paper_id)
        if not root_metadata.bibcode:
             print("Warning: No bibcode found, citations queries might fail if not using ADS.")
        print(f"Target Paper: {root_metadata.title}")
        
        print("Fetching citing papers (limit 25)...")
        citing_papers = get_citations(root_metadata.bibcode)
        print(f"Found {len(citing_papers)} citations.")
        
        if len(citing_papers) > 25:
             print("More than 25 citations found. Truncating to 25 as requested.")
             citing_papers = citing_papers[:25]
             
        results = []
        
        for i, citing_paper in enumerate(citing_papers):
            print(f"[{i+1}/{len(citing_papers)}] Processing citation from: {citing_paper.title}")
            
            if not citing_paper.arxiv_id:
                print("  -> No ArXiv ID found (required for source). Skipping source analysis.")
                results.append({'paper': citing_paper, 'citations': ["Source not available"]})
                continue
                
            try:
                # Download Source
                tar_path = download_source(citing_paper.arxiv_id, output_dir="data/sources")
                extract_dir = extract_source(tar_path, extract_to=f"data/extracted/{citing_paper.arxiv_id}")
                
                # Find Main Tex
                main_tex = find_main_tex(extract_dir)
                with open(main_tex, 'r', errors='replace') as f:
                    raw_tex_content = f.read()
                
                # Resolve Inclusions (handle \input, \include)
                tex_content = resolve_latex_inclusions(extract_dir, raw_tex_content)
                
                # Identify Key
                # We need to find the key used in THIS paper that refers to OUR root paper.
                # We search by DOI first, then title.
                citation_key = find_key_for_paper(
                    extract_dir, 
                    target_doi=root_metadata.doi, 
                    target_title=root_metadata.title,
                    target_authors=root_metadata.authors,
                    target_year=root_metadata.year
                )
                
                if not citation_key:
                    print("  -> Could not identify citation key in bibliography. Skipping AST search.")
                    results.append({'paper': citing_paper, 'citations': ["Citation key not found in .bib"]})
                    continue
                    
                print(f"  -> Found citation key: {citation_key}")
                
                # Parse AST
                ast = get_ast(tex_content)
                contexts = find_citations(ast, [citation_key])
                
                if not contexts:
                    print("  -> Key found but no usage in text found (maybe \nocite?).")
                    results.append({'paper': citing_paper, 'citations': ["No in-text citations found"]})
                else:
                    results.append({'paper': citing_paper, 'citations': contexts})
            
            except Exception as e:
                print(f"  -> Error processing {citing_paper.arxiv_id}: {e}")
                results.append({'paper': citing_paper, 'citations': [f"Error: {e}"]})

        # Output
        print("\n\n=== Citation Constellation ===\n")
        print_tree(root_metadata, results)
        
        # Cleanup
        if not args.keep_sources:
            print("Cleaning up data directory...")
            if os.path.exists("data"):
                shutil.rmtree("data")

    except Exception as e:
        print(f"Fatal Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
