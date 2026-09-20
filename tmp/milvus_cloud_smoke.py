"""只读验证云端 Milvus 连接，不创建、修改或删除任何数据。"""

import os
import sys

from pymilvus import MilvusClient


def main() -> None:
    uri = os.environ.get("MILVUS_CLOUD_URI")
    token = os.environ.get("MILVUS_CLOUD_TOKEN")
    if not uri or not token:
        raise SystemExit("Set MILVUS_CLOUD_URI and MILVUS_CLOUD_TOKEN first.")

    try:
        client = MilvusClient(uri=uri, token=token, timeout=10)
        version = client.get_server_version()
        print(f"Milvus cloud connection PASS: version={version}")
    except Exception as exc:
        # 错误信息中也不输出 Token，避免凭据进入终端日志。
        message = str(exc).replace(token, "***")
        print(f"Milvus cloud connection FAILED: {type(exc).__name__}: {message}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
