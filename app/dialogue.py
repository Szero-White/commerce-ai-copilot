"""Follow-up questions: "nó cao bao nhiêu?", "cái thứ hai giá bao nhiêu?".

Memory is one step deep and lives in the CLIENT: the previous answer returned `turn_context` (the document ids it showed,
in the order shown) and the client sends it back. Nothing is stored on the server, and no earlier text is ever put in a
prompt. The ids are untrusted input: each one is looked up in the database, and anything unknown is ignored.

A pointer is resolved only when it is unambiguous. Otherwise the answer is a question back, never a guess:
* "nó / cái này" -> the one document shown last (a single result, or a list of exactly one);
* "cái thứ hai" -> the second document of the list that was shown (the order of the sources panel);
* anything else -> `needs_clarification` with the candidates.
"""
from dataclasses import dataclass, field

MAX_IDS = 5
KINDS = ("single", "list", "clarify", "none")


@dataclass
class Resolution:
    action: str                       # 'standalone' | 'bound' | 'ask'
    doc_id: str | None = None
    options: list = field(default_factory=list)   # candidate documents (dicts) to offer when asking
    pointer: tuple | None = None


def turn_context_for(sources, kind=None):
    """What the client should send back with its next question."""
    ids = [s["id"] for s in sources][:MAX_IDS]
    return {"ids": ids, "kind": kind or ("none" if not ids else "single" if len(ids) == 1 else "list")}


def resolve(store, analysis, turn_context) -> Resolution:
    """Decide what a question that points at "something said before" refers to."""
    if not analysis.needs_referent:
        return Resolution("standalone")     # it names its own subject (or points at nothing): context is not needed
    known = []
    kind = "none"
    if turn_context:
        kind = turn_context.get("kind", "none")
        for doc_id in list(dict.fromkeys(turn_context.get("ids", [])))[:MAX_IDS]:
            doc = store.document(doc_id)          # untrusted id: only real documents count
            if doc:
                known.append(doc)
    kind_of_pointer, number = analysis.pointer
    if kind_of_pointer == "pronoun":
        if len(known) == 1:
            return Resolution("bound", known[0]["id"], pointer=analysis.pointer)
    elif kind in ("list", "clarify") and len(known) >= 2 and number is not None:
        index = number - 1 if number > 0 else len(known) + number
        if 0 <= index < len(known):
            return Resolution("bound", known[index]["id"], pointer=analysis.pointer)
    return Resolution("ask", options=known, pointer=analysis.pointer)


def clarification_text(options) -> str:
    if not options:
        return "Bạn đang hỏi về sản phẩm hoặc chính sách nào? Vui lòng nêu tên cụ thể."
    lines = [f"{i}. {d['title']} [{d['id']}]" for i, d in enumerate(options, 1)]
    return ("Mình chưa chắc bạn đang hỏi về mục nào. Bạn nêu tên, hoặc nói \"cái thứ hai\" theo thứ tự dưới đây:\n"
            + "\n".join(lines))
