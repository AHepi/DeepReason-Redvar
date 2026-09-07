"""A small, optional prose readback adapter (spec Parts II, V and VII).

These recognizers propose host actions; they never authorize or execute one.
The controller must retain the entire contribution independently, verify its
participant provenance, validate the current host grant and use revision, and
allow at most its shared action allowance. Unknown prose remains ordinary work.
Neither a source quotation nor a JSON object is a host action packet.

Recognized direct opening lines, case-insensitive for the fixed English words::

    Park the current use because the reference was shared.
    Stop using the current use because its necessary input is unavailable.
    Park u000003 because its claimed source passage is absent.
    Reactivate u000003 because the corrected source is now available.

An optional method/read plan begins with these complete sentences::

    Use the broader view.
    Read o000003.
    Read o000009.

``Use the NAME view.`` also accepts another name in the operator's finite recipe
menu. Up to two existing occurrence addresses can be read. Unsupported,
ambiguous, oversized, quoted, fenced, source-prefaced, and JSON-formatted
requests remain unresolved. This is a finite convenience grammar, not general
natural-language understanding. Prose does not need this grammar to survive,
be criticised, orient the working focus, or receive an operator's direct action.

Provenance cannot be inferred from an arbitrary flat string. A source that
contains an unquoted command is still source material: the controller must
never submit it here as an authorized participant response. Even a successfully
recognized participant proposal still needs the controller's authorization.
"""

from collections.abc import Mapping, Sequence
import re


SCAN_CHARS = 4000
MAX_USE_CANDIDATES = 16
MAX_PLAN_ANCHORS = 2
_IDENTIFIER = r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}"
_USE = re.compile(
    rf"(?P<verb>Park|Stop using|Reactivate) "
    rf"(?P<target>the current use|{_IDENTIFIER}) because (?P<reason>.+)",
    re.IGNORECASE,
)
_PLAN = re.compile(
    rf"(?:Use the (?P<recipe>{_IDENTIFIER}) view|Read (?P<anchor>{_IDENTIFIER}))\."
    r"(?=\s|$)",
    re.IGNORECASE,
)
_USE_AFTER_SENTENCE = re.compile(
    rf"[.!?]\s+(?:Park|Stop using|Reactivate) "
    rf"(?:the current use|{_IDENTIFIER}) because ", re.IGNORECASE,
)


def _opening(text):
    """Return a bounded direct opening and whether its first line is complete."""
    if not isinstance(text, str):
        raise TypeError("Mediation accepts contribution text as a string")
    scanned = text[:SCAN_CHARS]
    # Leading whitespace can be ordinary formatting, but four-space/tab code
    # indentation must not turn a displayed example into a direct proposal.
    start = 0
    while start < len(scanned):
        end = scanned.find("\n", start)
        end = len(scanned) if end == -1 else end
        raw = scanned[start:end]
        if raw.strip():
            if raw.startswith(("    ", "\t")):
                return "", False
            stripped = raw.lstrip()
            if stripped.startswith(('"', "'", "“", "‘", ">", "`", "{", "[")):
                return "", False
            rest = scanned[start:].lstrip(" \r")
            line_complete = "\n" in rest or len(text) <= SCAN_CHARS
            return rest, line_complete
        start = end + 1
    return "", False


def _identifier(value):
    identifier = value.get("id") if isinstance(value, Mapping) else value
    return identifier if isinstance(identifier, str) else None


def _candidates(eligible_uses):
    """No search of an unbounded use registry behind a small output packet."""
    if not isinstance(eligible_uses, (Mapping, Sequence)) or isinstance(eligible_uses, (str, bytes)):
        return None
    if len(eligible_uses) > MAX_USE_CANDIDATES:
        return None
    counts = {}
    for value in eligible_uses:
        identifier = _identifier(value)
        if identifier is not None:
            counts[identifier] = counts.get(identifier, 0) + 1
    return counts


