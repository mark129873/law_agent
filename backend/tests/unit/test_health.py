"""健康检查端点测试。

为什么做这个测试：BE-001 的验收标准是"项目可以正常启动"，
通过 TestClient 直接调用应用实例，不依赖网络端口即可完成基础验证。
"""

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_endpoint_returns_ok() -> None:
    """健康检查应返回 200 与 status=ok。"""
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
