"""PDF gap-analysis items: coverage matrix, provision map, TKDL status, feedback, lifecycle, OCR, retention, metrics, privacy."""
import shutil

import pytest


def _demo_id(client, h):
    return next(i["id"] for i in client.get("/api/innovations", headers=h).json()["data"] if i["is_demo"])


def test_coverage_matrix_is_computed_and_honest(client, researcher):
    d = client.get("/api/coverage", headers=researcher).json()["data"]
    cells = {r["jurisdiction"]: r["cells"] for r in d["matrix"]}
    assert cells["IN"]["REGULATORY"]["status"] == "Built"
    assert cells["US"]["REGULATORY"]["status"] == "Built"
    assert cells["AU"]["REGULATORY"]["status"] == "Built"
    assert all(c["status"] in ("Planned", "N/A") for c in cells["EU"].values())
    assert cells["INTERNATIONAL"]["SCIENTIFIC"]["status"] == "Built"
    assert d["corpus"]["documents"] >= 39 and d["corpus"]["chunks"] >= 80 and d["corpus"]["demo_documents"] >= 9


def test_eu_question_is_refused(db, workspace_id):
    from app.services.research import run_research
    out = run_research(db, "What does the European Union require to register an Ayurvedic medicine with the EMA?", workspace_id=workspace_id)
    assert out["type"] == "abstention"


def test_provision_map_flags_relevant_provisions(client, researcher):
    iid = _demo_id(client, researcher)
    p = client.get(f"/api/innovations/{iid}/provisions", headers=researcher).json()["data"]
    ids = {x["id"] for x in p["provisions"]}
    assert {"IN-PA-3p", "IN-PA-3d", "IN-BD-6", "US-350b", "US-321g", "AU-REG"} <= ids
    assert all(x["document_title"] for x in p["provisions"])
    assert "not a determination" in p["boundary"]


def test_summary_has_structured_cards_and_tkdl_status(client, researcher):
    iid = _demo_id(client, researcher)
    s = client.get(f"/api/innovations/{iid}/summary", headers=researcher).json()["data"]
    assert {"classification", "regulatory_pathway", "ip_considerations", "evidence", "next_steps"} <= set(s)
    assert s["ip_considerations"]["tkdl_access"]["status"] == "RESTRICTED_NOT_QUERIED"
    assert s["history"] and s["history"][0]["source_versions"]
    tk = client.get(f"/api/innovations/{iid}/tk", headers=researcher).json()["data"]
    assert tk["tkdl_access"]["status"] == "RESTRICTED_NOT_QUERIED" and "NOT a finding" in tk["tkdl_access"]["meaning"]


def test_feedback_workflow_with_snapshot(client, researcher, reviewer):
    r = client.post("/api/chat", headers=researcher, json={"message": "What does 21 CFR 101.93 require?", "jurisdiction": "US"}).json()["data"]
    mid = r["message"]["id"]
    fb = client.post("/api/feedback", headers=researcher, json={"message_id": mid, "category": "CITATION_NOT_SUPPORTING",
                                                              "reason": "Point 2 cites the wrong section", "target": {"key_point_id": 2}}).json()["data"]
    assert fb["status"] == "OPEN" and fb["snapshot"]["sources"] and fb["snapshot"]["sources"][0]["title"]
    upd = client.patch(f"/api/feedback/{fb['id']}", headers=reviewer, json={"status": "RESOLVED", "resolution_note": "Checked"}).json()["data"]
    assert upd["status"] == "RESOLVED"
    msgs = client.get(f"/api/conversations/{r['conversation']['id']}/messages", headers=researcher).json()["data"]
    assert msgs[-1]["flagged"] is True


def test_update_queue_and_document_curation(client, admin, db):
    q = client.get("/api/admin/update-queue", headers=admin).json()["data"]
    assert q and q[0]["update_status"] in ("Overdue", "Review due", "Superseded", "Never checked")
    doc_id = q[0]["document_id"]
    d = client.patch(f"/api/documents/{doc_id}/review", headers=admin, json={"action": "mark_checked", "note": "Re-verified"}).json()["data"]
    assert d["update_status"] == "Up to date"


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_scanned_pdf_is_ocrd(client, researcher):
    import pymupdf as fitz

    # Build an image-only PDF (no text layer) to force the OCR path.
    src = fitz.open()
    page = src.new_page(width=600, height=300)
    page.insert_text((40, 120), "Section 4 Ashwagandha root extract specification withanolides", fontsize=20)
    pix = page.get_pixmap(dpi=150)
    img_pdf = fitz.open()
    p2 = img_pdf.new_page(width=600, height=300)
    p2.insert_image(p2.rect, pixmap=pix)
    data = img_pdf.tobytes()
    r = client.post("/api/documents", headers=researcher, files={"file": ("scan.pdf", data, "application/pdf")},
                    data={"title": "Scanned spec", "domain": "SCIENTIFIC", "privacy_ack": "true"})
    job = r.json()["data"]["job"]
    j = client.get(f"/api/ingestion-jobs/{job['id']}", headers=researcher).json()["data"]
    assert j["job"]["status"] == "SUCCEEDED", j["job"]
    assert any(s["step"] == "ocr" and s.get("mean_confidence") for s in j["job"]["steps"])
    assert j["document"]["extraction_method"] == "PYMUPDF+TESSERACT_OCR" and j["document"]["ocr_confidence"] > 0
    detail = client.get(f"/api/documents/{j['document']['id']}", headers=researcher).json()["data"]
    assert "ashwagandha" in " ".join(c["content"] for c in detail["chunks"]).lower()


def test_retention_metrics_privacy(client, admin, researcher):
    r = client.post("/api/admin/retention/run?dry_run=true", headers=admin).json()["data"]
    assert r["dry_run"] is True and r["workspaces"]
    m = client.get("/api/metrics", headers=admin).json()["data"]
    assert m["latency_ms"]["p50"] is not None and "projection_10k_users" in m and m["corpus"]["documents"] >= 39
    p = client.get("/api/privacy", headers=researcher).json()["data"]
    assert p["retention"]["policy"] and p["llm"]["policy"] and p["upload_notice"]


def test_confidence_is_heuristic_with_signals(db, workspace_id):
    from app.services.research import run_research
    out = run_research(db, "What does Section 3(p) of the Indian Patents Act exclude?", workspace_id=workspace_id, jurisdiction="IN")
    c = out["confidence"]
    assert c["heuristic"] is True and len(c["signals"]) == 6 and "not a calibrated" in c["explanation"]
    assert any("demo" in p for p in c["penalties"]) or c["penalties"] == []
    assert out["response_language"] == "en" and out["source_languages"] == ["en"]
