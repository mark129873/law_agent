"""BE-012/021 真实数据端到端验证脚本（临时使用）。

针对 tests/data_source 中的真实法律文档：
上传（txt + md）→ 入库 ready → RAG 问答命中专利法内容。
"""
import asyncio
import os

os.chdir(r"C:\Users\nnnnnn\Desktop\law_agent\backend")

import httpx

BASE = "http://127.0.0.1:8000"


async def main() -> None:
    data_source = os.path.join("tests", "data_source")
    async with httpx.AsyncClient(timeout=300) as client:
        # 1. 上传真实专利法 TXT
        txt = open(os.path.join(data_source, "中华人民共和国专利法.txt"), "rb").read()
        resp = await client.post(
            f"{BASE}/api/documents",
            files={"file": ("中华人民共和国专利法.txt", txt, "text/plain")},
        )
        print("upload txt:", resp.status_code, resp.json().get("status"), "chunks_ready" if resp.status_code == 201 else resp.text[:200])

        # 2. 上传 md 测试文件
        md = open(os.path.join(data_source, "中华人民共和国专利法（要点笔记）.md"), "rb").read()
        resp = await client.post(
            f"{BASE}/api/documents",
            files={"file": ("中华人民共和国专利法（要点笔记）.md", md, "text/markdown")},
        )
        print("upload md:", resp.status_code, resp.json().get("status") if resp.status_code == 201 else resp.text[:200])

        # 3. 新建会话并流式提问（真实 Ollama RAG）
        conversation_id = (await client.post(f"{BASE}/api/conversations", json={"title": "专利法咨询"})).json()["id"]
        answer = []
        sources = []
        async with client.stream(
            "POST",
            f"{BASE}/api/chat/stream",
            json={"conversation_id": conversation_id, "question": "发明专利权的保护期限是多少年？依据是什么？"},
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    event = __import__("json").loads(line[6:])
                    if event["type"] == "delta":
                        answer.append(event["content"])
                    elif event["type"] == "sources":
                        sources = event["sources"]
                    elif event["type"] == "error":
                        print("STREAM ERROR:", event["message"])
        full = "".join(answer)
        print("=== RAG ANSWER ===")
        print(full[:400])
        print("=== SOURCES ===", __import__("json").dumps(sources, ensure_ascii=False)[:300])
        assert "20" in full or "二十" in full, "回答应包含 20 年保护期限"
        assert "专利法" in full, "回答应引用专利法来源"
        # sources 事件（BE-023）：RAG 检索有命中时必须先于 delta 推送参考来源
        assert sources, "RAG 检索有命中时应推送 sources 事件"
        assert all("source" in s and "content" in s for s in sources), "sources 每项应含 source/content"

        # 4. 消息已持久化，且 assistant 消息携带参考来源（刷新后前端仍可展示）
        messages = (await client.get(f"{BASE}/api/conversations/{conversation_id}/messages")).json()
        print("persisted messages:", [m["role"] for m in messages])
        assert messages[1]["sources"], "持久化的 assistant 消息应带 sources"
        assert messages[1]["sources"] == sources, "持久化来源应与流内 sources 一致"


asyncio.run(main())
