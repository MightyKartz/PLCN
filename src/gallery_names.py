"""Conservative matching against actual Libretro gallery filenames."""
import re
from artwork_identity import title_key

# Verified spellings in the PCE gallery. Keep parts/sequels explicitly separate.
PCE_ALIASES = {
    'rtypepart1': 'R-Type I',
    'rtypepart2': 'R-Type II',
    'xeviousfardrautdensetsu': 'Xevious - Fardraut Saga',
}


def gallery_title_key(system, name):
    key = title_key(name)
    if system == 'NEC - PC Engine - TurboGrafx 16':
        key = title_key(PCE_ALIASES.get(key, key))
    return key


def tags(name, languages=True):
    values = re.findall(r'\(([^()]*)\)|\[([^\[\]]*)\]', name)
    result = []
    for parts in values:
        value = next(p for p in parts if p).strip().casefold()
        if not languages and re.fullmatch(r'[a-z]{2}(?:,[a-z]{2})*', value):
            continue
        result.append(value)
    return tuple(sorted(result))


def matching_gallery_name(system, source, names):
    if source in names:
        return source
    from dos_artwork_names import search_names
    source_keys = {gallery_title_key(system, name) for name in search_names(system, source)}
    if system == 'DOS' and not any(re.fullmatch(r'(?:19|20)\d{2}', tag) for tag in tags(source)):
        # An omitted release year may match one unique DOS entry. Preserve all
        # other tags and refuse ambiguity, even across different release years.
        candidates = [name for name in names
                      if gallery_title_key(system, name) in source_keys
                      and tuple(t for t in tags(name) if not re.fullmatch(r'(?:19|20)\d{2}', t)) == tags(source)]
        if candidates:
            return candidates[0] if len(candidates) == 1 else None
    candidates = [name for name in names
                  if gallery_title_key(system, name) in source_keys
                  and tags(name, languages=False) == tags(source, languages=False)]
    exact_tags = [name for name in candidates if tags(name) == tags(source)]
    if exact_tags:
        candidates = exact_tags
    else:
        # Missing language annotations may fall back to an unannotated gallery
        # name, but never to a different explicitly annotated language variant.
        candidates = [name for name in candidates if tags(name) == tags(name, languages=False)]
    return candidates[0] if len(candidates) == 1 else None
