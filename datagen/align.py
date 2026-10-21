"""Move labels from the clean text to the OCR text of the same document.

OCR changes the text: characters are misread, dropped or added. The two texts are aligned
character by character, and each span's start and end are mapped through that alignment.
The span keeps its true `value`; its `text` becomes whatever OCR actually produced.
"""

from difflib import SequenceMatcher

from datagen.models import Span


def _char_maps(source: str, target: str) -> tuple[list[int], list[int]]:
    """Map span boundaries from `source` to `target`.

    `starts[i]` is where source character i begins in the target; `ends[i]` is where the source
    text up to (not including) i ends. They differ around OCR insertions: junk OCR adds between
    two fields belongs to neither, so a span's end must not stretch over it.
    """
    starts = [0] * (len(source) + 1)
    ends = [0] * (len(source) + 1)
    matcher = SequenceMatcher(None, source, target, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        n = i2 - i1
        for k in range(n):
            if tag == "equal":
                starts[i1 + k] = j1 + k
                ends[i1 + k + 1] = j1 + k + 1
            elif tag == "replace":
                # Spread the source characters over the replacement; a span ending at the end of
                # the replaced region takes the whole replacement.
                starts[i1 + k] = j1 + (k * (j2 - j1)) // n
                ends[i1 + k + 1] = j1 + -(-(k + 1) * (j2 - j1) // n)
            else:  # delete: these characters vanished; point at where they would have been
                starts[i1 + k] = j1
                ends[i1 + k + 1] = j1
    starts[len(source)] = len(target)
    return starts, ends


def project_spans(source: str, spans: list[Span], target: str) -> tuple[list[Span], int]:
    """Return the spans re-anchored in `target`, and how many were lost entirely."""
    starts, ends = _char_maps(source, target)
    projected: list[Span] = []
    lost = 0
    for span in spans:
        start, end = starts[span.start], ends[span.end]
        # Trim whitespace OCR may have pulled into the span's edges.
        while start < end and target[start].isspace():
            start += 1
        while end > start and target[end - 1].isspace():
            end -= 1
        # A misread field stays about its printed length. A span that grew far longer, or across
        # lines, was stretched over OCR junk by the alignment: its true position is unknown.
        new_line = "\n" in target[start:end] and "\n" not in span.text  # a wrapped field may
        stretched = end - start > 2 * len(span.text) + 3 or new_line  # legitimately span lines
        if start >= end or stretched:
            lost += 1
            continue
        projected.append(
            span.model_copy(update={"start": start, "end": end, "text": target[start:end]})
        )
    return projected, lost
