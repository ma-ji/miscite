from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NliVerdict:
    label: str  # "entailment" | "contradiction" | "neutral"
    confidence: float
    probs: dict[str, float]


class LocalNliModel:
    def __init__(self, model_name: str):
        try:
            import torch  # type: ignore
            from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Local NLI requires 'torch' and 'transformers'. Install them or disable MISCITE_ENABLE_LOCAL_NLI."
            ) from e

        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(model_name)

        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._device = device
        self._model.to(device)
        self._model.eval()

        # Normalize label mapping.
        self._id2label = {int(k): str(v).lower() for k, v in getattr(self._model.config, "id2label", {}).items()}

    def classify(self, *, premise: str, hypothesis: str) -> NliVerdict:
        torch = self._torch

        def _run(device: str):
            inputs = self._tokenizer(
                premise,
                hypothesis,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            inputs = {k: v.to(device) for k, v in inputs.items()}
            with torch.no_grad():
                out = self._model(**inputs)
            probs = torch.softmax(out.logits[0], dim=-1).detach().cpu().tolist()
            return probs

        try:
            probs = _run(self._device)
        except RuntimeError as e:
            msg = str(e).lower()
            if "out of memory" in msg and self._device.startswith("cuda"):
                raise RuntimeError("CUDA out of memory during NLI inference (no CPU fallback enabled).") from e
            raise

        by_label: dict[str, float] = {}
        for idx, p in enumerate(probs):
            lbl = self._id2label.get(idx, str(idx))
            by_label[lbl] = float(p)

        # Many MNLI-style checkpoints use these canonical labels.
        label_map = {
            "entailment": by_label.get("entailment", 0.0),
            "contradiction": by_label.get("contradiction", 0.0),
            "neutral": by_label.get("neutral", 0.0),
        }

        best = max(label_map.items(), key=lambda kv: kv[1])
        return NliVerdict(label=best[0], confidence=best[1], probs=label_map)
