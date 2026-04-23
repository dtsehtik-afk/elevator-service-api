"""Tests for inspection report listing, status transitions, and claim flow."""

import pytest
import uuid
from datetime import date


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def inspection_report(db, sample_elevator):
    """Create a FAIL inspection report directly in DB (no file upload needed)."""
    from app.models.inspection_report import InspectionReport
    report = InspectionReport(
        elevator_id=sample_elevator.id,
        source="upload",
        file_name="test_report.pdf",
        raw_address="1 HaShalom Rd",
        raw_city="Tel Aviv",
        inspection_date=date(2024, 1, 15),
        result="FAIL",
        inspector_name="Inspector Gadget",
        deficiency_count=3,
        deficiencies=[{"name": "door sensor", "done": False}, {"name": "emergency light", "done": False}, {"name": "cable", "done": False}],
        report_status="OPEN",
        match_status="AUTO_MATCHED",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@pytest.fixture()
def pass_report(db, sample_elevator):
    """Create a PASS inspection report directly in DB."""
    from app.models.inspection_report import InspectionReport
    report = InspectionReport(
        elevator_id=sample_elevator.id,
        source="upload",
        inspection_date=date(2024, 2, 1),
        result="PASS",
        deficiency_count=0,
        report_status="NA",
        match_status="AUTO_MATCHED",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def test_list_inspections(client, admin_token, inspection_report):
    resp = client.get("/inspections", headers=auth(admin_token))
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(str(r["id"]) == str(inspection_report.id) for r in data)


def test_list_inspections_filter_by_report_status(client, admin_token, inspection_report, pass_report):
    # Filter by report_status (supported filter) — OPEN reports only
    resp = client.get("/inspections?report_status=OPEN", headers=auth(admin_token))
    assert resp.status_code == 200
    assert all(r["report_status"] == "OPEN" for r in resp.json())


def test_claim_inspection_report(client, tech_token, inspection_report):
    rid = str(inspection_report.id)
    resp = client.post(
        f"/inspections/claim/{rid}",
        headers=auth(tech_token),
    )
    assert resp.status_code == 200
    # Claim returns {"ok": True, "technician_name": ...}
    assert resp.json()["ok"] is True


def test_checklist_update(client, admin_token, inspection_report):
    # Checklist update expects [{index, done}] list
    rid = str(inspection_report.id)
    resp = client.patch(
        f"/inspections/checklist/{rid}",
        json=[{"index": 0, "done": True}],
        headers=auth(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_inspection_not_found(client, admin_token):
    resp = client.get(f"/inspections/{uuid.uuid4()}/file", headers=auth(admin_token))
    assert resp.status_code == 404


def test_inspection_open_has_open_status(inspection_report):
    assert inspection_report.report_status == "OPEN"
    assert inspection_report.deficiency_count == 3


def test_inspection_pass_has_na_status(pass_report):
    assert pass_report.report_status == "NA"
    assert pass_report.deficiency_count == 0
