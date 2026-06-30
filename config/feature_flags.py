"""特征开关 – 运行时可通过 API 或管理界面修改"""
class FeatureFlags:
    _flags = {
        "campus_qa": True,           # 校园十万个为什么
        "dual_validation": True,     # 双路交叉验证
        "node2vec": True,            # Node2Vec 链路预测
        "ppr_recommend": True,       # PPR 推荐
        "semantic_cache": True,      # 语义缓存
        "offline_mode": False,       # 离线模式（关闭所有LLM）
        "strict_privacy": False,     # 严格隐私模式
    }

    @classmethod
    def is_enabled(cls, flag: str) -> bool:
        return cls._flags.get(flag, False)

    @classmethod
    def set_flag(cls, flag: str, value: bool) -> None:
        if flag in cls._flags:
            cls._flags[flag] = value

    @classmethod
    def get_all(cls) -> dict:
        return cls._flags.copy()