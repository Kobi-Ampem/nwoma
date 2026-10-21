"""Fine-tune XLM-RoBERTa to tag lab-report fields, then export it to int8 ONNX.

Locally, pack the train and dev documents for upload (the test set never leaves this machine):
    uv run python -m extract.train_ner export
On a Colab GPU (see notebooks/train_ner.ipynb):
    python -m extract.train_ner train --data ner_train_dev.jsonl.gz --out ner_model

`train` scores the dev set end to end with the same scorer as the LLM, once with the PyTorch
model and once with the int8 ONNX model, so the cost of compression is measured, not assumed.
"""

import argparse
import gzip
import json
import time
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from datagen.models import LabeledDoc
from evals.score import all_correct, prf, score_doc
from extract.ner import NerExtractor, RunModel
from extract.ner_data import LABEL2ID, LABELS, encode

BASE_MODEL = "FacebookAI/xlm-roberta-base"


def read_docs(path: Path, splits: set[str]) -> Iterator[LabeledDoc]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            doc = LabeledDoc.model_validate_json(line)
            if doc.split in splits:
                yield doc


def export(labels: Path, out: Path) -> None:
    n = 0
    with gzip.open(out, "wt", encoding="utf-8") as f:
        for doc in read_docs(labels, {"train", "dev"}):
            f.write(doc.model_dump_json() + "\n")
            n += 1
    print(f"{n} train+dev documents -> {out} ({out.stat().st_size / 1e6:.1f} MB)")


def evaluate(extractor: NerExtractor, docs: list[LabeledDoc]) -> dict[str, Any]:
    counts: dict[str, Counter[str]] = {"all": Counter(), "digital": Counter(), "scan": Counter()}
    correct: Counter[str] = Counter()
    start = time.perf_counter()
    for doc in docs:
        c = score_doc(doc, extractor.extract(doc.text))
        for key in ("all", doc.source):
            counts[key] += c
            correct[key] += all_correct(c)
    seconds = time.perf_counter() - start
    n = Counter(d.source for d in docs) + Counter({"all": len(docs)})
    return {
        key: {"docs": n[key], "f1": prf(counts[key])[2], "doc_all_correct": correct[key] / n[key]}
        for key in counts
    } | {"ms_per_doc": 1000 * seconds / len(docs)}


