import os
import tarfile
import requests
import time

def download_source(arxiv_id, output_dir="sources"):
    """
    Downloads the source tarball for a given ArXiv ID.
    Returns the path to the downloaded file.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # ArXiv source URL format: https://arxiv.org/e-print/<id>
    # Note: arxiv_id shoud be the bare ID (e.g. 2103.02607)
    url = f"https://arxiv.org/e-print/{arxiv_id}"
    
    filename = os.path.join(output_dir, f"{arxiv_id}.tar.gz")
    
    if os.path.exists(filename):
        return filename
        
    print(f"Downloading source for {arxiv_id}...")
    response = requests.get(url, stream=True)
    
    if response.status_code == 200:
        # Check content type. Sometimes it redirects to a PDF if source is not available?
        # Usually e-print returns a tar.gz
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        return filename
    else:
        raise RuntimeError(f"Failed to download source for {arxiv_id}. Status: {response.status_code}")

def extract_source(tar_path, extract_to=None):
    """
    Extracts the tarball to a directory.
    If extract_to is None, creates a dir with the same name as the tar file (without extension).
    Returns the path to the extracted directory.
    """
    if extract_to is None:
        extract_to = tar_path.replace(".tar.gz", "").replace(".tar", "")
    
    if not os.path.exists(extract_to):
        os.makedirs(extract_to)
    
    try:
        with tarfile.open(tar_path, "r:*") as tar:
            tar.extractall(path=extract_to)
        return extract_to
    except tarfile.ReadError:
        # Sometimes it's not a tar, but a single tex file gzipped?
        # Or maybe just a PDF renamed?
        # For now, simplistic handling.
        raise RuntimeError(f"Could not extract {tar_path}. It might not be a valid tar file.")

def find_main_tex(source_dir):
    """
    Heuristic to find the main tex file in a directory.
    1. Look for 'main.tex', 'ms.tex'.
    2. Look for files with \documentclass.
    """
    tex_files = [f for f in os.listdir(source_dir) if f.endswith('.tex')]
    
    if not tex_files:
        raise FileNotFoundError(f"No .tex files found in {source_dir}")
        
    # Priority list
    for name in ['main.tex', 'ms.tex', 'article.tex']:
        if name in tex_files:
            return os.path.join(source_dir, name)
            
    # Scan for documentclass
    for f in tex_files:
        path = os.path.join(source_dir, f)
        with open(path, 'r', errors='ignore') as fh:
            content = fh.read()
            if r'\documentclass' in content:
                return path
                
    # Fallback: return the first one or raise
    return os.path.join(source_dir, tex_files[0])
