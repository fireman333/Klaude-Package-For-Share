"""Run the med-manuscript-writing de-LLM revision harness on a local MLX model.

Usage:
  .venv/bin/python local_revise.py --rules RULES.md --in draft.md --out revised.md \
      [--model mlx-community/Qwen3-4B-Instruct-2507-4bit] [--claim-pass]

Default = lexical pass only. Claim-strength fixes belong to Claude (SKILL.md Step 3).

Revises paragraph by paragraph (headings kept verbatim) so a small model
stays on task. Each rewrite is rejected (retry once, then keep original) if it
loses or invents numbers, changes length >25%, or adds many new content words.
"""
import argparse
import re
import time

from ai_tell_score import TELL_WORDS
from mlx_lm import generate, load
from mlx_lm.sample_utils import make_sampler

SYSTEM = """You are a senior medical-journal copy editor. Revise ONE paragraph of a manuscript.
Follow these house rules exactly:

{rules}

Hard constraints:
- Keep every number, CI, p value, HR/OR/RR, sample size, and drug/disease name EXACTLY as given.
- Do not add facts, citations, or claims that are not in the paragraph.
- Do not remove a substantive claim; you may delete empty filler.
- Output ONLY the revised paragraph as plain prose. No preamble, no notes, no markdown bold."""

NUM = re.compile(r"\d+(?:[.,]\d+)?")


OPENERS = r"(?:Furthermore|Moreover|Additionally|Notably|Importantly|Crucially|Overall|In conclusion),"


# Claim-strength errors with a fixed rewrite hint (small models need the answer spelled out).
CLAIM_FLAGS = {
    r"\bno difference\b": 'replace with "no statistically significant difference"',
    r"\bequally effective\b|\bequivalent\b|\bcomparable efficacy\b": 'delete; say "did not differ significantly"',
    r"\bdemonstrat\w+ that\b|\bproves?\b": 'replace with "suggests"',
    r"\bsafe and effective\b": 'replace with "was associated with [the observed outcome]" using only outcomes named in the text',
    r"\bfirst-line\b|\bshould (?:be )?(?:consider|use|prescrib)\w*": 'delete the recommendation; state the finding may inform future trials',
    r"\bensures? generali[sz]ability\b": 'replace with "may support generalisability"',
    r"\bminimi[sz]es bias\b": 'delete',
    r"\bfirst study\b|\bto our knowledge, this is the first\b": 'delete',
}


def flagged_spans(para, kind="all"):
    """Sentences containing LLM tells, with the offending phrases."""
    out = []
    for sent in re.split(r"(?<=[.!?])\s+", para):
        low = sent.lower()
        hits = []
        if kind in ("all", "lex"):
            hits += [w for w in TELL_WORDS if re.search(r"\b" + re.escape(w.rstrip(",")) + r"\b", low)]
            if re.match(OPENERS, sent):
                hits.append(sent.split(",")[0] + ",")
            if "\u2014" in sent or " -- " in sent:
                hits.append("em dash")
            if re.search(r"\bnot only\b.*\bbut also\b", low):
                hits.append("not only...but also")
        for pat, hint in (CLAIM_FLAGS.items() if kind in ("all", "claim") else ()):
            m = re.search(pat, low)
            if m:
                hits.append(f'"{m.group(0)}" ({hint})')
        if hits:
            out.append((sent.strip(), sorted(set(hits))))
    return out


def revise_paragraph(model, tok, rules, para, max_tokens, sampler, kind="all"):
    spans = flagged_spans(para, kind)
    if not spans:
        return para
    task = "\n".join(f"- In: \"{s}\"  -> fix: {', '.join(h)}" for s, h in spans) or "- (none flagged; fix only rule violations you are certain of)"
    messages = [
        {"role": "system", "content": SYSTEM.format(rules=rules)},
        {"role": "user", "content": (
            "MINIMAL EDIT. Copy the paragraph and change ONLY the flagged phrases below "
            "(delete them or replace with a plain word). Every other sentence stays word-for-word. "
            "Do not add any number, fact, study, or drug that is not already in the paragraph.\n\n"
            f"Flagged:\n{task}\n\nParagraph:\n{para}")},
    ]
    prompt = tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
    out = generate(model, tok, prompt=prompt, max_tokens=max_tokens, sampler=sampler, verbose=False)
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip()
    return out


CONTENT = re.compile(r"\b[A-Za-z][A-Za-z-]{5,}\b")


def check(orig, new):
    """Return a reason string if the rewrite is unsafe, else ''."""
    o_num, n_num = set(NUM.findall(orig)), set(NUM.findall(new))
    if o_num - n_num:
        return f"numbers lost {sorted(o_num - n_num)}"
    if n_num - o_num:
        return f"numbers invented {sorted(n_num - o_num)}"
    ratio = len(new.split()) / max(len(orig.split()), 1)
    if ratio > 1.25 or ratio < 0.4:
        return f"length ratio {ratio:.2f}"
    o_words = {w.lower() for w in CONTENT.findall(orig)}
    novel = [w for w in CONTENT.findall(new) if w.lower() not in o_words]
    if len(novel) / max(len(new.split()), 1) > 0.25:
        return f"too many new content words ({len(novel)})"
    return ""


def guarded(model, tok, rules, para, max_tokens, sampler, kind="all", tries=2):
    """Rewrite with up to `tries` attempts; fall back to original if unsafe."""
    why = ""
    for _ in range(tries):
        new = revise_paragraph(model, tok, rules, para, max_tokens, sampler, kind)
        why = check(para, new)
        if not why:
            return new, ""
    return para, why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", required=True)
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="mlx-community/Qwen3-4B-Instruct-2507-4bit")
    ap.add_argument("--max-tokens", type=int, default=1500)
    ap.add_argument("--temp", type=float, default=0.2)
    ap.add_argument("--claim-pass", action="store_true",
                    help="also let the local model fix claim strength (UNSAFE on <10B models: "
                         "observed direction-of-effect inversions that no number check catches)")
    a = ap.parse_args()
    a.passes = ("lex", "claim") if a.claim_pass else ("lex",)

    rules = open(a.rules, encoding="utf-8").read()
    text = open(a.inp, encoding="utf-8").read()
    t0 = time.time()
    model, tok = load(a.model)
    sampler = make_sampler(temp=a.temp, top_p=0.9)
    print(f"[load] {a.model} in {time.time() - t0:.1f}s", flush=True)

    blocks = re.split(r"\n\s*\n", text.strip())
    out_blocks = []
    reverted = 0
    for i, b in enumerate(blocks, 1):
        if b.lstrip().startswith("#"):
            out_blocks.append(b.strip())
            continue
        t1 = time.time()
        new = b.strip()
        for kind in a.passes:  # focused passes beat one overloaded pass on small models
            new, why = guarded(model, tok, rules, new, a.max_tokens, sampler, kind)
            if why:
                print(f"[revert] block {i} {kind} pass: {why} -> keeping previous", flush=True)
                reverted += 1
        out_blocks.append(new)
        print(f"[block {i}/{len(blocks)}] {time.time() - t1:.1f}s", flush=True)

    open(a.out, "w", encoding="utf-8").write("\n\n".join(out_blocks) + "\n")
    print(f"[done] {a.out} total {time.time() - t0:.1f}s; reverted {reverted} block(s)")


if __name__ == "__main__":
    main()
