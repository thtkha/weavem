"""Normalize text, count words, and return a readable summary."""
from weavem import flow, task

normalize = task("normalize")
count = task("count")
summarize = task("summarize")


@flow
def document_summary():
    # weavem-node: "normalize"
    normalized = normalize(text="  Hello Weavem  ")
    # weavem-edges: {"text": "normalize-count"}
    # weavem-node: "count"
    statistics = count(text=normalized)
    # weavem-edges: {"stats": "count-summary"}
    # weavem-node: "summarize"
    summary = summarize(stats=statistics, prefix="Document")
    return {"summarize": summary}
