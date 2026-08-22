import difflib

def sim_chunk(confirmed_text, chunk_text, tolerance):
    text_to_append = chunk_text
    search_len = min(len(confirmed_text), 150)
    suffix = confirmed_text[-search_len:].lower()
    prefix = chunk_text[:150].lower()
    
    matcher = difflib.SequenceMatcher(None, suffix, prefix)
    match = matcher.find_longest_match(0, len(suffix), 0, len(prefix))
    
    print(f"Suffix: '{suffix}'")
    print(f"Prefix: '{prefix}'")
    print(f"Match: '{prefix[match.b:match.b+match.size]}', size: {match.size}, b: {match.b}")
    
    if match.size > 5:
        text_to_append = chunk_text[match.b + match.size:]
        print(f"Merge alignment -> '{text_to_append}'")
    else:
        print("Fallback")
        text_to_append = chunk_text # ignoring time fallback for simplicity in test
    return text_to_append

ct = "hola como estas "
new_ct = sim_chunk(ct, " estas muy bien y tu", 0.4)
ct += new_ct
new_ct2 = sim_chunk(ct, " bien y tu que tal", 0.4)
