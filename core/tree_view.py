from anytree import Node, RenderTree

def print_tree(root_paper, citation_data):
    """
    Prints the citation tree.
    root_paper: PaperMetadata object for the root.
    citation_data: List of dictionaries:
        {
            'paper': PaperMetadata,
            'citations': [CitationContext, CitationContext, ...]
        }
    """
    
    # Create Root Node
    root_node = Node(f"{root_paper.title} ({root_paper.year}) [{root_paper.arxiv_id or root_paper.doi or 'No ID'}]")
    
    for item in citation_data:
        citing_paper = item['paper']
        # Contexts is either specific objects or a list of error strings
        contexts_or_errors = item['citations']
        
        # 1. Paper Title Node
        paper_node = Node(f"{citing_paper.title} ({citing_paper.year})", parent=root_node)
        
        # 2. Metadata Nodes
        # Authors
        if citing_paper.authors:
            # Format: Authors: A, B, C...
            author_text = f"Authors: {', '.join(citing_paper.authors[:3])}"
            if len(citing_paper.authors) > 3:
                author_text += "..."
            Node(author_text, parent=paper_node)
            
        # Link
        if citing_paper.arxiv_id:
            Node(f"Link: https://arxiv.org/abs/{citing_paper.arxiv_id}", parent=paper_node)
        elif citing_paper.doi:
            Node(f"Link: https://doi.org/{citing_paper.doi}", parent=paper_node)

        # 3. Context Nodes (Hierarchical)
        # Check if we have valid CitationContext objects or just strings (errors)
        if contexts_or_errors and isinstance(contexts_or_errors[0], str):
            # It's an error or status message
            for msg in contexts_or_errors:
                Node(f"Status: {msg}", parent=paper_node)
        else:
            # We have CitationContext objects
            # We want to group by Section -> Subsection -> Subsubsection
            # Let's use a helper to find or create nodes
            
            def get_or_create_node(name, parent):
                for child in parent.children:
                    if child.name == name:
                        return child
                return Node(name, parent=parent)

            for ctx in contexts_or_errors:
                current_parent = paper_node
                
                # Section
                if ctx.section:
                    current_parent = get_or_create_node(f"Section: {ctx.section}", current_parent)
                    
                    # Subsection (only if section exists)
                    if ctx.subsection:
                        current_parent = get_or_create_node(f"Subsection: {ctx.subsection}", current_parent)
                        
                        # Subsubsection
                        if ctx.subsubsection:
                             current_parent = get_or_create_node(f"Subsubsection: {ctx.subsubsection}", current_parent)
                else:
                    # No section info, just attach to paper
                    # Or maybe it was in the abstract or introduction without a header?
                    # We can label it "Unknown Section" or similar if needed, or just leave it attached to paper?
                    # Current logic in parser defaults to None.
                    # Let's add a generic node if absolutely no context
                    if not ctx.section and not ctx.subsection:
                         Node(f"Cited in: Unknown Section", parent=paper_node)

    # Render
    for pre, fill, node in RenderTree(root_node):
        print("%s%s" % (pre, node.name))
