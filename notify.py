"""推送通知：Bark / Server酱 / 飞书机器人 / 钉钉机器人 / 自定义 webhook。"""
import json
from urllib.parse import quote

import requests

from db import get_db, get_setting_json, now


def _post(url, payload=None, timeout=10):
    r = requests.post(url, data=json.dumps(payload) if payload is not None else None,
                      headers={"Content-Type": "application/json"}, timeout=timeout)
    r.raise_for_status()
    return r.text[:200]


def send_bark(server, title, body):
    # server 形如 https://api.day.app/你的key
    return _post(f"{server.rstrip('/')}/{quote(title)}/{quote(body[:200])}?group=instmon")


def send_serverchan(sckey, title, body):
    # sckey 形如 https://sctapi.ftqq.com/SENDKEY.send
    return _post(sckey, {"title": title[:32], "desp": body})


def send_feishu(url, title, body):
    return _post(url, {"msg_type": "text", "content": {"text": f"{title}\n{body}"}})


def send_dingtalk(url, title, body):
    return _post(url, {"msgtype": "text", "text": {"content": f"{title}\n{body}"}})


def send_custom(url, title, body):
    return _post(url, {"title": title, "body": body, "ts": now()})


CHANNELS = [
    ("bark", "Bark (iOS)", "server", "https://api.day.app/你的Key"),
    ("serverchan", "Server酱", "url", "https://sctapi.ftqq.com/你的KEY.send"),
    ("feishu", "飞书群机器人", "url", "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"),
    ("dingtalk", "钉钉群机器人", "url", "https://oapi.dingtalk.com/robot/send?access_token=xxx"),
    ("custom", "自定义 Webhook", "url", "https://your.server/hook"),
]


def push_alert(title, body):
    """推送到所有已配置渠道，返回 {channel: ok}。"""
    results = {}
    for ch, _, _, _ in CHANNELS:
        cfg = get_setting_json(f"notify_{ch}", "")
        if not cfg:
            continue
        try:
            if ch == "bark":
                send_bark(cfg, title, body)
            elif ch == "serverchan":
                send_serverchan(cfg, title, body)
            elif ch == "feishu":
                send_feishu(cfg, title, body)
            elif ch == "dingtalk":
                send_dingtalk(cfg, title, body)
            else:
                send_custom(cfg, title, body)
            results[ch] = "ok"
        except Exception as e:  # noqa: BLE001
            results[ch] = f"{type(e).__name__}: {str(e)[:80]}"
    return results


def test_channel(ch, cfg):
    try:
        if ch == "bark":
            send_bark(cfg, "机构雷达测试", "这是一条测试推送 ✅")
        elif ch == "serverchan":
            send_serverchan(cfg, "机构雷达测试", "这是一条测试推送 ✅")
        elif ch == "feishu":
            send_feishu(cfg, "机构雷达测试", "这是一条测试推送 ✅")
        elif ch == "dingtalk":
            send_dingtalk(cfg, "机构雷达测试", "这是一条测试推送 ✅")
        else:
            send_custom(cfg, "机构雷达测试", "这是一条测试推送 ✅")
        return True
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {str(e)[:120]}"
