"""Agent 服务层（BE-033 填充）。

外部依赖统一封装（设计强制约束 23）：LLM/Milvus/Reranker/Citation
服务在此适配领域端口，业务节点禁止直连底层 SDK（约束 24/25）。
"""
