from sentence_transformers import SentenceTransformer, CrossEncoder

reranker = CrossEncoder(
    r"C:\Users\nnnnnn\.cache\huggingface\hub\models--Qwen--Qwen3-Reranker-0.6B\snapshots\e61197ed45024b0ed8a2d74b80b4d909f1255473",
    device="cpu",
)
query = "Transformer 的机制是什么？"

documents = [
    "BERT采用双向预训练，使用masked language model。",
    "Transformer 的核心是自注意力机制，可以建模长距离token之间的依赖关系。",
    "ResNet使用残差连接解决深度网络梯度消失。",
]

scores = reranker.predict(
    [(query, document) for document in documents]
)
print(scores)