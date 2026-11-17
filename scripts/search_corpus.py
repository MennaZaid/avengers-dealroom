"""Hybrid search (keyword + vector) over a RAG index. Usage: python scripts/search_corpus.py "Mom Test" [live]"""

import sys

from venture_os.evidence.retrieval import hybrid_search

if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "Mom Test"
    index = sys.argv[2] if len(sys.argv) > 2 else "corpus"
    for i, hit in enumerate(hybrid_search(query, index, k=5), 1):
        print(f"{i}. {hit['title'][:70]}  [{hit.get('corpus_id') or ''}]  score {hit['score']:.4f}  "
              f"({'; '.join(hit['matched'])})\n   {hit['url']}\n   {hit['text'][:160].replace(chr(10), ' ')}...")
