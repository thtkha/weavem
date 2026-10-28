def run(text, lowercase=True):
    cleaned = text.strip()
    return cleaned.lower() if lowercase else cleaned
