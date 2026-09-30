"""End-to-end flow (spec §92): user → login → workspace → innovation → profile → research
→ evidence → answer → verify → patents → regulatory comparison → gaps → escalation → report."""
import uuid

from conftest import login

WIZARD = {
    "basic": {"name": "Integration Test Formulation", "description": "Oral tablet of Ashwagandha root extract made by enzyme-assisted aqueous extraction.",
              "intended_use": "Support a healthy stress response", "innovation_type": "Formulation"},
    "ingredients": [{"common_name": "Ashwagandha", "botanical_name": "Withania somnifera", "extract": "Root extract", "quantity": "250 mg"},
                    {"common_name": "Brahmi"}],
    "formulation": {"dosage_form": "Tablet", "delivery_mechanism": "Immediate release"},
    "process": {"extraction": "Enzyme-assisted aqueous extraction with cellulase and pectinase at 45 °C", "manufacturing": "Pune, India"},
    "claims": ["Supports a healthy stress response", "Treats insomnia"],
    "markets": ["IN", "US", "AU"],
    "confidentiality": "CONFIDENTIAL",
}


def test_full_flow(client):
    email = f"flow-{uuid.uuid4().hex[:8]}@example.org"
    # Create user → login
    r = client.post("/api/auth/register", json={"name": "Flow Tester", "email": email, "password": "Str0ngPass", "workspace": "Flow WS"})
    assert r.status_code == 200
    h = login(client, email, "Str0ngPass")

    # Create workspace and select it
    ws = client.post("/api/workspaces", headers=h, json={"name": "Flow Confidential WS", "confidential_mode": True}).json()["data"]
    h = {**h, "X-Workspace-Id": ws["id"]}
    assert client.get(f"/api/workspaces/{ws['id']}", headers=h).json()["data"]["role"] == "OWNER"

    # Confidential innovation requires acknowledgement
    r = client.post("/api/innovations", headers=h, json={"wizard": WIZARD})
    assert r.status_code == 428 and r.json()["error"]["code"] == "CONFIDENTIALITY_ACK_REQUIRED"

    # Create innovation + generate profile + run analysis
    r = client.post("/api/innovations", headers=h, json={"wizard": WIZARD, "acknowledge_confidentiality": True})
    assert r.status_code == 200, r.text
    inn = r.json()["data"]
    iid = inn["id"]
    prof = inn["profile"]
    assert prof["route"] == "Oral"
    assert any("Brahmi" in a for a in prof["ambiguities"])
    assert any("disease/treatment claim" in a for a in prof["ambiguities"])
    assert any(f["feature_type"] == "EXTRACTION" for f in inn["features"])
    assert inn["confidential_warning"]

    # Edit + confirm profile
    r = client.patch(f"/api/innovations/{iid}/profile", headers=h, json={"manufacturing_location": "Pune, Maharashtra, India", "confirm": True})
    assert r.json()["data"]["profile"]["user_confirmed"] is True

    # Research → retrieve evidence → answer with citations
    r = client.post("/api/chat", headers=h, json={"message": "What approvals are needed in India to patent an invention based on an Indian medicinal plant?",
                                                  "innovation_id": iid, "jurisdiction": "IN"})
    assert r.status_code == 200, r.text
    msg = r.json()["data"]["message"]
    payload = msg["payload"]
    assert payload["type"] == "answer" and payload["evidence"] and payload["key_points"]
    conv_id = r.json()["data"]["conversation"]["id"]
    msgs = client.get(f"/api/conversations/{conv_id}/messages", headers=h).json()["data"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]

    # Verify a citation explicitly
    ev = payload["evidence"][0]
    v = client.post("/api/citations/verify", headers=h, json={"claim": ev["passage"][:180], "chunk_id": ev["chunk_id"]}).json()["data"]
    assert v["status"] in ("SUPPORTED", "PARTIALLY_SUPPORTED")
    # Add that passage to innovation evidence
    assert client.post(f"/api/innovations/{iid}/evidence", headers=h, json={"chunk_id": ev["chunk_id"], "evidence_type": "IP"}).status_code == 200
    evidence = client.get(f"/api/innovations/{iid}/evidence", headers=h).json()["data"]
    assert any(e["added_by"] == "USER" for e in evidence) and any(e["evidence_type"] == "SCIENTIFIC" for e in evidence)

    # Scientific evidence distinguishes ingredient vs formulation
    sci = client.get(f"/api/innovations/{iid}/scientific", headers=h).json()["data"]
    assert sci["cards"] and sci["formulation_evidence_found"] is False
    assert all("does NOT establish" in c["applicability"] for c in sci["cards"] if c["evidence_level"] == "INGREDIENT")

    # Patents: feature matrix + families
    pat = client.get(f"/api/innovations/{iid}/patents", headers=h).json()["data"]
    assert pat["matrix"], "expected extraction feature to match the fictional enzyme-extraction patent family"
    assert any(f["family_id"] == "DEMO-FAM-002" and len(f["members"]) == 2 for f in pat["families"])
    assert "Professional review is required" in pat["review_note"]
    ps = client.post("/api/search/patents", headers=h, json={"query": "curcumin phospholipid complex piperine"}).json()["data"]
    assert ps["families"][0]["family_id"] == "DEMO-FAM-001" and len(ps["families"][0]["members"]) >= 2

    # Classification + regulatory comparison
    cls = client.get(f"/api/innovations/{iid}/classification", headers=h).json()["data"]
    answers = {**cls["answers"], "food_positioning": "no"}
    res = client.post(f"/api/innovations/{iid}/classification", headers=h, json={"answers": answers}).json()["data"]
    assert set(res["results"]) == {"IN", "US", "AU"}
    assert res["results"]["US"]["provisional_key"] == "US_BOTANICAL_DRUG"  # 'Treats insomnia' is a disease claim
    assert all(x["human_review_required"] for x in res["results"].values())
    reg = client.get(f"/api/innovations/{iid}/regulatory", headers=h).json()["data"]
    dims = {row["dimension"] for row in reg["comparison"]}
    assert {"Possible category", "Authority", "Open questions", "Freshness", "Human review"} <= dims
    assert reg["passport"]["IN"]["pathway"]["source_document"]["title"]

    # Gaps, risk map, graph
    gaps = client.get(f"/api/innovations/{iid}/evidence-gaps", headers=h).json()["data"]
    keys = {g["gap_key"] for g in gaps}
    assert "formulation-evidence" in keys and "species:Brahmi" in keys and "us-ndi" in keys
    assert any(g["severity"] == "CRITICAL" and g["category"] == "CLAIMS" for g in gaps)
    g0 = gaps[0]
    assert client.patch(f"/api/innovations/{iid}/evidence-gaps/{g0['id']}", headers=h, json={"status": "ACKNOWLEDGED"}).json()["data"]["status"] == "ACKNOWLEDGED"
    risks = client.get(f"/api/innovations/{iid}/risk-map", headers=h).json()["data"]
    assert len(risks) == 8 and risks[0]["severity"] in ("CRITICAL", "HIGH")
    graph = client.get(f"/api/innovations/{iid}/graph", headers=h).json()["data"]
    types = {n["type"] for n in graph["nodes"]}
    assert {"Innovation", "Ingredient", "Patent", "Scientific Study", "Regulation", "Authority", "Jurisdiction", "Evidence Gap"} <= types
    assert all(e["provenance"].get("source") for e in graph["edges"])

    # Escalation
    esc = client.post("/api/escalations", headers=h, json={"innovation_id": iid, "type": "IP_REVIEW", "reason": "Overlap with enzyme-extraction family"}).json()["data"]
    assert esc["status"] == "OPEN" and esc["packet"]["patent_findings"]["families"] and esc["open_questions"]
    assert client.patch(f"/api/escalations/{esc['id']}", headers=h, json={"status": "IN_REVIEW"}).json()["data"]["status"] == "IN_REVIEW"

    # Report + export
    rep = client.post("/api/reports", headers=h, json={"innovation_id": iid}).json()["data"]
    for section in ("Executive Summary", "Innovation Profile", "Traditional Knowledge Context", "Scientific Evidence", "Patent / Prior-Art Findings",
                    "Feature Matrix", "Regulatory Passport", "Jurisdiction Comparison", "Evidence Gaps", "Risk Map", "Citation Verification",
                    "Conflicting Sources", "Open Questions", "Human Review Recommendations", "Source Registry", "Audit Metadata"):
        assert f"## {section}" in rep["markdown"], section
    md = client.get(f"/api/reports/{rep['id']}/markdown", headers=h)
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")

    # Audit trail captured the journey
    actions = {a["action"] for a in client.get("/api/audit", headers=h).json()["data"]}
    for a in ("innovation_created", "profile_generated", "search_started", "search_completed", "citation_verified", "escalation_created", "report_generated"):
        assert a in actions, a

    # Completion and dashboard
    detail = client.get(f"/api/innovations/{iid}", headers=h).json()["data"]
    assert detail["completion"]["percent"] == 100
    dash = client.get("/api/dashboard", headers=h).json()["data"]
    assert dash["stats"]["total_innovations"] == 1 and dash["stats"]["open_escalations"] == 1


def test_health_endpoints(client):
    for path in ("/health", "/health/database", "/health/vector", "/health/llm"):
        r = client.get(path)
        assert r.status_code == 200 and r.json()["success"] is True
    assert client.get("/health").json()["data"]["pgvector"] is True


def test_evaluation_suite_runs(client, admin):
    r = client.post("/api/admin/evaluations/run", headers=admin)
    assert r.status_code == 200, r.text
    m = r.json()["data"]["metrics"]
    assert m["questions"] == 20 and m["test_set_size"] == 20
    assert m["recall_at_k"] is not None and m["latency_p95_ms"] is not None
    assert m["baselines"]["bm25_keyword_only"]["recall_at_k"] is not None
    assert m["baselines"]["always_answer"]["abstention_accuracy"] < m["abstention_accuracy"]
    assert m["classification"]["agreement"] >= 0.75
    assert m["abstention_accuracy"] >= 0.8
    assert m["jurisdiction_accuracy"] >= 0.8
    assert m["citation_correctness"] == 1.0
