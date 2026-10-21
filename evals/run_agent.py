"""Evaluate the coding agent against the mappers' top-1 answer, item by item.

uv run python -m evals.run_agent --docs 20

Items are the true printed names (lab tests with their unit, referral diagnoses), so this
measures coding alone, not extraction. Each document is one agent run (at most 5 model calls).
Runs are cached; if the daily quota runs out the run stops and scores what it has.
"""

import argparse
import json
import statistics
from pathlib import Path

from dotenv import load_dotenv

from agent.coder import CodingAgent
from datagen.catalogue import BY_CODE
from datagen.models import LabReport
from evals.run_llm import sample_docs
from extract.llm import QuotaExhausted
from normalise.embed import Embedder
from normalise.icd10 import Icd10Mapper
from normalise.loinc import LoincMapper


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=Path("data/docs/labels.jsonl"))
    parser.add_argument("--docs", type=int, default=20, help="documents of each type")
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=Path("evals/results/agent.json"))
    args = parser.parse_args()

    embed = Embedder().encode
    loinc = LoincMapper(Path("data/loinc"), embed, Path("data/cache/loinc_names.npy"))
    icd10 = Icd10Mapper(
        Path("data/icd10cm/Code Descriptions/icd10cm_order_2027.txt"),
        embed,
        Path("data/cache/icd10_names.npy"),
    )
    agent = CodingAgent(args.model, loinc, icd10, Path("data/agent_cache"))
    half = args.docs // 2
    docs = sample_docs(args.labels, ["test", "test_unseen"], half, args.seed, half)

    tally = {
        kind: {"items": 0, "mapper": 0, "agent": 0, "mapper_close": 0, "agent_close": 0}
        for kind in ("loinc", "icd10")
    }
    steps: list[int] = []
    tokens: list[int] = []
    examples: list[str] = []
    done = 0
    for doc in docs:
        report = doc.report
        if isinstance(report, LabReport):
            kind = "loinc"
            items = [
                {
                    "id": f"r{i}",
                    "test": row.name.text,
                    "unit": row.unit.text if row.unit else "",
                    "value": row.value.text,
                    "ref_range": row.ref_range.text if row.ref_range else "",
                }
                for i, row in enumerate(report.results)
            ]
            gold = {
                f"r{i}": BY_CODE[row.name.value].code_for(doc.lang)
                for i, row in enumerate(report.results)
            }
            mapper_codes = {
                it["id"]: next((h.code for h in loinc.map(it["test"], it["unit"] or None)), "")
                for it in items
            }

            def close(a: str, b: str) -> bool:
                ra, rb = loinc.rows.get(a), loinc.rows.get(b)
                if ra is None or rb is None:
                    return False
                return all(ra[f] == rb[f] for f in ("COMPONENT", "PROPERTY", "SYSTEM"))
        else:
            kind = "icd10"
            items = [{"id": f"d{i}", "diagnosis": d.text} for i, d in enumerate(report.diagnoses)]
            gold = {f"d{i}": d.value for i, d in enumerate(report.diagnoses)}
            mapper_codes = {it["id"]: icd10.map(it["diagnosis"])[0].code for it in items}

            def close(a: str, b: str) -> bool:
                return a[:3] == b[:3]

        try:
            run = agent.run(doc.doc_id, report.doc_type, items, doc.text)
        except QuotaExhausted:
            print(f"Daily quota reached after {done} documents; rerun tomorrow to continue.")
            break
        done += 1
        steps.append(run.steps)
        tokens.append(run.input_tokens + run.output_tokens)
        t = tally[kind]
        for item_id, want in gold.items():
            got_agent = run.codes.get(item_id, "")
            t["items"] += 1
            t["mapper"] += mapper_codes[item_id] == want
            t["agent"] += got_agent == want
            t["mapper_close"] += close(mapper_codes[item_id], want)
            t["agent_close"] += close(got_agent, want)
            if got_agent == want != mapper_codes[item_id] and len(examples) < 8:
                name = next(it for it in items if it["id"] == item_id)
                examples.append(
                    f"{name.get('test') or name.get('diagnosis')!r}: mapper "
                    f"{mapper_codes[item_id]}, agent {got_agent} (right)"
                )
        print(
            f"{done}/{len(docs)} {doc.doc_id} {kind} steps={run.steps} "
            f"tools={len(run.tool_calls)}{' (cached)' if run.cached else ''}",
            flush=True,
        )

    report_out: dict[str, object] = {
        "docs": done,
        "mean_steps": statistics.mean(steps or [0]),
        "mean_tokens": statistics.mean(tokens or [0]),
    }
    for kind, t in tally.items():
        if not t["items"]:
            continue
        n = t["items"]
        label = "same test" if kind == "loinc" else "same category"
        report_out[kind] = {k: v / n for k, v in t.items() if k != "items"} | {"items": n}
        print(
            f"\n{kind}: {n} items  top-1 mapper {t['mapper'] / n:6.1%} "
            f"-> agent {t['agent'] / n:6.1%}"
            f"   {label}: mapper {t['mapper_close'] / n:6.1%} -> agent {t['agent_close'] / n:6.1%}"
        )
    print(
        f"mean steps per document {report_out['mean_steps']:.1f}, "
        f"tokens per document {report_out['mean_tokens']:.0f}"
    )
    for e in examples:
        print("  fixed:", e)
    args.out.write_text(json.dumps(report_out, indent=2) + "\n")


if __name__ == "__main__":
    main()
