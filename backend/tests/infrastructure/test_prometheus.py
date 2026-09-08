from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.observability.domain.metrics import Metric, MetricQuery, MetricRangeQuery
from app.observability.infrastructure.prometheus_query import PrometheusQueryAdapter, promql


@pytest.mark.asyncio
async def test_prometheus_cache_nan_privacy_and_fixed_query():
    requests = []

    def response(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {
                            "metric": {"id": "abc", "name": "backend", "secret": "do-not-export"},
                            "value": [1, "NaN"],
                        }
                    ],
                },
            },
        )

    async with httpx.AsyncClient(
        base_url="http://prometheus", transport=httpx.MockTransport(response)
    ) as client:
        adapter = PrometheusQueryAdapter(client, enabled=True)
        first = await adapter.instant(MetricQuery(Metric.CPU))
        assert first == await adapter.instant(MetricQuery(Metric.CPU))
        assert len(requests) == 1
        assert first.series[0].samples == [(1, None)]
        assert "secret" not in first.series[0].labels
        assert "query" in requests[0].url.params


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "connection",
        "malformed",
        "warnings",
        "cardinality",
        "invalid_payload",
        "invalid_row",
        "invalid_labels",
    ],
)
async def test_failures_do_not_raise_into_execution(failure):
    def response(request):
        if failure == "connection":
            raise httpx.ConnectError("sensitive upstream details", request=request)
        if failure == "malformed":
            return httpx.Response(200, text="not json")
        if failure == "invalid_payload":
            return httpx.Response(200, json=[])
        if failure in {"invalid_row", "invalid_labels"}:
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {"result": [None if failure == "invalid_row" else {"metric": []}]},
                },
            )
        return httpx.Response(
            200,
            json={
                "status": "success",
                "warnings": ["partial"] if failure == "warnings" else [],
                "data": {"result": [{}] * 201},
            },
        )

    async with httpx.AsyncClient(
        base_url="http://prometheus", transport=httpx.MockTransport(response)
    ) as client:
        result = await PrometheusQueryAdapter(client, enabled=True).instant(
            MetricQuery(Metric.HOST_CPU)
        )
        assert result.status == "unavailable"
        assert result.series == []
        assert "sensitive" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout, expected", [(3.0, "3000ms"), (0.25, "250ms")])
@pytest.mark.parametrize("range_query", [False, True])
async def test_timeout_uses_valid_prometheus_duration(timeout, expected, range_query):
    def response(request):
        assert request.url.params["timeout"] == expected
        return httpx.Response(200, json={"status": "success", "data": {"result": []}})

    async with httpx.AsyncClient(
        base_url="http://prometheus", transport=httpx.MockTransport(response)
    ) as client:
        adapter = PrometheusQueryAdapter(client, enabled=True, timeout=timeout)
        query = MetricQuery(Metric.TARGET_UP)
        if range_query:
            end = datetime.now(UTC)
            await adapter.range(MetricRangeQuery(query, end - timedelta(minutes=5), end))
        else:
            await adapter.instant(query)


@pytest.mark.asyncio
async def test_disabled_monitoring_makes_no_http_calls():
    def response(request):
        raise AssertionError("unexpected request")

    async with httpx.AsyncClient(
        base_url="http://prometheus", transport=httpx.MockTransport(response)
    ) as client:
        assert (
            await PrometheusQueryAdapter(client, enabled=False).instant(MetricQuery(Metric.CPU))
        ).status == "disabled"


def test_uptime_uses_raw_full_window_not_graph_downsampling():
    assert (
        promql(MetricQuery(Metric.PROBE_RATIO, window_seconds=86400))
        == "avg_over_time(probe_success[86400s])"
    )
    assert (
        promql(MetricQuery(Metric.PROBE_SAMPLES, window_seconds=86400))
        == "count_over_time(probe_success[86400s])"
    )
