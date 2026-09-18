"""最小 Milvus Lite 验证：本地文件建库、插入和向量检索。"""

from pathlib import Path
from tempfile import TemporaryDirectory

from pymilvus import MilvusClient
from pymilvus.exceptions import ConnectionConfigException


def main() -> None:
    with TemporaryDirectory(prefix="milvus-lite-") as folder:
        db_path = Path(folder) / "smoke.db"
        try:
            client = MilvusClient(uri=str(db_path))
        except (ConnectionConfigException, ModuleNotFoundError) as exc:
            if "milvus-lite" in str(exc) or getattr(exc, "name", "") == "milvus_lite":
                raise SystemExit(
                    "Milvus Lite unavailable; install "
                    "pymilvus[milvus-lite] on Ubuntu/macOS and retry."
                ) from exc
            raise

        collection = "smoke"
        client.create_collection(collection_name=collection, dimension=3)
        client.insert(
            collection_name=collection,
            data=[
                {"id": 1, "vector": [1.0, 0.0, 0.0], "text": "milvus lite"},
                {"id": 2, "vector": [0.0, 1.0, 0.0], "text": "standalone"},
            ],
        )
        hits = client.search(
            collection_name=collection,
            data=[[1.0, 0.0, 0.0]],
            limit=1,
            output_fields=["text"],
        )[0]
        assert hits and hits[0]["id"] == 1, hits
        print(f"Milvus Lite PASS: {db_path}")


if __name__ == "__main__":
    main()
