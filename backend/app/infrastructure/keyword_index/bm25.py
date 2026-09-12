"""BM25 关键词索引实现（BE-028 混合检索）。

技术选型与设计说明：
- jieba 做中文分词（法律文本无空格分隔，必须分词后才能做词面匹配），
  rank_bm25 的 BM25Okapi 做词面打分；两者都是纯 Python 库，无重型依赖。
- 语料快照持久化为单个 JSON 文件（临时文件 + os.replace 原子替换）：
  当前知识库规模（万级字符、数百 chunk）下全量重建 BM25 的代价可忽略，
  引入 SQLite 表或增量索引结构属于过度设计；快照与 Chroma 数据同在
  backend/data/ 下，干净环境重置时一并清除。
- BM25Okapi 不支持增量追加，每次增删后全量重建索引对象；
  这换来了"索引状态永远与语料记录一致"的简单不变量。

并发模型：所有阻塞操作（分词、建索引、读盘）经 asyncio.to_thread
包装，与 ChromaVectorStore 同一模式；用 threading.Lock 保护内存
状态，防止并发检索与写入交错破坏"BM25 对象 ↔ 语料记录"的对齐关系。

DDD 说明：本类实现 domain/repositories/keyword_index.py 的 KeywordIndex
端口，jieba/rank_bm25 等技术依赖被隔离在 infrastructure 层
（tests/unit/test_ddd_boundaries.py 以 AST 扫描强制执行）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import uuid
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi

from app.domain.entities.chunk import DocumentChunk, RetrievedChunk
from app.domain.repositories.keyword_index import KeywordIndex

logger = logging.getLogger("app.keyword_index.bm25")

# 快照格式版本：未来字段变更时可据此做迁移判断
_SNAPSHOT_VERSION = 1


def _tokenize(text: str) -> list[str]:
    """中文分词：小写归一后按 jieba 切词，丢弃空白 token。

    为什么在切词前统一小写：法律文本中的英文缩写/术语
    （如 WTO、TCP）大小写形式应视为同一词。
    """
    return [token for token in jieba.lcut(text.lower()) if token.strip()]


class Bm25KeywordIndex(KeywordIndex):
    """基于 jieba + rank_bm25 的进程内关键词索引。

    为什么语料记录（_chunks）与 BM25 索引对象（_bm25）分开保存：
    BM25 索引只存 token 化的词袋与打分模型，检索结果需要还原出
    完整 DocumentChunk（内容、来源 metadata）才能向上层返回；
    两者的对齐关系由同一把锁保护、每次变更后成对重建。
    """

    def __init__(self, persist_path: str) -> None:
        self._persist_path = Path(persist_path)
        # chunk_id -> 完整 chunk 记录（检索结果从这还原）
        self._chunks: dict[str, DocumentChunk] = {}
        # chunk_id -> 分词结果（重建 BM25 时按 id 顺序取用）
        self._tokens: dict[str, list[str]] = {}
        # BM25 打分模型；语料为空时为 None（search 直接返回空）
        self._bm25: BM25Okapi | None = None
        # 与 BM25 语料顺序对齐的 chunk_id 列表（get_scores 的行序）
        self._order: list[str] = []
        # 保护内存状态与写盘的互斥锁（to_thread 线程池并发访问）
        self._lock = threading.Lock()

    # ---- 生命周期 ----

    async def initialize(self) -> None:
        """加载语料快照并重建 BM25 索引（幂等：重复调用结果一致）。"""
        await asyncio.to_thread(self._load_snapshot)
        count = len(self._chunks)
        logger.info(
            "Keyword index initialized",
            extra={"service": "keyword_index", "chunk_count": count, "persist_path": str(self._persist_path)},
        )

    async def close(self) -> None:
        """进程内索引无需显式释放；置空模型引用帮助 GC。"""
        with self._lock:
            self._bm25 = None

    # ---- 写入与删除 ----

    async def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        """把 chunk 追加进语料并全量重建 BM25，随后原子写快照。"""
        total = await asyncio.to_thread(self._add_locked, chunks)
        logger.info(
            "Keyword index chunks added",
            extra={"service": "keyword_index", "added": len(chunks), "total_chunks": total},
        )

    def _add_locked(self, chunks: list[DocumentChunk]) -> int:
        with self._lock:
            for chunk in chunks:
                # 与 ChromaVectorStore 同一策略：无 id 时补生成 uuid，
                # 保证检索去重与按文档删除都有稳定主键
                chunk.chunk_id = chunk.chunk_id or uuid.uuid4().hex
                self._chunks[chunk.chunk_id] = chunk
                self._tokens[chunk.chunk_id] = _tokenize(chunk.content)
            self._rebuild_locked()
            self._save_snapshot_locked()
            return len(self._chunks)

    async def delete_by_document(self, document_id: str) -> int:
        """删除某文档的全部 chunk 并重建索引，返回删除数量。"""
        removed = await asyncio.to_thread(self._delete_locked, document_id)
        if removed:
            logger.info(
                "Keyword index chunks deleted",
                extra={"service": "keyword_index", "document_id": document_id, "removed": removed},
            )
        return removed

    def _delete_locked(self, document_id: str) -> int:
        with self._lock:
            doomed = [cid for cid, chunk in self._chunks.items() if chunk.document_id == document_id]
            for cid in doomed:
                del self._chunks[cid]
                del self._tokens[cid]
            self._rebuild_locked()
            self._save_snapshot_locked()
            return len(doomed)

    def _rebuild_locked(self) -> None:
        """按当前语料全量重建 BM25 模型（调用方必须已持锁）。

        为什么全量重建：BM25Okapi 的 IDF 在构造时一次性计算，
        不支持增量追加；全量重建让"打分模型与语料一致"成为
        结构保证而非需要小心维护的增量逻辑。
        """
        self._order = list(self._tokens.keys())
        corpus = [self._tokens[cid] for cid in self._order]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    # ---- 检索 ----

    async def search(self, query: str, top_k: int = 4) -> list[RetrievedChunk]:
        """BM25 词面打分检索，score 越大越相关（词面不相交的 chunk 被排除）。"""
        return await asyncio.to_thread(self._search_locked, query, top_k)

    def _search_locked(self, query: str, top_k: int) -> list[RetrievedChunk]:
        with self._lock:
            if self._bm25 is None:
                return []
            query_tokens = _tokenize(query)
            if not query_tokens:
                return []
            scores = self._bm25.get_scores(query_tokens)
            query_set = set(query_tokens)
            candidates: list[tuple[float, int, str]] = []
            for cid, score in zip(self._order, scores):
                doc_token_set = set(self._tokens[cid])
                overlap = len(query_set & doc_token_set)
                if overlap == 0:
                    # 词面完全不相交：非有效命中，直接排除
                    # （否则空知识库/无关查询场景会返回无意义结果）
                    continue
                candidates.append((float(score), overlap, cid))
            # 排序：BM25 分数优先；小语料下 IDF 可能归零（全部 0 分），
            # 此时按"命中的不同查询词数量"兜底排序，再按写入顺序稳定排列
            candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
            return [
                RetrievedChunk(chunk=self._chunks[cid], score=score)
                for score, _, cid in candidates[: max(1, top_k)]
            ]

    # ---- 快照持久化 ----

    def _load_snapshot(self) -> None:
        """从磁盘加载语料快照；文件不存在视为空索引（首次启动）。"""
        if not self._persist_path.exists():
            return
        with self._lock:
            raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
            for record in raw.get("chunks", []):
                chunk = DocumentChunk(
                    chunk_id=record["chunk_id"],
                    document_id=record["document_id"],
                    content=record["content"],
                    chunk_index=record["chunk_index"],
                    metadata=record.get("metadata", {}),
                )
                self._chunks[chunk.chunk_id] = chunk
                # 重新分词而不是把 token 存进快照：分词算法升级后
                # 旧快照自动按新分词重建，避免快照里存两份内容
                self._tokens[chunk.chunk_id] = _tokenize(chunk.content)
            self._rebuild_locked()

    def _save_snapshot_locked(self) -> None:
        """原子写快照（临时文件 + os.replace）；失败降级为日志告警。

        为什么失败不上抛：调用此刻向量库已经写入成功，若因快照
        写盘失败把整个文档标记为 failed，会造成"向量可检索但
        元数据 failed"的更糟的不一致；内存索引仍然可用，重启后
        由下次成功的写入补齐快照（与日志降级策略同一取舍）。
        """
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot = {
                "version": _SNAPSHOT_VERSION,
                "chunks": [
                    {
                        "chunk_id": chunk.chunk_id,
                        "document_id": chunk.document_id,
                        "content": chunk.content,
                        "chunk_index": chunk.chunk_index,
                        "metadata": chunk.metadata,
                    }
                    for chunk in self._chunks.values()
                ],
            }
            tmp_path = self._persist_path.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp_path, self._persist_path)
        except OSError as error:
            logger.warning(
                "Keyword index snapshot write failed",
                extra={"service": "keyword_index", "error": str(error)},
            )