def train(
    data: Path, out: Path, epochs: float, lr: float, batch: int, max_docs: int | None
) -> None:
    import torch
    from transformers import (
        AutoModelForTokenClassification,
        AutoTokenizer,
        DataCollatorForTokenClassification,
        Trainer,
        TrainingArguments,
    )

    out.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    train_docs = list(read_docs(data, {"train"}))[:max_docs]
    dev_docs = list(read_docs(data, {"dev"}))[:max_docs]
    train_windows = [w for d in train_docs for w in encode(tokenizer, d.text, d.spans)]
    dev_windows = [w for d in dev_docs for w in encode(tokenizer, d.text, d.spans)]
    print(f"train: {len(train_docs)} docs, {len(train_windows)} windows; dev: {len(dev_docs)}")

    model = AutoModelForTokenClassification.from_pretrained(
        BASE_MODEL,
        num_labels=len(LABELS),
        id2label=dict(enumerate(LABELS)),
        label2id=LABEL2ID,
    )
    args = TrainingArguments(
        output_dir=str(out / "checkpoints"),
        learning_rate=lr,
        per_device_train_batch_size=batch,
        per_device_eval_batch_size=batch,
        num_train_epochs=epochs,
        warmup_steps=0.1,  # first 10% of steps ramp the learning rate up from 0
        weight_decay=0.01,
        eval_strategy="epoch",  # dev loss per epoch: rising loss means overfitting
        save_strategy="no",
        logging_steps=50,
        fp16=torch.cuda.is_available(),
        report_to="none",
        seed=42,
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_windows,
        eval_dataset=dev_windows,
        data_collator=DataCollatorForTokenClassification(tokenizer),
    )
    trainer.train()

    device = next(model.parameters()).device
    model.eval()

    def run_torch(ids: Any, mask: Any) -> Any:
        with torch.no_grad():
            logits = model(
                input_ids=torch.from_numpy(ids).to(device),
                attention_mask=torch.from_numpy(mask).to(device),
            ).logits
        return logits.float().cpu().numpy()

    torch_run: RunModel = run_torch
    report: dict[str, Any] = {"base_model": BASE_MODEL, "epochs": epochs, "lr": lr}
    report["dev_pytorch"] = evaluate(NerExtractor(tokenizer, torch_run), dev_docs)
    print("dev, PyTorch:", json.dumps(report["dev_pytorch"], indent=1))

    # Export: ONNX graph with variable batch and sequence length, then int8 weights.
    from onnxruntime.quantization import QuantType, quantize_dynamic

    model.cpu()
    sample = tokenizer(["Hémoglobine 12,7 g/dL"], return_tensors="pt")
    torch.onnx.export(
        model,
        (sample["input_ids"], sample["attention_mask"]),
        str(out / "model.onnx"),
        input_names=["input_ids", "attention_mask"],
        output_names=["logits"],
        dynamic_axes={
            "input_ids": {0: "windows", 1: "tokens"},
            "attention_mask": {0: "windows", 1: "tokens"},
            "logits": {0: "windows", 1: "tokens"},
        },
        opset_version=17,
        dynamo=False,
    )

    # The export records one run of the model, so prove the graph matches PyTorch on what it will
    # really get: the longest dev document, several windows, padded to one width.
    import onnxruntime as ort

    longest = max(dev_docs, key=lambda d: len(d.text))
    _, ids, mask = NerExtractor(tokenizer, torch_run).batch(longest.text)
    with torch.no_grad():
        expected = model(
            input_ids=torch.from_numpy(ids), attention_mask=torch.from_numpy(mask)
        ).logits.numpy()
    session = ort.InferenceSession(str(out / "model.onnx"))
    got = session.run(["logits"], {"input_ids": ids, "attention_mask": mask})[0]
    diff = float(abs(expected - got)[mask == 1].max())
    report["onnx_check"] = {"windows": int(ids.shape[0]), "max_abs_logit_diff": diff}
    print(f"ONNX vs PyTorch on {ids.shape[0]} padded windows: max logit difference {diff:.2e}")
    if diff > 1e-3:
        raise SystemExit("The ONNX export does not match PyTorch; not quantising it.")

    # Shape inference and graph clean-up first, as onnxruntime recommends for int8.
    from onnxruntime.quantization.shape_inference import quant_pre_process

    quant_pre_process(str(out / "model.onnx"), str(out / "model.prep.onnx"))
    quantize_dynamic(out / "model.prep.onnx", out / "model.int8.onnx", weight_type=QuantType.QInt8)
    tokenizer.save_pretrained(out)
    sizes = {f: (out / f).stat().st_size / 1e6 for f in ("model.onnx", "model.int8.onnx")}
    report["size_mb"] = sizes

    report["dev_onnx_int8"] = evaluate(NerExtractor.from_onnx(out), dev_docs)
    print("dev, int8 ONNX:", json.dumps(report["dev_onnx_int8"], indent=1))
    (out / "train_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"sizes (MB): {sizes}\nsaved to {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export")
    exp.add_argument("--labels", type=Path, default=Path("data/docs/labels.jsonl"))
    exp.add_argument("--out", type=Path, default=Path("data/ner_train_dev.jsonl.gz"))
    tr = sub.add_parser("train")
    tr.add_argument("--data", type=Path, required=True)
    tr.add_argument("--out", type=Path, default=Path("ner_model"))
    tr.add_argument("--epochs", type=float, default=3)
    tr.add_argument("--lr", type=float, default=3e-5)
    tr.add_argument("--batch", type=int, default=16)
    tr.add_argument("--max-docs", type=int, default=None, help="small rehearsal run")
    args = parser.parse_args()
    if args.command == "export":
        export(args.labels, args.out)
    else:
        train(args.data, args.out, args.epochs, args.lr, args.batch, args.max_docs)


if __name__ == "__main__":
    main()
