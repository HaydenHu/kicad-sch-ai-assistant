"""
Multi-language support. Auto-detects system language, falls back to English.
"""

import locale
import os


def _detect_lang():
    """Detect UI language: zh for Chinese, en for others."""
    # 1. Check environment
    for env in ["LANG", "LC_ALL", "LANGUAGE", "KICAD_LANG"]:
        v = os.environ.get(env, "")
        if v and "zh" in v.lower():
            return "zh"
    # 2. Windows: try GetUserDefaultUILanguage
    try:
        import ctypes
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        # Primary language ID: 0x04 = Chinese
        if (lang_id & 0xFF) == 0x04:
            return "zh"
    except Exception:
        pass
    # 3. locale fallback
    try:
        lc = locale.getdefaultlocale()
        if lc and lc[0] and "zh" in lc[0].lower():
            return "zh"
    except Exception:
        pass
    # 4. Check for common Chinese code pages
    try:
        import ctypes
        acp = ctypes.windll.kernel32.GetACP()
        if acp in (936, 54936, 950):  # GBK, GB18030, Big5
            return "zh"
    except Exception:
        pass
    return "en"


LANG = _detect_lang()

STRINGS = {
    "zh": {
        "title": "AI 引脚助手",

        "paste": "粘贴",
        "file": "文件",
        "symbol_recog": "识别符号",
        "send": "发送",

        "copy_editor": "复制到符号编辑器",
        "save_sym": "保存 .kicad_sym",
        "export_json": "导出 JSON",
        "settings_btn": "设置",

        "settings_title": "设置",
        "api_key": "API Key",
        "model": "模型",
         "endpoint": "接入点",
        "save_key": "保存 Key",
        "free_key": "免费获取",
        "symbol_name": "符号名称",
        "ref_prefix": "参考前缀",
        "pin_length": "引脚长度 (mm)",
        "pin_spacing": "引脚间距 (mm)",
        "show_numbers": "显示引脚编号",
        "show_names": "显示引脚名称",

        "welcome": "欢迎！粘贴或拖入数据手册引脚图，点击识别符号提取引脚。",
        "thinking": "思考中...",
        "analyzing": "正在分析图片...",

        "image_pasted": "已粘贴图片，点击识别符号开始分析。",
        "image_loaded": "已加载图片: {name}，点击识别符号。",

        "no_image": "未加载图片。请先粘贴或打开一张引脚图。",
        "no_api_key": "API Key 未设置。请打开设置输入密钥。",
        "no_pins": "未检测到引脚。尝试更清晰的图片或检查 API Key。",
        "analysis_failed": "分析失败:\n{error}",
        "success_pins": "成功提取 {n} 个引脚。\n{s}",

        "no_pins_grid": "没有引脚数据。请先识别一张引脚图。",
        "copied": "已复制 {n} 个引脚。切换到 KiCad 符号编辑器按 Ctrl+V 粘贴。",
        "saved": "已保存: {path}",
        "exported": "已导出: {path}",
        "api_saved": "API Key 已保存。",

        "unsupported_format": "不支持的图片格式。",
        "no_clipboard": "剪贴板中没有图片。",

        "preview_title": "图片预览",
        "click_close": "点击图片或按 Esc 关闭",

        "chat_sidebar": "",
        "chat_send": "",
        "extracted_pins": "已提取引脚",
        "api_settings": "API 设置",
        "symbol_settings": "符号设置",
        "ok": "确定",
        "cancel": "取消",
        "model_hint": "选择预设或输入自定义模型名",
        "endpoint_hint": "选择预设或输入自定义端点",
    },
    "en": {
        "title": "AI Pin Assistant",

        "paste": "Paste",
        "file": "File",
        "symbol_recog": "Recognize",
        "send": "Send",

        "copy_editor": "Copy to Editor",
        "save_sym": "Save .kicad_sym",
        "export_json": "Export JSON",
        "settings_btn": "Settings",

        "settings_title": "Settings",
        "api_key": "API Key",
        "model": "Model",
         "endpoint": "接入点",
        "save_key": "Save Key",
        "free_key": "Get Free Key",
        "symbol_name": "Symbol Name",
        "ref_prefix": "Ref Prefix",
        "pin_length": "Pin Length (mm)",
        "pin_spacing": "Pin Spacing (mm)",
        "show_numbers": "Show Pin Numbers",
        "show_names": "Show Pin Names",

        "welcome": "Welcome! Paste a datasheet pin diagram, then click Recognize.",
        "thinking": "Thinking...",
        "analyzing": "Analyzing image...",

        "image_pasted": "Image pasted. Click Recognize to analyze.",
        "image_loaded": "Image loaded: {name}. Click Recognize.",

        "no_image": "No image loaded. Please paste or open a pin diagram first.",
        "no_api_key": "API key not set. Open Settings and enter your API key.",
        "no_pins": "No pins detected. Try a clearer image or check your API key.",
        "analysis_failed": "Analysis failed:\n{error}",
        "success_pins": "Success: {n} pins extracted.\n{s}",

        "no_pins_grid": "No pin data. Analyze an image first.",
        "copied": "Copied {n} pins. Switch to KiCad Symbol Editor and press Ctrl+V.",
        "saved": "Saved: {path}",
        "exported": "Exported: {path}",
        "api_saved": "API key saved.",

        "unsupported_format": "Unsupported image format.",
        "no_clipboard": "No image found on clipboard.",

        "preview_title": "Image Preview",
        "click_close": "Click image or press Escape to close",

        "extracted_pins": "Extracted Pins",
        "api_settings": "API Settings",
        "symbol_settings": "Symbol Settings",
        "ok": "OK",
        "cancel": "Cancel",
        "model_hint": "Select a preset or type a custom model name",
        "api_key_hint": "Select a preset or type a custom API Key",
        "endpoint_hint": "选择预设或输入自定义接入点",
    },
}


def T(key: str, **kwargs) -> str:
    """Translate a key. Falls back to English if key not found in current language."""
    text = STRINGS.get(LANG, STRINGS["en"]).get(key)
    if text is None:
        text = STRINGS["en"].get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text
