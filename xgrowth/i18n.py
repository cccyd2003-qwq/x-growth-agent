"""Tiny language system for user-facing strings (Telegram + CLI prompts).

Default language is English. Users pick `en` or `zh` at setup time
(stored in config as `language`). Add a language by adding a dict to STRINGS.
"""

from __future__ import annotations

DEFAULT_LANG = "en"

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # reply detail card
        "revise_note": "↪️ <i>Rewritten per your note “{note}”:</i>",
        "reply_hint": "💬 <i>Reply to this message to revise (e.g. punchier / shorter / make it a meme)</i>",
        "btn_copy": "📋 Copy {n}",
        "btn_original": "🔗 Original",
        "btn_delete_topic": "🗑 Delete topic",
        # digest / index
        "digest_header": "🗂 <b>{n} new post(s) this round</b> · {time}",
        "digest_tap": "\n\n👇 Tap one to see the full post + reply ideas",
        "index_tap": "\n\n👇 Tap one → a topic is created with replies just for it",
        # listener replies
        "topic_created": "✅ Topic created: {link}",
        "topic_exists": "↑ This one already has a topic: {link}",
        "cb_generating": "Generating replies…",
        "cb_topic_exists": "A topic already exists for this one",
        "cb_deleted": "Topic deleted",
        "no_target": "Open a post first (or reply inside its topic), then tell me how to revise.",
        "cycle_capped": "⚠️ Many new posts this round; handled the latest {n}, skipped {dropped} older ones.",
        # time-ago
        "just_now": "just now",
        "minutes_ago": "{n}m ago",
        "hours_ago": "{n}h ago",
        "days_ago": "{n}d ago",
    },
    "zh": {
        "revise_note": "↪️ <i>按你说的「{note}」重写：</i>",
        "reply_hint": "💬 <i>直接回复本条消息可让我改（例：更毒一点 / 更短 / 换个梗）</i>",
        "btn_copy": "📋 复制{n}",
        "btn_original": "🔗 看原帖",
        "btn_delete_topic": "🗑 删除话题",
        "digest_header": "🗂 <b>本轮 {n} 条新帖</b> · {time}",
        "digest_tap": "\n\n👇 点按钮看全文 + 回复建议",
        "index_tap": "\n\n👇 点一条 → 才为它建话题并写回复",
        "topic_created": "✅ 已建话题：{link}",
        "topic_exists": "↑ 这条已有话题：{link}",
        "cb_generating": "正在生成回复…",
        "cb_topic_exists": "已为这条建过话题",
        "cb_deleted": "已删除话题",
        "no_target": "先点开一条帖子（或在它的话题里）再告诉我怎么改～",
        "cycle_capped": "⚠️ 本轮新帖较多，已处理最新 {n} 条，跳过 {dropped} 条较旧的。",
        "just_now": "刚刚",
        "minutes_ago": "{n} 分钟前",
        "hours_ago": "{n} 小时前",
        "days_ago": "{n} 天前",
    },
}


def normalize_lang(lang: str | None) -> str:
    if not lang:
        return DEFAULT_LANG
    lang = lang.strip().lower()
    if lang in ("zh", "cn", "zh-cn", "zh_hans", "chinese", "中文"):
        return "zh"
    if lang in ("en", "en-us", "english"):
        return "en"
    return DEFAULT_LANG


def t(lang: str, key: str, **kwargs) -> str:
    """Look up a string for `lang`, formatting with kwargs. Falls back to English."""
    lang = normalize_lang(lang)
    table = STRINGS.get(lang) or STRINGS[DEFAULT_LANG]
    s = table.get(key) or STRINGS[DEFAULT_LANG].get(key) or key
    try:
        return s.format(**kwargs) if kwargs else s
    except Exception:
        return s
