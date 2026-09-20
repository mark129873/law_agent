"""按 backend/.env 启动 Embedding 与 Reranker 两个 llama serve 进程。

两个模型用途不同，必须使用两个独立端口：Embedding 进程启用
``--embedding``，Reranker 进程启用 ``--rerank``。设备参数是部署开关，
只有 ``LLAMA_DEVICE`` 非空时才追加 ``--device``，避免把空配置变成
llama serve 的非法参数。
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_ROOT))

from app.config.settings import Settings


def _server_command(
    model_path: str,
    base_url: str,
    mode: str,
    device: str,
    context_size: int = 0,
) -> list[str]:
    """把配置转换成不会经过 shell 的 llama serve 参数列表。"""
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or not parsed.port:
        raise ValueError(f"llama serve 地址必须包含 http(s)://主机:端口：{base_url}")
    if not model_path.strip():
        raise ValueError("必须配置模型路径")
    if context_size < 0:
        raise ValueError("llama serve 上下文长度不能小于 0")
    command = [
        "llama",
        "serve",
        "--model",
        model_path,
        mode,
        "--host",
        parsed.hostname,
        "--port",
        str(parsed.port),
        "--no-ui",
    ]
    if context_size:
        command.extend(["--ctx-size", str(context_size)])
    if device.strip():
        command.extend(["--device", device.strip()])
    return command


def _validate_model_path(model_path: str, label: str) -> None:
    """启动前检查路径，避免两个服务都在后台失败后才发现配置错误。"""
    path = Path(model_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"{label} 模型文件不存在：{path}")


def main() -> int:
    settings = Settings()
    _validate_model_path(settings.embedding_model_path, "Embedding")
    _validate_model_path(settings.reranker_model_path, "Reranker")
    commands = [
        _server_command(
            settings.embedding_model_path,
            settings.embedding_base_url,
            "--embedding",
            settings.llama_device,
            settings.llama_context_size,
        ),
        _server_command(
            settings.reranker_model_path,
            settings.reranker_base_url,
            "--rerank",
            settings.llama_device,
            settings.llama_context_size,
        ),
    ]
    processes: list[subprocess.Popen[bytes]] = []
    try:
        for command in commands:
            print("启动：", subprocess.list2cmdline(command), flush=True)
            processes.append(subprocess.Popen(command, cwd=_BACKEND_ROOT))
        while True:
            exited = [process.returncode for process in processes if process.poll() is not None]
            if exited:
                raise RuntimeError(f"llama serve 进程提前退出：returncode={exited}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("正在停止 llama serve 进程…", flush=True)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            if process.poll() is None:
                process.wait(timeout=10)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        raise SystemExit(f"启动 llama serve 失败：{error}") from error
