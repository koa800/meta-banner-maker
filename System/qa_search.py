"""
Q&A検索モジュール - Pinecone連携
過去の質問回答データをベクトル検索で類似検索
"""

import logging
import os
import json
from typing import Optional
from openai import OpenAI
from pinecone import Pinecone

logger = logging.getLogger("qa_search")

# 環境変数から設定
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
PINECONE_INDEX_NAME = "qa-index"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536


class QASearch:
    """Q&A検索クラス"""
    
    def __init__(self, pinecone_api_key: str = None, openai_api_key: str = None):
        self.pinecone_api_key = pinecone_api_key or PINECONE_API_KEY
        self.openai_api_key = openai_api_key or OPENAI_API_KEY
        
        self.pc = None
        self.index = None
        self.openai_client = None
        
        if self.pinecone_api_key:
            self.pc = Pinecone(api_key=self.pinecone_api_key)
            self.index = self.pc.Index(PINECONE_INDEX_NAME)
        
        if self.openai_api_key:
            self.openai_client = OpenAI(api_key=self.openai_api_key)
    
    def get_embedding(self, text: str) -> list[float]:
        """テキストをベクトルに変換"""
        if not self.openai_client:
            raise ValueError("OpenAI APIキーが設定されていません")
        
        response = self.openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding
    
    def upsert_qa(self, qa_id: str, question: str, answer: str, metadata: dict = None):
        """Q&Aデータをインデックスに追加/更新"""
        if not self.index:
            raise ValueError("Pineconeが初期化されていません")
        
        # 質問文をベクトル化
        embedding = self.get_embedding(question)
        
        # メタデータを構築
        meta = {
            "question": question,
            "answer": answer,
            "created_at": metadata.get("created_at", "") if metadata else "",
            "user_name": metadata.get("user_name", "") if metadata else "",
            "source": metadata.get("source", "spreadsheet") if metadata else "spreadsheet",
        }
        if metadata:
            meta.update({k: v for k, v in metadata.items() if k not in meta})
        
        # Pineconeにアップサート
        self.index.upsert(
            vectors=[{
                "id": qa_id,
                "values": embedding,
                "metadata": meta
            }]
        )
        
        return True
    
    def search_similar(self, question: str, top_k: int = 5, score_threshold: float = 0.7) -> list[dict]:
        """類似質問を検索"""
        if not self.index:
            raise ValueError("Pineconeが初期化されていません")
        
        # 質問文をベクトル化
        embedding = self.get_embedding(question)
        
        # 類似検索
        results = self.index.query(
            vector=embedding,
            top_k=top_k,
            include_metadata=True
        )
        
        # スコア閾値でフィルタリング
        similar_qa = []
        for match in results.matches:
            if match.score >= score_threshold:
                similar_qa.append({
                    "id": match.id,
                    "score": match.score,
                    "question": match.metadata.get("question", ""),
                    "answer": match.metadata.get("answer", ""),
                    "user_name": match.metadata.get("user_name", ""),
                    "created_at": match.metadata.get("created_at", ""),
                })
        
        return similar_qa
    
    def delete_qa(self, qa_id: str):
        """Q&Aデータを削除"""
        if not self.index:
            raise ValueError("Pineconeが初期化されていません")
        
        self.index.delete(ids=[qa_id])
        return True
    
    def get_stats(self) -> dict:
        """インデックスの統計情報を取得"""
        if not self.index:
            raise ValueError("Pineconeが初期化されていません")
        
        stats = self.index.describe_index_stats()
        return {
            "total_vectors": stats.total_vector_count,
            "dimension": stats.dimension,
        }


def generate_answer_with_context(
    question: str,
    similar_qa: list[dict],
    openai_api_key: str = None
) -> str:
    """類似Q&Aを参考にして回答を生成"""
    api_key = openai_api_key or OPENAI_API_KEY
    if not api_key:
        raise ValueError("OpenAI APIキーが設定されていません")
    
    client = OpenAI(api_key=api_key)
    
    # 類似Q&Aをコンテキストとして構築
    context_parts = []
    for i, qa in enumerate(similar_qa[:3], 1):
        context_parts.append(f"""
【参考{i}】（類似度: {qa['score']:.2f}）
質問: {qa['question']}
回答: {qa['answer']}
""")
    
    context = "\n".join(context_parts) if context_parts else "（類似の過去質問はありません）"
    
    system_prompt = """あなたはマーケティング講座の受講生サポートを行うAIアシスタントです。
受講生からの質問に対して、丁寧かつ的確に回答してください。

【回答のルール】
- 簡潔で分かりやすい日本語で回答する
- 専門用語は必要に応じて補足説明を加える
- 過去の類似質問への回答を参考にしつつ、現在の質問に適した回答を作成する
- 不明な点がある場合は、その旨を正直に伝える
- 回答は500文字以内を目安にする
"""

    user_prompt = f"""【今回の質問】
{question}

【過去の類似質問と回答】
{context}

上記を参考に、今回の質問に対する最適な回答を作成してください。"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=800,
        temperature=0.7
    )
    
    return response.choices[0].message.content


# CLI用
if __name__ == "__main__":
    import sys
    
    qa_search = QASearch()
    
    if len(sys.argv) < 2:
        print("""
使い方:
  python qa_search.py stats           # 統計情報を表示
  python qa_search.py search "質問"   # 類似質問を検索
  python qa_search.py answer "質問"   # AI回答を生成
""")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "stats":
        stats = qa_search.get_stats()
        print(f"登録済みQ&A数: {stats['total_vectors']}")
        print(f"ベクトル次元数: {stats['dimension']}")
    
    elif cmd == "search" and len(sys.argv) > 2:
        question = sys.argv[2]
        results = qa_search.search_similar(question)
        
        if results:
            print(f"\n「{question}」の類似質問:\n")
            for i, qa in enumerate(results, 1):
                print(f"[{i}] 類似度: {qa['score']:.2f}")
                print(f"    質問: {qa['question'][:50]}...")
                print(f"    回答: {qa['answer'][:50]}...")
                print()
        else:
            print("類似質問が見つかりませんでした")
    
    elif cmd == "answer" and len(sys.argv) > 2:
        question = sys.argv[2]
        similar = qa_search.search_similar(question)
        answer = generate_answer_with_context(question, similar)
        
        print(f"\n【質問】\n{question}\n")
        print(f"【AI回答】\n{answer}")
