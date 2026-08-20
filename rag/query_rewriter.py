"""Query Rewriting —— 多轮对话查询改写

多轮对话中，用户的最新问题常包含代词（"它"、"这个政策"）或省略上下文
（如追问"那学分要求呢？"）。直接检索会导致召回失败。

本模块使用 LLM 将最新问题改写为自包含的独立查询，提升 BM25 / Dense 检索召回。
LLM 不可用时自动回退原始查询，不影响主流程。
"""
from typing import List, Optional, Dict, Any

from utils.config_loader import get


REWRITE_SYSTEM_PROMPT = """你是校园问答系统的查询改写专家。

任务：根据对话历史，把用户的最新问题改写成一个独立、完整、自包含的检索查询。

规则：
1. 消解代词：把"它"、"这个"、"该政策"等替换为对话历史中对应的具体实体
2. 补全省略：如果最新问题省略了主语或背景（如"那学分呢？"），需结合上文补全
3. 保持原意：不得添加对话历史中没有的信息，不得改变用户意图
4. 保持简洁：改写后仍是一个自然语言问题，不超过 50 字
5. 无需改写时原样输出最新问题

输出格式：只输出改写后的问题本身，不要任何解释、引号或前缀。"""


class QueryRewriter:
    """多轮对话查询改写器

    用法:
        rewriter = QueryRewriter()
        result = rewriter.rewrite(
            query="那它的学分要求呢？",
            chat_history=[
                {"role": "human", "content": "保研需要什么条件？"},
                {"role": "ai", "content": "保研需要绩点前 20%……"},
            ],
        )
        # result["rewritten"] == "保研的学分要求是什么？"
    """

    def __init__(self):
        self._enabled = bool(get("features.query_rewriting", True))
        self._history_rounds = int(get("rag.query_rewrite_history_rounds", 4))

    @property
    def enabled(self) -> bool:
        return self._enabled

    def rewrite(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        """改写用户查询

        Args:
            query: 用户最新问题
            chat_history: 对话历史列表，每项 {"role": "human"|"ai", "content": str}
            user_id: 用户标识（用于限速）

        Returns:
            {
                "original": str,     # 原始查询
                "rewritten": str,    # 改写后查询（失败时等于 original）
                "changed": bool,     # 是否发生了改写
                "source": str,       # "llm" | "passthrough" | "fallback"
            }
        """
        query = (query or "").strip()
        history = self._trim_history(chat_history)

        if not query:
            return self._passthrough(query, "empty query")

        # 无对话历史时无需改写
        if not self._enabled or not history:
            return self._passthrough(query, "no history or disabled")

        try:
            from utils import get_llm_client

            llm = get_llm_client()
            user_message = self._build_user_message(query, history)
            rewritten = llm.call(
                system_prompt=REWRITE_SYSTEM_PROMPT,
                user_message=user_message,
                user_id=user_id,
            )
            rewritten = self._sanitize(rewritten)

            if not rewritten or len(rewritten) > len(query) * 3:
                # LLM 输出异常（为空 / 失控膨胀），回退原始查询
                return self._passthrough(query, "llm output invalid")

            return {
                "original": query,
                "rewritten": rewritten,
                "changed": rewritten != query,
                "source": "llm",
            }
        except Exception:
            # LLM 不可用时回退，不影响主流程
            return self._passthrough(query, "llm unavailable")

    # ── internal ───────────────────────────────────────────────────────

    def _trim_history(
        self, chat_history: Optional[List[Dict[str, str]]]
    ) -> List[Dict[str, str]]:
        """只保留最近 N 轮对话，避免上下文过长"""
        if not chat_history:
            return []
        rounds = self._history_rounds
        return [
            h for h in chat_history[-(rounds * 2):]
            if (h.get("content") or "").strip()
        ]

    @staticmethod
    def _build_user_message(
        query: str, history: List[Dict[str, str]]
    ) -> str:
        lines = ["对话历史："]
        for h in history:
            role = "用户" if h.get("role") == "human" else "助手"
            lines.append(f"{role}: {h.get('content', '')}")
        lines.append("")
        lines.append(f"用户最新问题：{query}")
        lines.append("")
        lines.append("请输出改写后的独立问题：")
        return "\n".join(lines)

    @staticmethod
    def _sanitize(text: str) -> str:
        """清洗 LLM 输出：去引号、前缀、换行"""
        if not text:
            return ""
        t = text.strip().strip('"').strip("'").strip("`").strip()
        # 去除常见的输出前缀
        for prefix in ("改写后:", "改写后：", "改写结果:", "改写结果："):
            if t.startswith(prefix):
                t = t[len(prefix):].strip()
        return t.split("\n")[0].strip()

    @staticmethod
    def _passthrough(query: str, note: str) -> Dict[str, Any]:
        return {
            "original": query,
            "rewritten": query,
            "changed": False,
            "source": "passthrough",
            "note": note,
        }


def history_from_messages(messages: List[Any], rounds: Optional[int] = None) -> List[Dict[str, str]]:
    """从 LangGraph BaseMessage 列表构建改写器可用的对话历史

    排除最新一条 human 消息（它就是待改写的 query），
    只保留 human / ai 消息。
    """
    max_rounds = rounds or int(get("rag.query_rewrite_history_rounds", 4))
    history: List[Dict[str, str]] = []
    for msg in messages:
        role = getattr(msg, "type", "")
        if role not in ("human", "ai"):
            continue
        content = getattr(msg, "content", "") or ""
        if not content.strip():
            continue
        history.append({"role": role, "content": content})

    # 去掉最后一条（即当前待处理的 query 本身，由调用方单独传入）
    if history and history[-1]["role"] == "human":
        history = history[:-1]

    return history[-(max_rounds * 2):]


# ── demo ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    rewriter = QueryRewriter()

    # 场景 1：含代词的多轮追问
    history = [
        {"role": "human", "content": "保研需要什么条件？"},
        {"role": "ai", "content": "保研需要绩点排名前 20%，且无挂科记录。"},
    ]
    r1 = rewriter.rewrite("那它的学分要求呢？", history)
    print("场景1:", r1)

    # 场景 2：无历史 → 直接透传
    r2 = rewriter.rewrite("图书馆几点开门？")
    print("场景2:", r2)
