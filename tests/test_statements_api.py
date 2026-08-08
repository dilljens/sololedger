"""Tests for the statements API — upload, list, get (with a real PDF)."""

import os

import pytest
from fastapi.testclient import TestClient


def make_pdf(text: str) -> bytes:
    """Build a minimal valid PDF whose text pdfminer can extract.

    A single page with one text object; xref offsets computed exactly so
    strict parsers accept it.
    """
    escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
        b" /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    return bytes(out)


@pytest.fixture
def client(isolated_environment):
    from app.api import app as api_app
    os.environ["SOLOLEDGER_OPEN_MODE"] = "true"
    c = TestClient(api_app)
    yield c
    os.environ.pop("SOLOLEDGER_OPEN_MODE", None)


class TestStatementsAPI:
    def test_upload_classifies_and_files(self, client):
        pdf = make_pdf("WELLS FARGO  Statement of Account "
                       "January 1, 2026 through January 31, 2026")
        r = client.post(
            "/api/v1/statements/upload",
            files={"file": ("statement.pdf", pdf, "application/pdf")},
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["success"] is True
        assert data["institution"] == "wells_fargo"
        assert data["id"] is not None

    def test_upload_with_overrides(self, client):
        pdf = make_pdf("Some generic text without an institution signature")
        r = client.post(
            "/api/v1/statements/upload",
            files={"file": ("stmt.pdf", pdf, "application/pdf")},
            data={"institution": "chase", "account_mask": "4321", "period": "2026-02"},
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["institution"] == "chase"
        assert data["period"] == "2026-02"
        assert "4321" in data["filed_path"]

    def test_list_and_get(self, client):
        pdf = make_pdf("WELLS FARGO Statement January 1, 2026 through January 31, 2026")
        r = client.post(
            "/api/v1/statements/upload",
            files={"file": ("statement.pdf", pdf, "application/pdf")},
        )
        assert r.status_code == 200
        sid = r.json()["data"]["id"]

        r = client.get("/api/v1/statements")
        assert r.status_code == 200
        statements = r.json()["data"]["statements"]
        assert len(statements) >= 1
        mine = next(s for s in statements if s["id"] == sid)
        assert mine["institution"] == "wells_fargo"
        assert mine["exists"] is True

        r = client.get(f"/api/v1/statements/{sid}")
        assert r.status_code == 200
        one = r.json()["data"]
        assert one["filename"] == "statement.pdf"
        assert one["absolute_path"] and os.path.exists(one["absolute_path"])

    def test_get_missing(self, client):
        r = client.get("/api/v1/statements/999999")
        assert r.status_code == 404
