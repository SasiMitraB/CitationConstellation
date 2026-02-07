"""
Utility functions for author name normalization and comparison.
"""

import unicodedata
import re


def normalize_author_name(author):
    """
    Normalize author name for comparison.

    Returns (last_name, first_initial) tuple in lowercase.

    Handles:
    - "Last, First" and "First Last" formats
    - Initials vs full names
    - Unicode characters (using NFKD normalization)
    - Compound last names (van der, O', etc.)

    Args:
        author (str): Author name in various formats

    Returns:
        tuple: (last_name, first_initial) in lowercase, or None if parsing fails

    Examples:
        >>> normalize_author_name("Smith, John A.")
        ('smith', 'j')
        >>> normalize_author_name("John A. Smith")
        ('smith', 'j')
        >>> normalize_author_name("van der Berg, Hans")
        ('van der berg', 'h')
    """
    if not author or not isinstance(author, str):
        return None

    # Normalize unicode characters
    author = unicodedata.normalize('NFKD', author)
    # Remove diacritics
    author = ''.join([c for c in author if not unicodedata.combining(c)])

    # Remove extra whitespace
    author = ' '.join(author.split())

    # Try "Last, First" format first
    if ',' in author:
        parts = author.split(',', 1)
        last_name = parts[0].strip()
        first_name = parts[1].strip() if len(parts) > 1 else ''
    else:
        # Try "First Last" format
        parts = author.split()
        if len(parts) >= 2:
            # Last name is the last word
            last_name = parts[-1]
            first_name = parts[0]
        elif len(parts) == 1:
            # Only one name - treat as last name
            last_name = parts[0]
            first_name = ''
        else:
            return None

    # Clean and extract first initial
    last_name = re.sub(r'[^\w\s\'-]', '', last_name).strip().lower()

    # Get first character of first name
    first_initial = ''
    if first_name:
        # Remove periods and spaces from initials
        first_name = re.sub(r'[.\s]', '', first_name)
        if first_name:
            first_initial = first_name[0].lower()

    return (last_name, first_initial) if last_name else None


def find_shared_authors(root_authors, citing_authors):
    """
    Find authors that appear in both lists.

    Returns list of author names (from citing_authors) that match root_authors.
    Matching is done using normalized (last_name, first_initial) tuples.

    Args:
        root_authors (list): List of author names from root paper
        citing_authors (list): List of author names from citing paper

    Returns:
        list: Author names from citing_authors that match root_authors

    Edge cases:
        - Handle None/empty lists → return []
        - Match on (last_name, first_initial) for robustness

    Examples:
        >>> find_shared_authors(["Smith, John"], ["John Smith", "Doe, Jane"])
        ['John Smith']
        >>> find_shared_authors([], ["Smith, John"])
        []
    """
    if not root_authors or not citing_authors:
        return []

    # Normalize root authors and create a set for fast lookup
    root_normalized = set()
    for author in root_authors:
        normalized = normalize_author_name(author)
        if normalized:
            root_normalized.add(normalized)

    # Find matching authors from citing paper
    shared = []
    for author in citing_authors:
        normalized = normalize_author_name(author)
        if normalized and normalized in root_normalized:
            shared.append(author)

    return shared
