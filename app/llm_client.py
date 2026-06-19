import base64
import json
import re

import httpx

from app.config import DASHSCOPE_API_KEY, QWEN_ENDPOINT

_CODE_BLOCK_RE = re.compile(r"```json\s*|```")


class NotAPlantError(Exception):
    """图片中未检测到植物。"""

_RESPONSE_SCHEMA_HINT = """
{
  "identifier": {
    "common_name": "中文常用名，如 白芥",
    "scientific_name": "拉丁学名，如 Sinapis alba",
    "family": "科属，如 十字花科",
    "about": "一段中文简介，包含来源、特征、用途等",
    "tags": ["一年生植物", "原产地：地中海", "经济作物"],
    "edible_parts": ["叶子", "油脂", "种子"],
    "common_aliases": ["白芥", "黄芥子", "White Mustard"]
  },
  "schedule": {
    "soil_type": "排水良好的壤土或沙质土，微碱性为佳",
    "fertilizer": "生长初期施富氮肥料，之后每3-4周轻量追肥",
    "weekly": [
      {"day": "周一", "water_ml": 50, "sunlight_hours": "6-8小时"},
      {"day": "周二", "water_ml": 40, "sunlight_hours": "6-8小时"},
      {"day": "周三", "water_ml": 20, "sunlight_hours": "6-8小时"},
      {"day": "周四", "water_ml": 20, "sunlight_hours": "6-8小时"},
      {"day": "周五", "water_ml": 20, "sunlight_hours": "6-8小时"},
      {"day": "周六", "water_ml": 20, "sunlight_hours": "6-8小时"},
      {"day": "周日", "water_ml": null, "sunlight_hours": "6-8小时"}
    ]
  },
  "diagnosis": {
    "health_status": "diseased",
    "disease_name": "早疫病",
    "pathogen": "Alternaria solani（链格孢菌）",
    "severity": "moderate",
    "confidence": 0.85,
    "symptoms": ["下部叶片出现深褐色圆形斑点，具同心环纹（靶心状）", "病斑周围组织黄化，向叶缘扩展"],
    "treatments": [
      {"title": "杀菌剂试用", "detail": "连续7-10天喷施唑醚代森锌等杀菌剂，症状出现即开始，整季持续用药"},
      {"title": "修剪病叶", "detail": "立即摘除所有可见病叶并妥善处理，勿堆肥——装袋丢弃，防止孢子扩散"}
    ],
    "prevention": ["每季轮作，同一位置连续2年以上不种同类作物", "重新种植时选择抗病品种"]
  }
}
"""


def _build_prompt(label: str, confidence: float) -> str:
    return (
        "你是一名植物学和植物病理学专家。本地分类模型对这张图片做了初步判断，"
        f"预测类别为 '{label}'，置信度为 {confidence * 100:.1f}%。\n\n"
        "请结合图片本身和模型的预测结果，生成一份完整的分析报告，用于在网页上展示。"
        "除下方明确要求使用英文枚举值的字段外，所有展示给用户看的文本内容必须使用简体中文"
        "（拉丁学名、外文别名等专有名词除外）。任何说明性、占位性的内容也必须用中文表达，"
        "禁止出现 \"N/A\"、\"Unknown\"、\"None\"、\"Not applicable\" 等英文占位词——"
        "无法确定时请用中文表述，例如「未知」「无法识别」「不适用」。\n\n"
        "只返回一个 JSON 对象，不要包含 markdown 代码块标记，不要包含星号。"
        "JSON 结构、字段含义与取值规则示例如下（仅说明格式，请根据图片重新生成真实内容，"
        "不要照抄示例数值）：\n"
        f"{_RESPONSE_SCHEMA_HINT}\n\n"
        "字段规则说明：\n"
        "1. identifier：这株植物的通用百科信息（常用名、学名、科属、标签、简介、可食用部位、"
        "别名）。about 字段是植物简介，长度必须控制在 100 字以内。"
        "不要填写 confidence 字段（系统会自动覆盖）。\n"
        "2. schedule：针对这种植物给出周一到周日的个性化养护建议；"
        "water_ml 必须是数字（毫升）或 null（表示当天无需浇水/休息日），不要写成带单位的字符串；"
        "sunlight_hours 用中文描述日照时长。\n"
        "3. diagnosis：\n"
        "   - health_status 必须是英文枚举值，只能是 \"healthy\" 或 \"diseased\"\n"
        "   - severity 必须是英文枚举值 \"low\"/\"moderate\"/\"high\"，植株健康时设为 null\n"
        "   - confidence 是你对本次诊断结论的置信度，取值 0 到 1 之间的小数\n"
        "   - 若植株健康，或没有可识别的病原体：disease_name、pathogen、severity 必须设为 "
        "JSON 的 null（绝不能写成字符串 \"None\" 或 \"无\"），"
        "symptoms/treatments/prevention 可以是空数组\n"
        "   - 若有病害：结合模型预测和图片内容给出中文病名、病原学名、"
        "观察到的症状列表、推荐治疗方案（每项含 title 和 detail，均用中文）、预防建议列表\n"
        "4. 如果图片根本不是植物（如人物、动物、风景、物品等），不要套用上面的结构，"
        "只返回 {\"not_a_plant\": true} 这一个 JSON 对象，不要包含其他任何字段或文字。\n"
    )


def _empty_result() -> dict:
    return {
        "identifier": {
            "common_name": "解析失败",
            "scientific_name": "",
            "family": "",
            "about": "未能解析模型返回的内容，请重试。",
            "tags": [],
            "edible_parts": [],
            "common_aliases": [],
        },
        "schedule": {
            "soil_type": "",
            "fertilizer": "",
            "weekly": [],
        },
        "diagnosis": {
            "health_status": "healthy",
            "disease_name": None,
            "pathogen": None,
            "severity": None,
            "confidence": 0.0,
            "symptoms": [],
            "treatments": [],
            "prevention": [],
        },
    }


_NULL_LIKE = {"none", "null", "无", "n/a", "na", ""}


def _normalize_nullable(diagnosis: dict) -> None:
    for key in ("disease_name", "pathogen", "severity"):
        value = diagnosis.get(key)
        if isinstance(value, str) and value.strip().lower() in _NULL_LIKE:
            diagnosis[key] = None


def _clean_json_text(text: str) -> dict:
    cleaned = _CODE_BLOCK_RE.sub("", text).strip()
    if not cleaned:
        return _empty_result()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return _empty_result()

    if isinstance(data, dict) and data.get("not_a_plant") is True:
        raise NotAPlantError()

    for key in ("identifier", "schedule", "diagnosis"):
        data.setdefault(key, {})

    _normalize_nullable(data["diagnosis"])

    return data


async def diagnose(image_bytes: bytes, mime_type: str, label: str, confidence: float) -> dict:
    if not DASHSCOPE_API_KEY:
        raise RuntimeError("Missing DashScope API key")

    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    image_data_url = f"data:{mime_type};base64,{image_b64}"

    payload = {
        "model": "qwen-vl-plus",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                    {"type": "text", "text": _build_prompt(label, confidence)},
                ],
            }
        ],
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        try:
            response = await client.post(QWEN_ENDPOINT, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise TimeoutError("Qwen API request timed out")
        except httpx.RequestError as exc:
            raise RuntimeError(f"Qwen API request failed: {exc}")

    if response.status_code != 200:
        raise RuntimeError(
            f"Qwen API Error: {response.status_code} {response.text}"
        )

    data = response.json()
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        text = ""

    return _clean_json_text(text)
