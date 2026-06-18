import random

_SAMPLE_NAMES = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace",
                 "Henry", "Iris", "Jack", "Kate", "Leo", "Mia", "Noah", "Olivia"]
_SAMPLE_TAGS = ["摄影", "旅行", "探店", "美食", "露营", "装备", "穿搭", "美妆",
                "读书", "运动", "音乐", "电影", "科技", "生活", "萌宠"]
_SAMPLE_TITLES = ["周末露营装备推荐", "探店藏在巷子里的咖啡馆", "夏日护肤好物分享",
                  "城市周边一日游攻略", "新入手的相机测评", "在家也能做的美味甜点"]
_SAMPLE_CONTENTS = ["最近入手的露营装备分享...", "这家店环境很好，推荐给大家",
                    "用了两周后的真实感受，值得入手", "详细攻略，建议收藏"]
_next_id = 1001


def _next_auto_id() -> int:
    global _next_id
    _next_id += 1
    return _next_id


def generate_fake_value(
    prop_name: str,
    schema_type: str = "string",
    *,
    enum: list | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
    fmt: str = "",
) -> object:
    if enum:
        return random.choice(enum)

    name_lower = prop_name.lower()

    # Name-specific overrides take priority over generic type defaults
    if "message" in name_lower:
        return "操作成功"
    if "id" in name_lower:
        return _next_auto_id()
    if "count" in name_lower or "total" in name_lower:
        return random.randint(100, 20000)
    if "price" in name_lower:
        return round(random.uniform(9.9, 999.0), 2)
    if "page" in name_lower:
        return 1
    if "size" in name_lower:
        return 20

    if schema_type in ("integer", "number"):
        lo = int(minimum) if minimum is not None else 0
        hi = int(maximum) if maximum is not None else 99999
        return random.randint(lo, min(hi, 99999))

    if schema_type == "boolean":
        return random.choice([True, False])

    if fmt == "email" or "email" in name_lower:
        return f"user{_next_auto_id()}@example.com"
    if fmt == "uri" or fmt == "url" or "avatar" in name_lower or "cover" in name_lower or "image" in name_lower:
        return f"https://cdn.example.com/{prop_name}/{_next_auto_id()}.jpg"
    if fmt == "date-time" or "time" in name_lower:
        return "2025-06-15 14:30:00"
    if fmt == "date" or "date" in name_lower:
        return "2025-06-15"
    if fmt == "uuid":
        return str(_next_auto_id())
    if "phone" in name_lower:
        return f"138{random.randint(10000000, 99999999)}"
    if "code" in name_lower:
        return "123456"
    if "token" in name_lower:
        return f"eyJ{random.randint(100000, 999999)}.{random.randint(100000, 999999)}"
    if "name" in name_lower or "nickname" in name_lower:
        return random.choice(_SAMPLE_NAMES)
    if "title" in name_lower:
        return random.choice(_SAMPLE_TITLES)
    if "content" in name_lower or "bio" in name_lower or "description" in name_lower:
        return random.choice(_SAMPLE_CONTENTS)
    if "tag" in name_lower:
        return random.sample(_SAMPLE_TAGS, min(3, len(_SAMPLE_TAGS)))
    if "gender" in name_lower:
        return random.choice([0, 1, 2])
    if "visibility" in name_lower:
        return "public"
    if name_lower.startswith("has") or name_lower.startswith("is") or name_lower.startswith("allow") or name_lower.startswith("show"):
        return True

    return f"sample-{prop_name}"
