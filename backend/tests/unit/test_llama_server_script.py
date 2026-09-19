"""llama serve 启动参数的最小回归测试。"""

from scripts.start_llama_servers import _server_command


def test_empty_device_does_not_add_device_argument() -> None:
    command = _server_command("embedding.gguf", "http://127.0.0.1:11434", "--embedding", "", 0)
    assert "--device" not in command


def test_configured_device_is_forwarded() -> None:
    command = _server_command("reranker.gguf", "http://127.0.0.1:11435", "--rerank", "Vulkan1", 4096)
    assert command[-2:] == ["--device", "Vulkan1"]
    assert "--ctx-size" in command and "4096" in command
