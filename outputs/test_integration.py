import importlib.util
import io
import json
import uuid
from pathlib import Path

import fitz
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = REPO_ROOT / "backend" / "main.py"

spec = importlib.util.spec_from_file_location("pii_shield_backend", BACKEND_PATH)
backend_main = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(backend_main)

client = TestClient(backend_main.app)


def create_sample_pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text(
        fitz.Point(72, 96),
        "Aadhaar 2345 6789 3456\nPAN ABCDE1234F\nEmail secure.user@shieldmail.in",
        fontsize=16,
    )
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def test_health_contract():
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert isinstance(payload["ocr_available"], bool)
    assert payload["version"] == "1.0.0"


def test_scan_returns_contract_shape_and_valid_finding_ids():
    pdf_bytes = create_sample_pdf_bytes()
    response = client.post(
        "/scan",
        files={"file": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["mode"] in {"pdf_text", "ocr_image"}
    assert isinstance(payload["page_count"], int)
    assert payload["page_count"] == 1
    assert len(payload["pages"]) == 1

    page = payload["pages"][0]
    assert page["page_number"] == 1
    assert isinstance(page["image_b64"], str)
    assert page["width"] > 0
    assert page["height"] > 0

    findings = payload["findings"]
    assert len(findings) >= 3
    assert {finding["type"] for finding in findings} >= {"aadhaar", "pan", "email"}

    for finding in findings:
        parsed = uuid.UUID(finding["id"])
        assert parsed.version == 4
        assert finding["severity"] in {"high", "medium"}
        assert 0.0 <= finding["confidence"] <= 1.0
        assert isinstance(finding["value"], str)
        assert isinstance(finding["raw_value"], str)
        assert finding["page"] == 1
        if finding["bbox"] is not None:
            assert 0.0 <= finding["bbox"]["x"] <= 1.0
            assert 0.0 <= finding["bbox"]["y"] <= 1.0
            assert 0.0 <= finding["bbox"]["w"] <= 1.0
            assert 0.0 <= finding["bbox"]["h"] <= 1.0

    risk_score = payload["risk_score"]
    expected_high = sum(1 for finding in findings if finding["severity"] == "high")
    expected_medium = sum(1 for finding in findings if finding["severity"] == "medium")
    assert risk_score["total_findings"] == len(findings)
    assert risk_score["high_count"] == expected_high
    assert risk_score["medium_count"] == expected_medium
    assert risk_score["level"] == ("HIGH" if expected_high else "MEDIUM" if expected_medium else "SAFE")


def test_redact_accepts_finding_id_array_and_returns_pdf():
    pdf_bytes = create_sample_pdf_bytes()
    scan_response = client.post(
        "/scan",
        files={"file": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert scan_response.status_code == 200, scan_response.text

    findings = scan_response.json()["findings"]
    redactable_ids = [finding["id"] for finding in findings if finding["bbox"] is not None]
    assert redactable_ids

    response = client.post(
        "/redact",
        files={"file": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"finding_ids": json.dumps(redactable_ids)},
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF")


def test_redact_rejects_invalid_finding_ids():
    pdf_bytes = create_sample_pdf_bytes()
    response = client.post(
        "/redact",
        files={"file": ("sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"finding_ids": json.dumps(["not-a-real-finding-id"])},
    )

    assert response.status_code == 400
    assert response.json()["error"] in {"invalid_finding_ids", "file_mismatch"}