def resolve_use(text, eligible_uses, current_use=None):
    """Read back one addressed use proposal, or return ``None`` unresolved.

    ``eligible_uses`` is an already bounded host-selected sequence of use
    dictionaries/IDs (or a mapping keyed by ID). A current-use proposal still
    must name exactly one member of that packet. Duplicate IDs are ambiguous.
    The reason is the complete opening line after ``because``; no semantic
    judgment about its quality is attempted. Conflicting direct use proposals
    found within the bounded scan are left unresolved, not ranked or voted on.
    """
    opening, line_complete = _opening(text)
    if not opening or not line_complete:
        return None
    first_line, _, remainder = opening.partition("\n")
    match = _USE.fullmatch(first_line.strip())
    if match is None or not match.group("reason").strip():
        return None
    # This deliberately errs toward leaving a multi-action passage unresolved.
    if _USE_AFTER_SENTENCE.search(first_line):
        return None
    for line in remainder.splitlines():
        if line.startswith(("    ", "\t")):
            continue
        if _USE.fullmatch(line.strip()):
            return None
    candidates = _candidates(eligible_uses)
    if candidates is None:
        return None
    target = match.group("target")
    if target.lower() == "the current use":
        target = _identifier(current_use)
    if target is None or candidates.get(target) != 1:
        return None
    action = "reactivate" if match.group("verb").lower() == "reactivate" else "park"
    reason = match.group("reason").strip()
    return {
        "action": action, "use_id": target, "reason": reason,
        "readback": f"Proposed {action} of use {target} because {reason} "
                    "Host authorization and revision checks are still required.",
    }


def resolve_plan(text, recipes, collection):
    """Read a small direct-opening recipe/read plan without executing it.

    Only a prefix of complete ``Use the NAME view.`` / ``Read ID.`` sentences
    is interpreted. Parsing stops at the first other prose, quotation or JSON.
    At most four directive sentences are inspected and at most two occurrence
    metadata lookups occur. Further requested reading remains unresolved.
    No bodies, search results, model calls, or graph traversal are used here.
    Recipe changes are proposals within the supplied menu, never new authority.
    """
    result = {"anchors": [], "readback": "No bounded direct-opening plan was resolved."}
    opening, _ = _opening(text)
    if not opening:
        return result
    if not isinstance(recipes, (Mapping, Sequence)) or isinstance(recipes, (str, bytes)) or len(recipes) > 16:
        result["readback"] = "Recipe menu is unavailable or exceeds the bounded candidate limit."
        return result
    position = 0
    recipes_seen = []
    anchors_requested = []
    notices = []
    matched = 0
    while matched < 4:
        match = _PLAN.match(opening, position)
        if match is None:
            break
        matched += 1
        recipe, anchor = match.group("recipe"), match.group("anchor")
        if recipe is not None:
            if recipe not in recipes:
                notices.append(f"Recipe {recipe} is outside the supplied menu; no change resolved.")
            elif recipe not in recipes_seen:
                recipes_seen.append(recipe)
        elif anchor not in anchors_requested:
            anchors_requested.append(anchor)
        position = match.end()
        # New-line indentation signalling a displayed code example is not
        # stripped into a new direct instruction.
        whitespace = re.match(r"[ \r\n\t]*", opening[position:]).group(0)
        if "\n    " in whitespace or "\n\t" in whitespace:
            break
        position += len(whitespace)
    if not matched:
        return result
    if len(recipes_seen) > 1:
        result["readback"] = "Conflicting view recipes remain unresolved; no plan was selected."
        return result
    if recipes_seen:
        result["recipe"] = recipes_seen[0]
        notices.append(f"Proposed view recipe: {recipes_seen[0]}.")
    for anchor in anchors_requested[:MAX_PLAN_ANCHORS]:
        if anchor in collection.data.get("occurrences", {}):
            result["anchors"].append(anchor)
        else:
            notices.append(f"Occurrence {anchor} is unavailable; its read remains unresolved.")
    if result["anchors"]:
        notices.append("Proposed addressed reads: " + ", ".join(result["anchors"]) + ".")
    if len(anchors_requested) > MAX_PLAN_ANCHORS:
        notices.append("Additional directives exceed this plan's bounded allowance and remain unresolved.")
    if matched == 4 and position < len(opening):
        notices.append("Further text lies beyond the four-directive interpretation allowance.")
    if "recipe" in result or result["anchors"]:
        notices.append("Host grants, reading budgets and installation gates still apply.")
    result["readback"] = " ".join(notices) or "The bounded direct-opening plan remains unresolved."
    return result
