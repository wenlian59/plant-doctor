from io import BytesIO

import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForImageClassification

from app.config import MODEL_PATH

_processor = AutoImageProcessor.from_pretrained(MODEL_PATH)
_model = AutoModelForImageClassification.from_pretrained(MODEL_PATH)
_model.eval()


def classify(image_bytes: bytes) -> tuple[str, float]:
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    inputs = _processor(images=image, return_tensors="pt")

    with torch.no_grad():
        logits = _model(**inputs).logits

    probs = torch.nn.functional.softmax(logits, dim=-1)[0]
    top_idx = int(torch.argmax(probs))

    label = _model.config.id2label[top_idx]
    confidence = float(probs[top_idx])
    return label, confidence
