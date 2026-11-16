"""Conservative matching against actual Libretro gallery filenames."""
import re
from artwork_identity import title_key
from rom_paths import DISC_MARKER

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


def release_tags(name):
    """Identity constraints; translation packaging is not a release or revision."""
    if re.fullmatch(r'CN\s*\[[^\[\]]+\]', name, re.I):
        return set()
    marker = DISC_MARKER.search(name)
    result = {'disc ' + (marker[1] or marker[2])} if marker else set()
    for tag in tags(name):
        if tag == 'cn' or re.match(r'^t[+-]', tag):
            continue
        tag = {'j': 'japan', 'u': 'usa', 'e': 'europe'}.get(tag, tag)
        tag = re.sub(r'^(disc|disk|cd)\s*(\d+)(?:\s*of\s*\d+)?$', r'disc \2', tag)
        result.add(tag)
    return result


def release_candidates(source, names):
    if source in names:
        return [source]
    constraints = release_tags(source)
    return [name for name in names if constraints <= release_tags(name)]


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


def matching_artwork_name(system, source, names, constraints=None):
    """An unnumbered game may use a numbered image, never another known disc."""
    exact = matching_gallery_name(system, source, names)
    if exact:
        return exact
    if constraints is not None:
        # The caller knows only the game title. Region/revision on its recommended
        # box art is not evidence about the ROM or the other image types.
        presentation = re.compile(
            r'Japan|USA|Europe|Asia|World|China|Taiwan|Korea|France|Germany|Italy|Spain|Australia|'
            r'(?:En|Ja|Fr|De|Es|It|Zh|Ko|Pt|Nl|Sv|Ru)(?:,\s*(?:En|Ja|Fr|De|Es|It|Zh|Ko|Pt|Nl|Sv|Ru))*|'
            r'Rev(?:ision)?\s+[\w.]+|Reprint(?:\s+[A-Z])?|Unl|Aftermarket', re.I)
        def edition(name):
            return {tag for tag in tags(name) if not presentation.fullmatch(tag)}
        variants = [name for name in names if title_key(name) == title_key(source)
                    and set(constraints) <= release_tags(name) and edition(name) == edition(source)]
        if not variants and any(term in system for term in ('Arcade', 'FBNeo', 'MAME')):
            variants = [name for name in names if title_key(name) == title_key(source)
                        and set(constraints) <= release_tags(name)
                        and not re.search(r'\b(?:hack|bootleg|prototype)\b', name, re.I)]
        if variants:
            from title_family import recommend_source
            return recommend_source(variants)
    if DISC_MARKER.search(source):
        return None
    matches = []
    for name in names:
        disc = DISC_MARKER.search(name)
        if disc and gallery_title_key(system, name) == gallery_title_key(system, source):
            unnumbered = DISC_MARKER.sub('', name).strip()
            if matching_gallery_name(system, source, [unnumbered]):
                matches.append((int(disc[1] or disc[2]), name))
    return min(matches)[1] if matches else None
