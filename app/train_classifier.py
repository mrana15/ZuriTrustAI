"""Build the synthetic training set and train the triage classifier.

Usage:  python -m app.train_classifier

Outputs
* app/data/triage_training.json  - every training example (inspectable, versioned)
* app/data/triage_model.json     - trained model loaded by the screener
* eval/REPORT_classifier.md      - 5-fold cross-validation results

The training set is SYNTHETIC: danger-sign phrases from the clinically reviewed
danger_signs.json are placed into everyday sentence templates, negated variants
are labelled routine, and routine examples come from knowledge-base questions
and hand-written statements. Evaluation scenarios in eval/ are never used.
"""
from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path

from .classifier import NaiveBayesClassifier, cross_validate

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"

POSITIVE_TEMPLATES = [
    "{p}", "I have {p}", "I am having {p}", "there is {p}", "I noticed {p} today", "{p} since yesterday",
    "my wife has {p}", "she has {p}", "please help, {p}", "I'm pregnant and {p}", "after delivery {p}",
    "{p} and I am scared", "since morning {p}", "it started last night, {p}",
]
NEGATIVE_TEMPLATES = ["no {p}", "I don't have {p}", "there is no {p}", "without {p}", "never had {p}"]

EXTRA_ROUTINE = [
    "I feel fine today", "everything is okay", "just asking a question", "I am a bit tired after work",
    "my back aches a little in the evening", "I am hungry all the time", "can I eat beans", "is it okay to drink tea",
    "how do I join the savings group", "thank you", "good morning", "I want to learn about business",
    "the baby is kicking well", "my check up was normal", "I slept well", "how much does delivery cost",
    "where can I buy a mosquito net", "my feet hurt from walking", "I feel a little nervous about labour",
    "when is my next clinic visit", "I want to start the 90 day track", "how do I save money",
    "I had a normal day", "my baby is feeding well", "I have mild heartburn after meals", "I pee more often at night",
]
EXTRA_DANGER = [
    ("I am losing a lot of blood", "emergency"), ("blood everywhere on the bed", "emergency"),
    ("she is shaking and not responding", "emergency"), ("my eyes are blurry and my head is pounding", "emergency"),
    ("I cannot catch my breath", "emergency"), ("my baby has not moved all day", "emergency"),
    ("I feel like ending it all", "emergency"), ("the newborn is too weak to suck", "emergency"),
    ("my body is very hot", "urgent"), ("my hands and face are puffy", "urgent"), ("fluid is coming out of my vagina", "urgent"),
    ("I keep throwing up", "urgent"), ("pain in my lower belly", "urgent"), ("I feel very unwell", "urgent"),
    ("discharge with a bad smell", "urgent"), ("the baby's skin is turning yellow", "urgent"),
]


def build_dataset(seed: int = 11) -> list[dict]:
    rng = random.Random(seed)
    signs = json.loads((DATA / "danger_signs.json").read_text(encoding="utf-8"))["signs"]
    kb = json.loads((DATA / "knowledge_base.json").read_text(encoding="utf-8"))["entries"]
    rows: list[dict] = []
    for s in signs:
        phrases = list(s.get("phrases", []))
        groups = s.get("all_of")
        if groups:  # combine one phrase from each group
            for _ in range(8):
                phrases.append(" ".join(rng.choice(g) for g in groups))
        for p in phrases:
            for t in rng.sample(POSITIVE_TEMPLATES, 3):
                rows.append({"text": t.format(p=p), "label": s["level"], "source": f"sign:{s['id']}"})
            if s.get("phrases"):
                t = rng.choice(NEGATIVE_TEMPLATES)
                rows.append({"text": t.format(p=p), "label": "routine", "source": f"negated:{s['id']}"})
        # context exclusions from the clinical list (e.g. bleeding gums / nose) are routine
        for ex in s.get("exclude_context", []):
            for p in rng.sample(s["phrases"], min(3, len(s["phrases"]))):
                for text in (f"my {ex} {p}", f"{p} from my {ex}"):
                    rows.append({"text": text, "label": "routine", "source": f"excluded:{s['id']}"})
    for e in kb:
        for q in e["questions"]:
            rows.append({"text": q, "label": "routine", "source": f"kb:{e['id']}"})
    rows += [{"text": t, "label": "routine", "source": "handwritten"} for t in EXTRA_ROUTINE]
    rows += [{"text": t, "label": y, "source": "handwritten"} for t, y in EXTRA_DANGER]
    # de-duplicate
    seen, out = set(), []
    for r in rows:
        if r["text"] not in seen:
            seen.add(r["text"])
            out.append(r)
    return out


def main() -> None:
    rows = build_dataset()
    texts, labels = [r["text"] for r in rows], [r["label"] for r in rows]
    cv = cross_validate(texts, labels, k=5)
    model = NaiveBayesClassifier().fit(texts, labels)
    signs_version = json.loads((DATA / "danger_signs.json").read_text(encoding="utf-8"))["version"]
    model.meta = {
        "trained": date.today().isoformat(),
        "n_examples": len(rows),
        "label_counts": {c: labels.count(c) for c in sorted(set(labels))},
        "danger_signs_version": signs_version,
        "training_data": "synthetic (see app/train_classifier.py)",
        "cross_validation": cv,
    }
    (DATA / "triage_training.json").write_text(
        json.dumps({"note": "SYNTHETIC training data generated by app/train_classifier.py. No real user data.",
                    "examples": rows}, indent=1), encoding="utf-8")
    model.save(DATA / "triage_model.json")
    report = "\n".join([
        "# Triage classifier report",
        "",
        f"Trained {model.meta['trained']} on {len(rows)} **synthetic** examples "
        f"({', '.join(f'{k}: {v}' for k, v in model.meta['label_counts'].items())}).",
        "",
        "> Cross-validation on synthetic data shows the model learned the training patterns; it is **not** evidence of real-world accuracy.",
        "",
        "| Metric (5-fold CV) | Value |",
        "|---|---|",
        f"| Accuracy | {cv['accuracy']:.1%} |",
        *[f"| Recall: {c} | {r:.1%} |" for c, r in cv["recall"].items()],
        "",
    ])
    (ROOT / "eval" / "REPORT_classifier.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
