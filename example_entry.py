import feedparser

entry = feedparser.parse('https://export.arxiv.org/api/query?search_query=all:electron&max_results=1').entries[0]
print(entry.keys())
