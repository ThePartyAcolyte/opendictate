import difflib
suffix = " hola, como estas"
prefix = " hola, como estas bien y tu"
matcher = difflib.SequenceMatcher(None, suffix, prefix)
match = matcher.find_longest_match(0, len(suffix), 0, len(prefix))
print(f"Match: '{prefix[match.b:match.b+match.size]}', size: {match.size}, a: {match.a}, b: {match.b}")
text_to_append = prefix[match.b + match.size:]
print(f"Appended: '{text_to_append}'")
