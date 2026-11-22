"""Tiny text helpers used by the rule-based parts of the AI services."""
import re

STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "our", "are", "was", "have", "has", "need", "needs",
    "needed", "some", "any", "one", "two", "three", "four", "five", "into", "not", "but", "per", "use", "used",
    "unit", "units", "item", "items", "good", "small", "condition", "least", "about", "very", "can", "will",
    "would", "like", "want", "please", "new", "old", "lab", "work", "working",
}


def words(text):
    """Lower-case content words of a text, with a simple plural rule (chairs -> chair)."""
    result = set()
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if len(word) > 3 and word.endswith("s"):
            word = word[:-1]
        if len(word) >= 3 and word not in STOPWORDS:
            result.add(word)
    return result


def contains_phrase(text, phrase):
    """True if the phrase starts at a word boundary in the text ("monitor" matches "monitors")."""
    return re.search(rf"\b{re.escape(phrase)}", text.lower()) is not None
