import json
from pathlib import Path

from fastapi.testclient import TestClient

from pipeline_dashboard_backend import create_app


def write_json(
    path: Path,
    payload: object,
) -> None:
    path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def make_client() -> TestClient:
    return TestClient(create_app())


def build_dashboard(
    client: TestClient,
    tmp_path: Path,
) -> None:
    metrics_path = tmp_path / "metrics.json"
    health_path = tmp_path / "health.json"

    write_json(
        metrics_path,
        {
            "report_type": "metrics",
            "generated_at": "2026-07-13T15:00:00+00:00",
            "status": "healthy",
            "summary": {
                "pipeline_count": 8,
            },
            "metrics": [
                {
                    "name": "success_rate",
                    "value": 98.5,
                    "unit": "percent",
                    "labels": {
                        "environment": "test",
                    },
                },
                {
                    "name": "average_latency_ms",
                    "value": 25.0,
                    "unit": "milliseconds",
                    "labels": {
                        "environment": "test",
                    },
                },
            ],
        },
    )

    write_json(
        health_path,
        {
            "report_type": "health",
            "generated_at": "2026-07-13T15:01:00+00:00",
            "status": "degraded",
            "summary": {
                "failed_pipeline_count": 1,
            },
        },
    )

    response = client.post(
        "/api/v1/dashboard/build",
        json={
            "artifact_paths": [
                str(metrics_path),
                str(health_path),
            ],
            "generated_at": "2026-07-13T16:00:00+00:00",
            "snapshot_id": "dashboard-api-test",
            "require_source_types": [
                "metrics",
                "health",
            ],
        },
    )

    assert response.status_code == 200


def test_health_endpoint() -> None:
    response = make_client().get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "pipeline-dashboard-backend",
        "version": "0.1.0",
    }


def test_info_endpoint() -> None:
    response = make_client().get("/api/v1/info")
    payload = response.json()

    assert response.status_code == 200
    assert payload["api_version"] == "v1"
    assert payload["state_backend"] == "memory"
    assert "dashboard_build" in payload["capabilities"]


def test_dashboard_is_missing_before_first_build() -> None:
    response = make_client().get("/api/v1/dashboard")

    assert response.status_code == 404
    assert response.json()["detail"] == ("no dashboard snapshot has been built")


def test_build_dashboard_endpoint(
    tmp_path: Path,
) -> None:
    client = make_client()

    build_dashboard(client, tmp_path)

    response = client.get("/api/v1/dashboard")
    payload = response.json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["report"]["snapshot"]["snapshot_id"] == ("dashboard-api-test")
    assert payload["report"]["snapshot"]["overall_status"] == ("degraded")


def test_build_rejects_empty_artifact_paths() -> None:
    response = make_client().post(
        "/api/v1/dashboard/build",
        json={"artifact_paths": []},
    )

    assert response.status_code == 422


def test_build_rejects_unknown_request_field(
    tmp_path: Path,
) -> None:
    response = make_client().post(
        "/api/v1/dashboard/build",
        json={
            "artifact_paths": [str(tmp_path / "metrics.json")],
            "unknown_field": True,
        },
    )

    assert response.status_code == 422


def test_build_returns_failed_report_for_missing_file(
    tmp_path: Path,
) -> None:
    response = make_client().post(
        "/api/v1/dashboard/build",
        json={"artifact_paths": [str(tmp_path / "missing.json")]},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["success"] is False
    assert "does not exist" in payload["report"]["errors"][0]


def test_build_returns_400_when_isolation_disabled(
    tmp_path: Path,
) -> None:
    response = make_client().post(
        "/api/v1/dashboard/build",
        json={
            "artifact_paths": [str(tmp_path / "missing.json")],
            "continue_on_error": False,
        },
    )

    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]


def test_snapshot_endpoint(
    tmp_path: Path,
) -> None:
    client = make_client()
    build_dashboard(client, tmp_path)

    response = client.get("/api/v1/dashboard/snapshot")
    payload = response.json()

    assert response.status_code == 200
    assert payload["snapshot_id"] == "dashboard-api-test"
    assert payload["overall_status"] == "degraded"


def test_list_panels(
    tmp_path: Path,
) -> None:
    client = make_client()
    build_dashboard(client, tmp_path)

    response = client.get("/api/v1/dashboard/panels")
    payload = response.json()

    assert response.status_code == 200
    assert payload["count"] == 3
    assert [panel["panel_id"] for panel in payload["panels"]] == [
        "overview",
        "metrics",
        "health",
    ]


def test_list_panels_filters_by_type(
    tmp_path: Path,
) -> None:
    client = make_client()
    build_dashboard(client, tmp_path)

    response = client.get(
        "/api/v1/dashboard/panels",
        params={"panel_type": "health"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["count"] == 1
    assert payload["panels"][0]["panel_id"] == "health"


def test_list_panels_filters_by_status(
    tmp_path: Path,
) -> None:
    client = make_client()
    build_dashboard(client, tmp_path)

    response = client.get(
        "/api/v1/dashboard/panels",
        params={"status": "healthy"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["count"] == 1
    assert payload["panels"][0]["panel_id"] == "metrics"


def test_get_panel(
    tmp_path: Path,
) -> None:
    client = make_client()
    build_dashboard(client, tmp_path)

    response = client.get("/api/v1/dashboard/panels/metrics")

    assert response.status_code == 200
    assert response.json()["title"] == "Pipeline Metrics"


def test_get_panel_returns_404(
    tmp_path: Path,
) -> None:
    client = make_client()
    build_dashboard(client, tmp_path)

    response = client.get("/api/v1/dashboard/panels/runtime")

    assert response.status_code == 404


def test_find_metrics_by_partial_name(
    tmp_path: Path,
) -> None:
    client = make_client()
    build_dashboard(client, tmp_path)

    response = client.get(
        "/api/v1/dashboard/metrics",
        params={"name_contains": "latency"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["count"] == 1
    assert payload["metrics"][0]["metric"]["name"] == ("average_latency_ms")


def test_find_metrics_by_numeric_range(
    tmp_path: Path,
) -> None:
    client = make_client()
    build_dashboard(client, tmp_path)

    response = client.get(
        "/api/v1/dashboard/metrics",
        params={
            "unit": "percent",
            "minimum": 95,
            "maximum": 100,
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["count"] == 1
    assert payload["metrics"][0]["metric"]["value"] == 98.5


def test_metric_lookup(
    tmp_path: Path,
) -> None:
    client = make_client()
    build_dashboard(client, tmp_path)

    response = client.get("/api/v1/dashboard/metrics/average_latency_ms")

    assert response.status_code == 200
    assert response.json()["panel_id"] == "metrics"


def test_metric_lookup_returns_404(
    tmp_path: Path,
) -> None:
    client = make_client()
    build_dashboard(client, tmp_path)

    response = client.get("/api/v1/dashboard/metrics/not-found")

    assert response.status_code == 404


def test_summary_endpoint(
    tmp_path: Path,
) -> None:
    client = make_client()
    build_dashboard(client, tmp_path)

    response = client.get("/api/v1/dashboard/summary")
    payload = response.json()

    assert response.status_code == 200
    assert payload["snapshot_id"] == "dashboard-api-test"
    assert payload["overall_status"] == "degraded"
    assert payload["panel_count"] == 3
    assert payload["source_count"] == 2


def test_openapi_document_is_available() -> None:
    response = make_client().get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == ("Pipeline Dashboard Backend")
