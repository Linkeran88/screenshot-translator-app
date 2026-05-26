import json
import re
import sys
import threading
import traceback
import urllib.request
import urllib.parse
from datetime import datetime
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageOps, ImageFilter
import pytesseract
from deep_translator import GoogleTranslator
from pynput import keyboard as pynput_keyboard
import mss

from PyQt6.QtCore import Qt, QRect, QPoint, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap, QImage, QTextOption
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QSpinBox,
    QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget, QGraphicsDropShadowEffect, QFileDialog, QSplitter, QSizeGrip
)

APP_NAME = "截图翻译"
CONFIG_PATH = Path.home() / ".screenshot_translator_app_config.json"
HISTORY_PATH = Path.home() / ".screenshot_translator_app_history.json"
NOTEBOOK_PATH = Path.home() / ".screenshot_translator_app_notebook.txt"
APP_ICON_FILE = Path(__file__).with_name("app_icon.png")
TESSERACT_DEFAULT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if Path(TESSERACT_DEFAULT).exists():
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_DEFAULT

@dataclass
class AppConfig:
    hotkey: str = "<ctrl>+<shift>+x"
    source_lang: str = "auto"
    target_lang_default: str = "zh-CN"
    target_lang_when_chinese: str = "en"
    target_lang_when_non_chinese: str = "zh-CN"
    tesseract_lang: str = "eng+chi_sim"
    bubble_duration_ms: int = 0
    auto_direction: bool = True
    translation_service: str = "google"
    deepl_api_key: str = ""
    deepl_api_url: str = "https://api-free.deepl.com/v2/translate"
    microsoft_api_key: str = ""
    microsoft_region: str = ""
    microsoft_endpoint: str = "https://api.cognitive.microsofttranslator.com"
    openai_api_key: str = ""
    openai_api_url: str = "https://api.openai.com/v1/chat/completions"
    openai_model: str = "gpt-4o-mini"
    custom_api_url: str = ""
    custom_api_key: str = ""
    save_history: bool = True
    max_history_items: int = 300
    tts_rate: int = 170
    always_on_top: bool = True
    ocr_scale: int = 2
    ocr_grayscale: bool = True
    ocr_sharpen: bool = True
    ocr_threshold: bool = False

class ConfigStore:
    @staticmethod
    def load() -> AppConfig:
        if not CONFIG_PATH.exists():
            return AppConfig()
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            default = asdict(AppConfig())
            default.update(data)
            return AppConfig(**default)
        except Exception:
            return AppConfig()

    @staticmethod
    def save(config: AppConfig) -> None:
        CONFIG_PATH.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")


class HistoryStore:
    MAX_ITEMS = 200

    @staticmethod
    def load() -> list:
        if not HISTORY_PATH.exists():
            return []
        try:
            data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    @staticmethod
    def save(records: list) -> None:
        try:
            max_items = ConfigStore.load().max_history_items
        except Exception:
            max_items = HistoryStore.MAX_ITEMS
        HISTORY_PATH.write_text(json.dumps(records[:max_items], ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def add_record(record: dict) -> None:
        records = HistoryStore.load()
        records.insert(0, record)
        HistoryStore.save(records)


class NotebookStore:
    @staticmethod
    def load_text() -> str:
        if not NOTEBOOK_PATH.exists():
            return ""
        try:
            return NOTEBOOK_PATH.read_text(encoding="utf-8")
        except Exception:
            return ""

    @staticmethod
    def save_text(text: str) -> None:
        NOTEBOOK_PATH.write_text(text or "", encoding="utf-8")

    @staticmethod
    def append_entry(title: str, content: str) -> None:
        existing = NotebookStore.load_text().strip()
        entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {title}\n{content.strip()}\n"
        merged = entry if not existing else existing + "\n\n" + entry
        NotebookStore.save_text(merged)


class SpeechManager:
    def __init__(self):
        self._engine = None
        self._engine_lock = threading.Lock()
        self._thread = None
        self._voice_cache = None

    def available_voices(self):
        if self._voice_cache is not None:
            return self._voice_cache
        voices_out = []
        try:
            import pyttsx3
            engine = pyttsx3.init()
            for index, voice in enumerate(engine.getProperty('voices') or []):
                name = getattr(voice, 'name', None) or f'语音 {index + 1}'
                voice_id = getattr(voice, 'id', '')
                langs = getattr(voice, 'languages', []) or []
                lang_text = ''
                try:
                    lang_text = ' '.join(str(x) for x in langs)
                except Exception:
                    lang_text = ''
                label = name if not lang_text else f'{name} · {lang_text}'
                voices_out.append((label, voice_id))
            try:
                engine.stop()
            except Exception:
                pass
        except Exception:
            pass
        if not voices_out:
            voices_out = [('System default voice', '')]
        self._voice_cache = voices_out
        return voices_out

    def speak(self, text: str, voice_id: str = '', rate: int = 170, error_callback=None):
        text = (text or '').strip()
        if not text:
            return
        self.stop()

        def runner():
            engine = None
            try:
                import pyttsx3
                engine = pyttsx3.init()
                with self._engine_lock:
                    self._engine = engine
                if voice_id:
                    engine.setProperty('voice', voice_id)
                engine.setProperty('rate', rate)
                engine.say(text)
                engine.runAndWait()
            except Exception as e:
                if error_callback:
                    QTimer.singleShot(0, lambda e=e: error_callback(str(e)))
            finally:
                try:
                    if engine is not None:
                        engine.stop()
                except Exception:
                    pass
                with self._engine_lock:
                    if self._engine is engine:
                        self._engine = None

        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()

    def stop(self):
        with self._engine_lock:
            engine = self._engine
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass


SPEECH_MANAGER = SpeechManager()

class EventBus(QObject):
    start_capture = pyqtSignal()
    show_settings = pyqtSignal()
    show_main = pyqtSignal()
    show_history = pyqtSignal()
    show_notebook = pyqtSignal()
    quit_app = pyqtSignal()

class LanguageDetector:
    CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
    LATIN_RE = re.compile(r"[A-Za-z]")

    @classmethod
    def contains_chinese(cls, text: str) -> bool:
        return bool(cls.CHINESE_RE.search(text))

    @classmethod
    def choose_target_language(cls, text: str, config: AppConfig) -> str:
        if not config.auto_direction:
            return config.target_lang_default
        if cls.contains_chinese(text):
            return config.target_lang_when_chinese
        return config.target_lang_when_non_chinese

    @classmethod
    def direction_label(cls, text: str, target: str) -> str:
        if cls.contains_chinese(text):
            source = "中文"
        elif cls.LATIN_RE.search(text):
            source = "Foreign"
        else:
            source = "自动"
        target_name = {"zh-CN":"中文", "en":"英文", "ja":"日文", "ko":"韩文", "fr":"法文", "de":"德文", "es":"西班牙文"}.get(target, target)
        return f"{source} to {target_name}"


class TranslationService:
    SERVICE_OPTIONS = [
        ("Google 免费源", "google"),
        ("DeepL API", "deepl"),
        ("Microsoft Translator API", "microsoft"),
        ("OpenAI API", "openai"),
        ("自定义 API", "custom_api"),
    ]

    @staticmethod
    def normalize_service(service: str) -> str:
        mapping = {
            "Google 免费源": "google",
            "DeepL API": "deepl",
            "Microsoft Translator API": "microsoft",
            "OpenAI API": "openai",
            "自定义 API": "custom_api",
        }
        return mapping.get(service, service or "google")

    @staticmethod
    def lang_for_deepl(code: str) -> str:
        mapping = {
            "auto": "",
            "zh-CN": "ZH",
            "en": "EN",
            "ja": "JA",
            "ko": "KO",
            "fr": "FR",
            "de": "DE",
            "es": "ES",
        }
        return mapping.get(code, code.upper())

    @staticmethod
    def lang_for_microsoft(code: str) -> str:
        mapping = {
            "zh-CN": "zh-Hans",
            "en": "en",
            "ja": "ja",
            "ko": "ko",
            "fr": "fr",
            "de": "de",
            "es": "es",
        }
        return mapping.get(code, code)

    @staticmethod
    def post_json(url: str, payload, headers: dict | None = None, timeout: int = 30):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            if value:
                req.add_header(key, value)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}

    @staticmethod
    def post_form(url: str, data: dict, headers: dict | None = None, timeout: int = 30):
        body = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        for key, value in (headers or {}).items():
            if value:
                req.add_header(key, value)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}

    @staticmethod
    def translate_with_deepl(text: str, source: str, target: str, config) -> str:
        api_key = getattr(config, "deepl_api_key", "")
        if not api_key:
            raise RuntimeError("DeepL API Key 未配置。请在设置中心填写 DeepL API Key。")
        url = getattr(config, "deepl_api_url", "") or "https://api-free.deepl.com/v2/translate"
        payload = {
            "auth_key": api_key,
            "text": text,
            "target_lang": TranslationService.lang_for_deepl(target),
        }
        source_lang = TranslationService.lang_for_deepl(source)
        if source_lang:
            payload["source_lang"] = source_lang
        data = TranslationService.post_form(url, payload)
        translations = data.get("translations") or []
        if translations:
            return translations[0].get("text", "")
        raise RuntimeError("DeepL 返回结果为空。")

    @staticmethod
    def translate_with_microsoft(text: str, source: str, target: str, config) -> str:
        api_key = getattr(config, "microsoft_api_key", "")
        if not api_key:
            raise RuntimeError("Microsoft Translator API Key 未配置。请在设置中心填写 API Key。")
        endpoint = (getattr(config, "microsoft_endpoint", "") or "https://api.cognitive.microsofttranslator.com").rstrip("/")
        params = {"api-version": "3.0", "to": TranslationService.lang_for_microsoft(target)}
        if source and source != "auto":
            params["from"] = TranslationService.lang_for_microsoft(source)
        url = endpoint + "/translate?" + urllib.parse.urlencode(params)
        headers = {
            "Ocp-Apim-Subscription-Key": api_key,
            "Ocp-Apim-Subscription-Region": getattr(config, "microsoft_region", ""),
        }
        data = TranslationService.post_json(url, [{"Text": text}], headers=headers)
        if data and isinstance(data, list):
            translations = data[0].get("translations") or []
            if translations:
                return translations[0].get("text", "")
        raise RuntimeError("Microsoft Translator 返回结果为空。")

    @staticmethod
    def translate_with_openai(text: str, source: str, target: str, config) -> str:
        api_key = getattr(config, "openai_api_key", "")
        if not api_key:
            raise RuntimeError("OpenAI API Key 未配置。请在设置中心填写 API Key。")
        url = getattr(config, "openai_api_url", "") or "https://api.openai.com/v1/chat/completions"
        model = getattr(config, "openai_model", "") or "gpt-4o-mini"
        language_names = {
            "auto": "auto-detected language",
            "zh-CN": "Simplified Chinese",
            "en": "English",
            "ja": "Japanese",
            "ko": "Korean",
            "fr": "French",
            "de": "German",
            "es": "Spanish",
        }
        source_name = language_names.get(source, source)
        target_name = language_names.get(target, target)
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a translation engine. Only return the translated text. Do not explain."},
                {"role": "user", "content": f"Translate from {source_name} to {target_name}:\n\n{text}"},
            ],
            "temperature": 0.1,
        }
        data = TranslationService.post_json(url, payload, headers={"Authorization": f"Bearer {api_key}"})
        try:
            return data["choices"][0]["message"]["content"].strip()
        except Exception:
            raise RuntimeError("OpenAI 返回结果格式不正确。")

    @staticmethod
    def translate_with_custom_api(text: str, source: str, target: str, config) -> str:
        url = getattr(config, "custom_api_url", "")
        if not url:
            raise RuntimeError("自定义 API URL 未配置。请在设置中心填写 URL。")
        headers = {}
        api_key = getattr(config, "custom_api_key", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {"text": text, "source": source, "target": target}
        data = TranslationService.post_json(url, payload, headers=headers)
        for key in ["translation", "translated", "result", "text"]:
            value = data.get(key) if isinstance(data, dict) else None
            if isinstance(value, str):
                return value
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            nested = data["data"]
            for key in ["translation", "translated", "result", "text"]:
                value = nested.get(key)
                if isinstance(value, str):
                    return value
        raise RuntimeError("自定义 API 返回结果中未找到 translation / result / text 字段。")

    @staticmethod
    def translate(text: str, source: str = "auto", target: str = "zh-CN", service: str = "google", config=None) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        service = TranslationService.normalize_service(service)
        if service == "google":
            return GoogleTranslator(source=source, target=target).translate(text)
        if config is None:
            raise RuntimeError("该翻译源需要配置对象。")
        if service == "deepl":
            return TranslationService.translate_with_deepl(text, source, target, config)
        if service == "microsoft":
            return TranslationService.translate_with_microsoft(text, source, target, config)
        if service == "openai":
            return TranslationService.translate_with_openai(text, source, target, config)
        if service == "custom_api":
            return TranslationService.translate_with_custom_api(text, source, target, config)
        return GoogleTranslator(source=source, target=target).translate(text)

def grab_full_screen_image() -> Image.Image:
    with mss.mss() as sct:
        monitor = sct.monitors[0]
        shot = sct.grab(monitor)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
        img.info["monitor_left"] = monitor["left"]
        img.info["monitor_top"] = monitor["top"]
        return img

def pil_to_pixmap(img: Image.Image) -> QPixmap:
    rgba = img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimg = QImage(data, rgba.width, rgba.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())

class CaptureOverlay(QWidget):
    captured = pyqtSignal(Image.Image, QPoint)

    def __init__(self, screen_image: Image.Image):
        super().__init__()
        self.screen_image = screen_image
        self.bg_pixmap = pil_to_pixmap(screen_image)
        self.start_pos = QPoint()
        self.end_pos = QPoint()
        self.is_selecting = False
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_pos = event.position().toPoint()
            self.end_pos = self.start_pos
            self.is_selecting = True
            self.update()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.end_pos = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            self.end_pos = event.position().toPoint()
            self.is_selecting = False
            rect = self.get_selection_rect()
            if rect.width() > 8 and rect.height() > 8:
                crop = self.crop_by_widget_rect(rect)
                self.captured.emit(crop, rect.bottomRight())
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def get_selection_rect(self) -> QRect:
        return QRect(self.start_pos, self.end_pos).normalized()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.bg_pixmap)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        if self.is_selecting:
            rect = self.get_selection_rect()
            source = self.widget_rect_to_image_rect(rect)
            visible_crop = self.bg_pixmap.copy(source)
            painter.drawPixmap(rect, visible_crop)
            painter.setPen(QPen(QColor(0, 160, 255), 2))
            painter.drawRect(rect)

    def widget_rect_to_image_rect(self, rect: QRect) -> QRect:
        win_w = max(1, self.width())
        win_h = max(1, self.height())
        img_w = self.screen_image.width
        img_h = self.screen_image.height
        sx = img_w / win_w
        sy = img_h / win_h
        x = int(round(rect.x() * sx))
        y = int(round(rect.y() * sy))
        w = int(round(rect.width() * sx))
        h = int(round(rect.height() * sy))
        x = max(0, min(x, img_w - 1))
        y = max(0, min(y, img_h - 1))
        w = max(1, min(w, img_w - x))
        h = max(1, min(h, img_h - y))
        return QRect(x, y, w, h)

    def crop_by_widget_rect(self, rect: QRect) -> Image.Image:
        r = self.widget_rect_to_image_rect(rect)
        return self.screen_image.crop((r.x(), r.y(), r.x() + r.width(), r.y() + r.height()))


class TranslationBubble(QWidget):
    def __init__(self, original: str, translated: str, direction: str, duration_ms: int, app_icon=None, config=None):
        super().__init__()
        self.config = config or ConfigStore.load()
        self.duration_ms = duration_ms
        self.drag_pos = None
        self.original = original
        self.translated = translated
        self.direction = direction
        self.app_icon = app_icon or QIcon()
        if not self.app_icon.isNull():
            self.setWindowIcon(self.app_icon)

        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if getattr(self.config, 'always_on_top', True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setStyleSheet("""
            QWidget#card {
                background: rgba(21, 24, 32, 238);
                border: 1px solid rgba(255, 255, 255, 22);
                border-radius: 24px;
            }
            QWidget#hero {
                background: rgba(255, 255, 255, 18);
                border: 1px solid rgba(255, 255, 255, 24);
                border-radius: 18px;
            }
            QWidget#panel {
                background: rgba(255, 255, 255, 12);
                border: 1px solid rgba(255, 255, 255, 16);
                border-radius: 18px;
            }
            QLabel {
                color: #F6F7FB;
                background: transparent;
            }
            QLabel#title {
                font-size: 19px;
                font-weight: 700;
                color: #FFFFFF;
            }
            QLabel#subtitle {
                color: rgba(255,255,255,155);
                font-size: 12px;
            }
            QLabel#chip {
                background: rgba(0, 122, 255, 28);
                color: #A9D2FF;
                border: 1px solid rgba(80, 160, 255, 55);
                border-radius: 12px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#sectionTitle {
                color: rgba(255,255,255,205);
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#meta {
                color: rgba(255,255,255,120);
                font-size: 11px;
            }
            QLabel#controlLabel {
                color: rgba(255,255,255,145);
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#dotRed, QLabel#dotYellow, QLabel#dotGreen {
                min-width: 12px; max-width: 12px; min-height: 12px; max-height: 12px;
                border-radius: 6px; border: 1px solid rgba(0,0,0,25);
            }
            QLabel#dotRed { background: #FF5F57; }
            QLabel#dotYellow { background: #FEBC2E; }
            QLabel#dotGreen { background: #28C840; }
            QComboBox {
                min-height: 38px;
                border-radius: 12px;
                padding: 0 12px;
                color: white;
                background: rgba(255,255,255,14);
                border: 1px solid rgba(255,255,255,18);
                font-size: 13px;
                font-weight: 600;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background: #1E2430;
                color: white;
                border: 1px solid rgba(255,255,255,18);
                selection-background-color: rgba(0, 122, 255, 170);
            }
            QTextEdit {
                color: #F4F7FB;
                background: transparent;
                border: none;
                font-size: 15px;
                padding: 0px;
                selection-background-color: rgba(0, 122, 255, 80);
            }
            QSplitter::handle:vertical {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(255,255,255,14),
                    stop:0.5 rgba(0,122,255,95),
                    stop:1 rgba(255,255,255,14));
                min-height: 22px;
                border-radius: 10px;
                border: 1px solid rgba(130,190,255,80);
                margin: 6px 80px;
            }
            QSplitter::handle:vertical:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(255,255,255,20),
                    stop:0.5 rgba(0,122,255,180),
                    stop:1 rgba(255,255,255,20));
                border: 1px solid rgba(150,210,255,150);
            }
            QSizeGrip {
                width: 24px;
                height: 24px;
                background: rgba(255,255,255,10);
                border: 1px solid rgba(255,255,255,18);
                border-radius: 8px;
            }
            QPushButton {
                min-height: 38px; border-radius: 12px; padding: 0 14px;
                font-size: 13px; font-weight: 600; border: 1px solid rgba(255,255,255,18);
            }
            QPushButton#primary {
                background: rgba(0, 122, 255, 220); color: white; border: 1px solid rgba(0, 122, 255, 120);
            }
            QPushButton#primary:hover { background: rgba(20, 132, 255, 240); }
            QPushButton#secondary {
                background: rgba(255,255,255,14); color: #FFFFFF;
            }
            QPushButton#secondary:hover { background: rgba(255,255,255,20); }
            QPushButton#ghost {
                background: rgba(255,255,255,10); color: rgba(255,255,255,220);
            }
            QPushButton#ghost:hover { background: rgba(255,255,255,16); }
            QPushButton#swapBtn {
                min-width: 42px; max-width: 42px; padding: 0;
                background: rgba(255,255,255,12); color: #D7E7FF;
            }
        """)

        self.card = QWidget(self)
        self.card.setObjectName("card")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(52)
        shadow.setOffset(0, 16)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.card.setGraphicsEffect(shadow)

        hero = QWidget()
        hero.setObjectName("hero")
        dot_red = QLabel(); dot_red.setObjectName("dotRed")
        dot_yellow = QLabel(); dot_yellow.setObjectName("dotYellow")
        dot_green = QLabel(); dot_green.setObjectName("dotGreen")
        dots = QHBoxLayout()
        dots.setSpacing(6)
        dots.addWidget(dot_red); dots.addWidget(dot_yellow); dots.addWidget(dot_green)

        title = QLabel(APP_NAME)
        title.setObjectName("title")
        subtitle = QLabel("深色毛玻璃风格 · 拖动中间蓝色分隔条调整文本框，右下角可缩放窗口")
        subtitle.setObjectName("subtitle")
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        title_block.addWidget(title)
        title_block.addWidget(subtitle)

        self.direction_chip = QLabel(direction)
        self.direction_chip.setObjectName("chip")
        self.direction_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hero_top = QHBoxLayout()
        hero_top.setSpacing(10)
        hero_top.addLayout(dots)
        hero_top.addSpacing(6)
        hero_top.addLayout(title_block)
        hero_top.addStretch(1)
        hero_top.addWidget(self.direction_chip)

        self.hero_meta_left = QLabel(f"译文长度：{len(translated)}")
        self.hero_meta_left.setObjectName("meta")
        self.hero_meta_right = QLabel(f"原文长度：{len(original)}")
        self.hero_meta_right.setObjectName("meta")
        hero_meta = QHBoxLayout()
        hero_meta.addWidget(self.hero_meta_left)
        hero_meta.addStretch(1)
        hero_meta.addWidget(self.hero_meta_right)

        from_label = QLabel("源语言")
        from_label.setObjectName("controlLabel")
        to_label = QLabel("目标语言")
        to_label.setObjectName("controlLabel")
        self.source_combo = QComboBox()
        self.target_combo = QComboBox()
        for label, code in self.language_options():
            self.source_combo.addItem(label, code)
            self.target_combo.addItem(label, code)
        self._set_combo_value(self.source_combo, 'en')
        self._set_combo_value(self.target_combo, 'zh-CN')
        self.source_combo.currentIndexChanged.connect(self.update_direction_chip)
        self.target_combo.currentIndexChanged.connect(self.update_direction_chip)

        self.translate_btn = QPushButton("翻译")
        self.translate_btn.setObjectName("primary")
        self.translate_btn.clicked.connect(self.retranslate)

        self.swap_btn = QPushButton("⇄")
        self.swap_btn.setObjectName("swapBtn")
        self.swap_btn.clicked.connect(self.swap_languages)

        control_row = QHBoxLayout()
        control_row.setSpacing(10)
        control_row.addWidget(from_label)
        control_row.addWidget(self.source_combo, 1)
        control_row.addWidget(to_label)
        control_row.addWidget(self.target_combo, 1)
        control_row.addWidget(self.swap_btn)
        control_row.addWidget(self.translate_btn)

        voice_label = QLabel("语音")
        voice_label.setObjectName("controlLabel")
        self.voice_combo = QComboBox()
        self.populate_voices()
        play_original_btn = QPushButton("▶ 朗读原文")
        play_original_btn.setObjectName("secondary")
        play_translation_btn = QPushButton("▶ 朗读译文")
        play_translation_btn.setObjectName("primary")
        stop_voice_btn = QPushButton("停止")
        stop_voice_btn.setObjectName("ghost")
        play_original_btn.clicked.connect(lambda: self.speak_text(self.orig_editor.toPlainText()))
        play_translation_btn.clicked.connect(lambda: self.speak_text(self.trans_editor.toPlainText()))
        stop_voice_btn.clicked.connect(self.stop_speaking)

        voice_row = QHBoxLayout()
        voice_row.setSpacing(10)
        voice_row.addWidget(voice_label)
        voice_row.addWidget(self.voice_combo, 1)
        voice_row.addWidget(play_original_btn)
        voice_row.addWidget(play_translation_btn)
        voice_row.addWidget(stop_voice_btn)

        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(16, 14, 16, 14)
        hero_layout.setSpacing(10)
        hero_layout.addLayout(hero_top)
        hero_layout.addLayout(hero_meta)
        hero_layout.addLayout(control_row)
        hero_layout.addLayout(voice_row)

        self.trans_panel, self.trans_editor, self.trans_meta = self._build_panel("译文", translated, big=True)
        self.orig_panel, self.orig_editor, self.orig_meta = self._build_panel("原文", original, big=False)

        self.text_splitter = QSplitter(Qt.Orientation.Vertical)
        self.text_splitter.setChildrenCollapsible(False)
        self.text_splitter.setOpaqueResize(True)
        self.text_splitter.setHandleWidth(22)
        self.text_splitter.setMinimumHeight(360)
        self.text_splitter.setToolTip("拖动中间蓝色分隔条，可调整译文和原文区域大小")
        self.text_splitter.addWidget(self.trans_panel)
        self.text_splitter.addWidget(self.orig_panel)
        self.text_splitter.setStretchFactor(0, 3)
        self.text_splitter.setStretchFactor(1, 2)
        self.text_splitter.setSizes([420, 260])

        history_btn = QPushButton("历史记录")
        history_btn.setObjectName("secondary")
        notebook_btn = QPushButton("记事本")
        notebook_btn.setObjectName("secondary")
        add_note_btn = QPushButton("摘录到记事本")
        add_note_btn.setObjectName("secondary")
        pin_btn = QPushButton("置顶 / 取消置顶")
        pin_btn.setObjectName("ghost")
        history_btn.clicked.connect(self.open_history)
        notebook_btn.clicked.connect(self.open_notebook)
        add_note_btn.clicked.connect(self.add_translation_excerpt_to_notebook)
        pin_btn.clicked.connect(self.toggle_always_on_top)

        utility_row = QHBoxLayout()
        utility_row.setSpacing(10)
        utility_row.addWidget(history_btn)
        utility_row.addWidget(notebook_btn)
        utility_row.addWidget(add_note_btn)
        utility_row.addWidget(pin_btn)
        utility_row.addStretch(1)

        copy_original_btn = QPushButton("复制原文")
        copy_original_btn.setObjectName("secondary")
        copy_translation_btn = QPushButton("复制译文")
        copy_translation_btn.setObjectName("primary")
        copy_all_btn = QPushButton("复制全部")
        copy_all_btn.setObjectName("secondary")
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("ghost")
        copy_original_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.orig_editor.toPlainText()))
        copy_translation_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.trans_editor.toPlainText()))
        copy_all_btn.clicked.connect(self.copy_all)
        close_btn.clicked.connect(self.close)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addWidget(copy_original_btn)
        button_row.addWidget(copy_translation_btn)
        button_row.addWidget(copy_all_btn)
        button_row.addStretch(1)
        button_row.addWidget(close_btn)
        self.resize_grip = QSizeGrip(self)
        self.resize_grip.setToolTip("拖动这里缩放整个翻译窗口")
        button_row.addWidget(self.resize_grip)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(14)
        card_layout.addWidget(hero)
        card_layout.addWidget(self.text_splitter, 1)
        card_layout.addLayout(utility_row)
        card_layout.addLayout(button_row)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.addWidget(self.card)

        self.resize(900, 760)
        self.setMinimumSize(760, 640)
        self.update_direction_chip()
        self.save_history_entry()

    @staticmethod
    def language_options():
        return [
            ("自动", "auto"),
            ("中文", "zh-CN"),
            ("英文", "en"),
            ("日文", "ja"),
            ("韩文", "ko"),
            ("法文", "fr"),
            ("德文", "de"),
            ("西班牙文", "es"),
        ]

    def _set_combo_value(self, combo, value):
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def current_source_target(self):
        return (self.source_combo.currentData() or 'en', self.target_combo.currentData() or 'zh-CN')

    def update_direction_chip(self):
        source, target = self.current_source_target()
        self.direction_chip.setText(f"{self.human_label(source)} → {self.human_label(target)}")

    def swap_languages(self):
        source, target = self.current_source_target()
        if source == 'auto':
            source = 'en'
        self._set_combo_value(self.source_combo, target)
        self._set_combo_value(self.target_combo, source)
        self.update_direction_chip()
        self.retranslate()

    def _build_panel(self, title: str, content: str, big: bool = False):
        panel = QWidget()
        panel.setObjectName("panel")
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        meta_label = QLabel(self.word_meta(content))
        meta_label.setObjectName("meta")
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(title_label)
        head.addStretch(1)
        head.addWidget(meta_label)
        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(content)
        editor.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        if big:
            editor.setMinimumHeight(120)
            editor.setStyleSheet("QTextEdit { font-size: 16px; font-weight: 500; color: #F6F8FC; }")
        else:
            editor.setMinimumHeight(90)
            editor.setStyleSheet("QTextEdit { font-size: 14px; color: rgba(244,248,252,220); }")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        layout.addLayout(head)
        layout.addWidget(editor)
        return panel, editor, meta_label

    def word_meta(self, content: str) -> str:
        return f"{len(content.split())} words" if content else "0 words"

    def human_label(self, code: str) -> str:
        mapping = {
            'auto': '自动', 'zh-CN': '中文', 'en': '英文', 'ja': '日文',
            'ko': '韩文', 'fr': '法文', 'de': '德文', 'es': '西班牙文'
        }
        return mapping.get(code, code)

    def populate_voices(self):
        self.voice_combo.clear()
        for label, voice_id in SPEECH_MANAGER.available_voices():
            self.voice_combo.addItem(label, voice_id)

    def speak_text(self, text: str):
        text = (text or '').strip()
        if not text:
            QMessageBox.information(self, '语音', '没有可朗读的文字。')
            return
        voice_id = self.voice_combo.currentData() or ''
        SPEECH_MANAGER.speak(text, voice_id, getattr(self.config, 'tts_rate', 170), error_callback=lambda msg: QMessageBox.warning(self, '语音播放错误', msg))

    def stop_speaking(self):
        SPEECH_MANAGER.stop()

    def selected_translation_excerpt(self):
        selected = self.trans_editor.textCursor().selectedText().replace('\u2029', '\n').strip()
        return selected or self.trans_editor.toPlainText().strip()

    def add_translation_excerpt_to_notebook(self):
        excerpt = self.selected_translation_excerpt()
        if not excerpt:
            QMessageBox.information(self, '记事本', '没有可摘录的译文。')
            return
        NotebookStore.append_entry(f"{self.direction_chip.text()} · Translation excerpt", excerpt)
        QMessageBox.information(self, '记事本', '已添加到记事本。')

    def toggle_always_on_top(self):
        current = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, not current)
        self.show()
        self.raise_()

    def open_history(self):
        dialog = HistoryDialog(self.app_icon)
        dialog.exec()

    def open_notebook(self):
        dialog = NotebookDialog(self.app_icon)
        dialog.exec()

    def save_history_entry(self):
        if not getattr(self.config, 'save_history', True):
            return
        source, target = self.current_source_target()
        HistoryStore.add_record({
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source': source,
            'target': target,
            'direction': self.direction_chip.text(),
            'original': self.orig_editor.toPlainText(),
            'translation': self.trans_editor.toPlainText(),
        })

    def retranslate(self):
        source, target = self.current_source_target()
        if source == target and source != 'auto':
            QMessageBox.information(self, '语言选择', '源语言和目标语言不能相同。')
            return
        self.update_direction_chip()
        try:
            self.translate_btn.setText('Translating...')
            self.translate_btn.setEnabled(False)
            translated = TranslationService.translate(self.original, source=source, target=target, service=getattr(self.config, 'translation_service', 'google'), config=self.config)
            self.translated = translated
            self.trans_editor.setPlainText(translated)
            self.trans_meta.setText(self.word_meta(translated))
            self.hero_meta_left.setText(f"译文长度：{len(translated)}")
            self.save_history_entry()
        except Exception as e:
            QMessageBox.warning(self, '翻译失败', str(e))
        finally:
            self.translate_btn.setText('翻译')
            self.translate_btn.setEnabled(True)

    def copy_all(self):
        QApplication.clipboard().setText('译文:\n' + self.trans_editor.toPlainText() + '\n\n原文:\n' + self.orig_editor.toPlainText())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self.drag_pos)

    def mouseReleaseEvent(self, event):
        self.drag_pos = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # QSizeGrip 放在按钮栏里；这里保留 resizeEvent 便于窗口尺寸变化时稳定刷新布局。
        self.update()

    def show_near(self, anchor: QPoint):
        screen_geo = QApplication.primaryScreen().availableGeometry()
        x = min(anchor.x() + 18, screen_geo.right() - self.width() - 18)
        y = min(anchor.y() + 18, screen_geo.bottom() - self.height() - 18)
        x = max(screen_geo.left() + 18, x)
        y = max(screen_geo.top() + 18, y)
        self.move(x, y)
        self.show()
        if self.duration_ms > 0:
            QTimer.singleShot(self.duration_ms, self.close)


class HistoryDialog(QDialog):
    def __init__(self, app_icon=None):
        super().__init__()
        self.setWindowTitle('翻译历史')
        if app_icon and not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self.resize(900, 640)
        self.current_records = []

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('搜索历史：关键词、原文、译文、语言、日期...')
        self.search_input.textChanged.connect(self.refresh)

        self.viewer = QTextEdit()
        self.viewer.setReadOnly(True)

        refresh_btn = QPushButton('刷新')
        export_md_btn = QPushButton('导出 Markdown')
        export_csv_btn = QPushButton('导出 CSV')
        add_notebook_btn = QPushButton('将当前结果加入记事本')
        clear_btn = QPushButton('清空历史')
        close_btn = QPushButton('关闭')
        refresh_btn.clicked.connect(self.refresh)
        export_md_btn.clicked.connect(self.export_markdown)
        export_csv_btn.clicked.connect(self.export_csv)
        add_notebook_btn.clicked.connect(self.add_shown_to_notebook)
        clear_btn.clicked.connect(self.clear_history)
        close_btn.clicked.connect(self.accept)

        row = QHBoxLayout()
        row.addWidget(refresh_btn)
        row.addWidget(export_md_btn)
        row.addWidget(export_csv_btn)
        row.addWidget(add_notebook_btn)
        row.addWidget(clear_btn)
        row.addStretch(1)
        row.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.search_input)
        layout.addWidget(self.viewer)
        layout.addLayout(row)
        self.refresh()

    def filtered_records(self):
        records = HistoryStore.load()
        keyword = (self.search_input.text() if hasattr(self, 'search_input') else '').strip().lower()
        if keyword:
            def match(item):
                haystack = '\n'.join([
                    str(item.get('time', '')),
                    str(item.get('direction', '')),
                    str(item.get('source', '')),
                    str(item.get('target', '')),
                    str(item.get('original', '')),
                    str(item.get('translation', '')),
                ]).lower()
                return keyword in haystack
            records = [item for item in records if match(item)]
        return records

    def refresh(self):
        records = self.filtered_records()
        self.current_records = records
        keyword = (self.search_input.text() if hasattr(self, 'search_input') else '').strip()
        if not records:
            self.viewer.setPlainText('No matching translation history.' if keyword else '暂无翻译历史。')
            return
        self.viewer.setPlainText(self.records_to_markdown(records, plain=True))

    def records_to_markdown(self, records, plain=False):
        parts = []
        for i, item in enumerate(records, 1):
            parts.append(
                f"## {i}. [{item.get('time', '')}] {item.get('direction', '')}\n\n"
                f"**Original**\n\n{item.get('original', '')}\n\n"
                f"**Translation**\n\n{item.get('translation', '')}\n"
            )
        separator = '\n' + ('-' * 80) + '\n' if plain else '\n\n---\n\n'
        return separator.join(parts)

    def export_markdown(self):
        records = self.current_records or self.filtered_records()
        if not records:
            QMessageBox.information(self, 'Export', '没有可导出的历史记录。')
            return
        default = str(Path.home() / 'translation_history.md')
        path, _ = QFileDialog.getSaveFileName(self, '导出历史 Markdown', default, 'Markdown Files (*.md);;All Files (*)')
        if path:
            Path(path).write_text('# Translation History\n\n' + self.records_to_markdown(records), encoding='utf-8')

    def export_csv(self):
        import csv
        records = self.current_records or self.filtered_records()
        if not records:
            QMessageBox.information(self, 'Export', '没有可导出的历史记录。')
            return
        default = str(Path.home() / 'translation_history.csv')
        path, _ = QFileDialog.getSaveFileName(self, '导出历史 CSV', default, 'CSV Files (*.csv);;All Files (*)')
        if path:
            with open(path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['time', 'source', 'target', 'direction', 'original', 'translation'])
                for item in records:
                    writer.writerow([item.get('time',''), item.get('source',''), item.get('target',''), item.get('direction',''), item.get('original',''), item.get('translation','')])

    def add_shown_to_notebook(self):
        records = self.current_records or self.filtered_records()
        if not records:
            QMessageBox.information(self, '记事本', '没有可添加的历史记录。')
            return
        NotebookStore.append_entry('历史记录摘录', self.records_to_markdown(records[:20]))
        QMessageBox.information(self, '记事本', '当前显示的历史记录已加入记事本。')

    def clear_history(self):
        if QMessageBox.question(self, '清空历史', '确定清空所有翻译历史吗？') == QMessageBox.StandardButton.Yes:
            HistoryStore.save([])
            self.refresh()


class NotebookDialog(QDialog):
    def __init__(self, app_icon=None):
        super().__init__()
        self.setWindowTitle('记事本')
        if app_icon and not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self.resize(760, 560)
        self.editor = QTextEdit()
        self.editor.setPlainText(NotebookStore.load_text())
        save_btn = QPushButton('保存')
        reload_btn = QPushButton('重新加载')
        export_txt_btn = QPushButton('导出 TXT')
        export_md_btn = QPushButton('导出 Markdown')
        clear_btn = QPushButton('清空')
        close_btn = QPushButton('关闭')
        save_btn.clicked.connect(self.save)
        reload_btn.clicked.connect(self.reload)
        export_txt_btn.clicked.connect(self.export_txt)
        export_md_btn.clicked.connect(self.export_markdown)
        clear_btn.clicked.connect(self.clear_notes)
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addWidget(save_btn)
        row.addWidget(reload_btn)
        row.addWidget(export_txt_btn)
        row.addWidget(export_md_btn)
        row.addWidget(clear_btn)
        row.addStretch(1)
        row.addWidget(close_btn)
        layout = QVBoxLayout(self)
        layout.addWidget(self.editor)
        layout.addLayout(row)

    def save(self):
        NotebookStore.save_text(self.editor.toPlainText())
        QMessageBox.information(self, '记事本', '记事本已保存。')

    def reload(self):
        self.editor.setPlainText(NotebookStore.load_text())

    def export_txt(self):
        self.save()
        default = str(Path.home() / f"screenshot_translator_notes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        path, _ = QFileDialog.getSaveFileName(self, '导出 TXT', default, 'Text Files (*.txt);;All Files (*)')
        if path:
            Path(path).write_text(self.editor.toPlainText(), encoding='utf-8')
            QMessageBox.information(self, '记事本', 'TXT 已导出。')

    def export_markdown(self):
        self.save()
        default = str(Path.home() / f"screenshot_translator_notes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
        path, _ = QFileDialog.getSaveFileName(self, '导出 Markdown', default, 'Markdown Files (*.md);;All Files (*)')
        if path:
            content = self.editor.toPlainText().strip()
            md = '# Screenshot Translator Notes\n\n' + (content if content else '') + '\n'
            Path(path).write_text(md, encoding='utf-8')
            QMessageBox.information(self, '记事本', 'Markdown 已导出。')

    def clear_notes(self):
        if QMessageBox.question(self, '清空记事本', '确定清空记事本所有内容吗？') == QMessageBox.StandardButton.Yes:
            self.editor.clear()
            NotebookStore.save_text('')


class SettingsDialog(QDialog):
    config_saved = pyqtSignal(AppConfig)
    def __init__(self, config: AppConfig):
        super().__init__()
        self.setWindowTitle("设置中心")
        if APP_ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_FILE)))
        self.resize(560, 560)
        self.config = config
        self.setStyleSheet("""
            QDialog { background: #171B24; color: white; }
            QLabel, QCheckBox { color: white; }
            QLineEdit, QComboBox, QSpinBox {
                min-height: 30px; border-radius: 8px; padding: 4px 8px;
                background: rgba(255,255,255,18); color: white; border: 1px solid rgba(255,255,255,28);
            }
            QComboBox QAbstractItemView {
                background: #1E2430;
                color: white;
                border: 1px solid rgba(255,255,255,35);
                selection-background-color: #1677ff;
                selection-color: white;
            }
            QPushButton { min-height: 36px; border-radius: 10px; padding: 0 14px; background: rgba(255,255,255,18); color: white; border: 1px solid rgba(255,255,255,26); }
            QPushButton:hover { background: rgba(255,255,255,30); }
        """)

        self.hotkey_input = QLineEdit(config.hotkey)
        self.ocr_lang_input = QLineEdit(config.tesseract_lang)
        self.service_combo = QComboBox()
        for label, code in TranslationService.SERVICE_OPTIONS:
            self.service_combo.addItem(label, code)
        idx = self.service_combo.findData(getattr(config, 'translation_service', 'google'))
        self.service_combo.setCurrentIndex(idx if idx >= 0 else 0)

        self.deepl_key_input = QLineEdit(getattr(config, 'deepl_api_key', ''))
        self.deepl_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.deepl_url_input = QLineEdit(getattr(config, 'deepl_api_url', 'https://api-free.deepl.com/v2/translate'))
        self.microsoft_key_input = QLineEdit(getattr(config, 'microsoft_api_key', ''))
        self.microsoft_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.microsoft_region_input = QLineEdit(getattr(config, 'microsoft_region', ''))
        self.microsoft_endpoint_input = QLineEdit(getattr(config, 'microsoft_endpoint', 'https://api.cognitive.microsofttranslator.com'))
        self.openai_key_input = QLineEdit(getattr(config, 'openai_api_key', ''))
        self.openai_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_url_input = QLineEdit(getattr(config, 'openai_api_url', 'https://api.openai.com/v1/chat/completions'))
        self.openai_model_input = QLineEdit(getattr(config, 'openai_model', 'gpt-4o-mini'))
        self.custom_url_input = QLineEdit(getattr(config, 'custom_api_url', ''))
        self.custom_key_input = QLineEdit(getattr(config, 'custom_api_key', ''))
        self.custom_key_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.default_source = QComboBox(); self.default_target = QComboBox()
        self.target_when_chinese = QComboBox(); self.target_when_non_chinese = QComboBox()
        for combo in [self.default_source, self.default_target, self.target_when_chinese, self.target_when_non_chinese]:
            combo.addItems(["auto", "zh-CN", "en", "ja", "ko", "fr", "de", "es"])
        self.default_source.setCurrentText(getattr(config, 'source_lang', 'auto'))
        self.default_target.setCurrentText(config.target_lang_default)
        self.target_when_chinese.setCurrentText(config.target_lang_when_chinese)
        self.target_when_non_chinese.setCurrentText(config.target_lang_when_non_chinese)

        self.auto_direction_checkbox = QCheckBox("自动判断中文 / 非中文翻译方向")
        self.auto_direction_checkbox.setChecked(config.auto_direction)
        self.save_history_checkbox = QCheckBox("保存翻译历史")
        self.save_history_checkbox.setChecked(getattr(config, 'save_history', True))
        self.always_on_top_checkbox = QCheckBox("翻译卡片始终置顶")
        self.always_on_top_checkbox.setChecked(getattr(config, 'always_on_top', True))
        self.ocr_gray_checkbox = QCheckBox("OCR 灰度预处理")
        self.ocr_gray_checkbox.setChecked(getattr(config, 'ocr_grayscale', True))
        self.ocr_sharp_checkbox = QCheckBox("OCR 锐化预处理")
        self.ocr_sharp_checkbox.setChecked(getattr(config, 'ocr_sharpen', True))
        self.ocr_threshold_checkbox = QCheckBox("OCR 高对比阈值")
        self.ocr_threshold_checkbox.setChecked(getattr(config, 'ocr_threshold', False))

        self.duration_input = QSpinBox(); self.duration_input.setRange(0, 60000); self.duration_input.setSingleStep(1000); self.duration_input.setValue(config.bubble_duration_ms); self.duration_input.setSuffix(" ms")
        self.history_max_input = QSpinBox(); self.history_max_input.setRange(20, 2000); self.history_max_input.setValue(getattr(config, 'max_history_items', 300))
        self.tts_rate_input = QSpinBox(); self.tts_rate_input.setRange(80, 260); self.tts_rate_input.setValue(getattr(config, 'tts_rate', 170)); self.tts_rate_input.setSuffix(" wpm")
        self.ocr_scale_input = QSpinBox(); self.ocr_scale_input.setRange(1, 4); self.ocr_scale_input.setValue(getattr(config, 'ocr_scale', 2)); self.ocr_scale_input.setSuffix("x")

        form = QFormLayout()
        form.addRow("快捷键", self.hotkey_input)
        form.addRow("翻译服务", self.service_combo)
        form.addRow("DeepL API Key", self.deepl_key_input)
        form.addRow("DeepL API URL", self.deepl_url_input)
        form.addRow("Microsoft API Key", self.microsoft_key_input)
        form.addRow("Microsoft 区域", self.microsoft_region_input)
        form.addRow("Microsoft Endpoint", self.microsoft_endpoint_input)
        form.addRow("OpenAI API Key", self.openai_key_input)
        form.addRow("OpenAI API URL", self.openai_url_input)
        form.addRow("OpenAI 模型", self.openai_model_input)
        form.addRow("自定义 API URL", self.custom_url_input)
        form.addRow("自定义 API Key", self.custom_key_input)
        form.addRow("默认源语言", self.default_source)
        form.addRow("默认目标语言", self.default_target)
        form.addRow("检测到中文时译为", self.target_when_chinese)
        form.addRow("检测到非中文时译为", self.target_when_non_chinese)
        form.addRow("自动翻译方向", self.auto_direction_checkbox)
        form.addRow("OCR 识别语言", self.ocr_lang_input)
        form.addRow("OCR 放大倍数", self.ocr_scale_input)
        form.addRow("OCR 灰度", self.ocr_gray_checkbox)
        form.addRow("OCR 锐化", self.ocr_sharp_checkbox)
        form.addRow("OCR 阈值", self.ocr_threshold_checkbox)
        form.addRow("语音速度", self.tts_rate_input)
        form.addRow("气泡停留时间", self.duration_input)
        form.addRow("窗口置顶", self.always_on_top_checkbox)
        form.addRow("保存历史", self.save_history_checkbox)
        form.addRow("最大历史数量", self.history_max_input)

        save_btn = QPushButton("保存")
        cancel_btn = QPushButton("取消")
        save_btn.clicked.connect(self.save)
        cancel_btn.clicked.connect(self.reject)
        buttons = QHBoxLayout(); buttons.addStretch(1); buttons.addWidget(save_btn); buttons.addWidget(cancel_btn)
        layout = QVBoxLayout(self); layout.addLayout(form); layout.addLayout(buttons)

    def save(self):
        self.config.hotkey = self.hotkey_input.text().strip() or "<ctrl>+<shift>+x"
        self.config.tesseract_lang = self.ocr_lang_input.text().strip() or "eng+chi_sim"
        self.config.translation_service = self.service_combo.currentData() or "google"
        self.config.deepl_api_key = self.deepl_key_input.text().strip()
        self.config.deepl_api_url = self.deepl_url_input.text().strip() or "https://api-free.deepl.com/v2/translate"
        self.config.microsoft_api_key = self.microsoft_key_input.text().strip()
        self.config.microsoft_region = self.microsoft_region_input.text().strip()
        self.config.microsoft_endpoint = self.microsoft_endpoint_input.text().strip() or "https://api.cognitive.microsofttranslator.com"
        self.config.openai_api_key = self.openai_key_input.text().strip()
        self.config.openai_api_url = self.openai_url_input.text().strip() or "https://api.openai.com/v1/chat/completions"
        self.config.openai_model = self.openai_model_input.text().strip() or "gpt-4o-mini"
        self.config.custom_api_url = self.custom_url_input.text().strip()
        self.config.custom_api_key = self.custom_key_input.text().strip()
        self.config.source_lang = self.default_source.currentText()
        self.config.auto_direction = self.auto_direction_checkbox.isChecked()
        self.config.target_lang_default = self.default_target.currentText()
        self.config.target_lang_when_chinese = self.target_when_chinese.currentText()
        self.config.target_lang_when_non_chinese = self.target_when_non_chinese.currentText()
        self.config.bubble_duration_ms = self.duration_input.value()
        self.config.save_history = self.save_history_checkbox.isChecked()
        self.config.max_history_items = self.history_max_input.value()
        self.config.tts_rate = self.tts_rate_input.value()
        self.config.always_on_top = self.always_on_top_checkbox.isChecked()
        self.config.ocr_scale = self.ocr_scale_input.value()
        self.config.ocr_grayscale = self.ocr_gray_checkbox.isChecked()
        self.config.ocr_sharpen = self.ocr_sharp_checkbox.isChecked()
        self.config.ocr_threshold = self.ocr_threshold_checkbox.isChecked()
        ConfigStore.save(self.config)
        self.config_saved.emit(self.config)
        self.accept()

class ScreenshotTranslator:
    def __init__(self, config: AppConfig):
        self.config = config

    def preprocess_for_ocr(self, image: Image.Image) -> Image.Image:
        img = image.convert("RGB")
        try:
            scale = max(1, int(getattr(self.config, 'ocr_scale', 2)))
            if scale > 1:
                img = img.resize((img.width * scale, img.height * scale), Image.Resampling.LANCZOS)
            if getattr(self.config, 'ocr_grayscale', True):
                img = ImageOps.grayscale(img)
            if getattr(self.config, 'ocr_sharpen', True):
                img = img.filter(ImageFilter.SHARPEN)
            if getattr(self.config, 'ocr_threshold', False):
                if img.mode != 'L':
                    img = ImageOps.grayscale(img)
                img = img.point(lambda p: 255 if p > 170 else 0)
        except Exception:
            return image.convert("RGB")
        return img

    def recognize_text(self, image: Image.Image) -> str:
        img = self.preprocess_for_ocr(image)
        text = pytesseract.image_to_string(img, lang=self.config.tesseract_lang)
        return text.strip()

    def translate_text(self, text: str):
        target = LanguageDetector.choose_target_language(text, self.config)
        translated = TranslationService.translate(text, source=self.config.source_lang, target=target, service=self.config.translation_service, config=self.config)
        return translated, LanguageDetector.direction_label(text, target)

    def process(self, image: Image.Image):
        original = self.recognize_text(image)
        if not original:
            return "", "", ""
        translated, direction = self.translate_text(original)
        return original, translated, direction

class MainPanel(QWidget):
    def __init__(self, bus: EventBus, app_icon=None):
        super().__init__()
        self.bus = bus
        self.setWindowTitle(APP_NAME)
        if app_icon and not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self.resize(420, 300)
        self.setStyleSheet("""
            QWidget { background: #171B24; color: white; }
            QLabel#title { font-size: 24px; font-weight: 700; }
            QLabel#hint { color: rgba(255,255,255,150); font-size: 13px; }
            QPushButton {
                min-height: 42px;
                border-radius: 12px;
                padding: 0 16px;
                font-size: 14px;
                font-weight: 600;
                color: white;
                background: rgba(255,255,255,18);
                border: 1px solid rgba(255,255,255,24);
            }
            QPushButton:hover { background: rgba(255,255,255,30); }
            QPushButton#primary { background: rgba(0,122,255,220); border: 1px solid rgba(0,122,255,120); }
        """)
        title = QLabel(APP_NAME)
        title.setObjectName('title')
        hint = QLabel('按 Ctrl + Shift + X 截图翻译，或使用下面的按钮。关闭这个面板后，程序会继续在系统托盘运行。')
        hint.setObjectName('hint')
        hint.setWordWrap(True)
        capture_btn = QPushButton('截图翻译')
        capture_btn.setObjectName('primary')
        history_btn = QPushButton('翻译历史')
        notebook_btn = QPushButton('记事本')
        settings_btn = QPushButton('设置')
        quit_btn = QPushButton('退出应用')
        capture_btn.clicked.connect(self.bus.start_capture.emit)
        history_btn.clicked.connect(self.bus.show_history.emit)
        notebook_btn.clicked.connect(self.bus.show_notebook.emit)
        settings_btn.clicked.connect(self.bus.show_settings.emit)
        quit_btn.clicked.connect(self.bus.quit_app.emit)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(8)
        layout.addWidget(capture_btn)
        layout.addWidget(history_btn)
        layout.addWidget(notebook_btn)
        layout.addWidget(settings_btn)
        layout.addStretch(1)
        layout.addWidget(quit_btn)

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def changeEvent(self, event):
        if event.type() == event.Type.WindowStateChange and self.isMinimized():
            QTimer.singleShot(0, self.hide)
        super().changeEvent(event)

    def show_panel(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

class TrayIcon:
    def __init__(self, app, bus, config):
        self.icon = QIcon(str(APP_ICON_FILE)) if APP_ICON_FILE.exists() else self.create_icon()
        self.tray = QSystemTrayIcon(self.icon, app)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        show_main_action = QAction("显示主面板", menu)
        capture_action = QAction("截图翻译", menu)
        history_action = QAction("翻译历史", menu)
        notebook_action = QAction("记事本", menu)
        settings_action = QAction("设置", menu)
        quit_action = QAction("退出", menu)
        show_main_action.triggered.connect(bus.show_main.emit)
        capture_action.triggered.connect(bus.start_capture.emit)
        history_action.triggered.connect(bus.show_history.emit)
        notebook_action.triggered.connect(bus.show_notebook.emit)
        settings_action.triggered.connect(bus.show_settings.emit)
        quit_action.triggered.connect(bus.quit_app.emit)
        menu.addAction(show_main_action)
        menu.addAction(capture_action)
        menu.addAction(history_action)
        menu.addAction(notebook_action)
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: bus.show_main.emit() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()
    def create_icon(self):
        pixmap = QPixmap(64, 64); pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(0, 140, 255)); painter.setPen(Qt.PenStyle.NoPen); painter.drawEllipse(6, 6, 52, 52)
        painter.setPen(QPen(QColor("white"), 5)); painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "T"); painter.end()
        return QIcon(pixmap)
    def show_message(self, title, message):
        self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)

class AppController(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app; self.config = ConfigStore.load(); self.translator = ScreenshotTranslator(self.config)
        self.bus = EventBus(); self.tray = TrayIcon(app, self.bus, self.config)
        app.setWindowIcon(self.tray.icon)
        self.main_panel = MainPanel(self.bus, self.tray.icon)
        self.bubbles = []; self.listener = None
        self.bus.start_capture.connect(self.open_capture_overlay)
        self.bus.show_settings.connect(self.open_settings)
        self.bus.show_main.connect(self.show_main_panel)
        self.bus.show_history.connect(self.open_history)
        self.bus.show_notebook.connect(self.open_notebook)
        self.bus.quit_app.connect(self.quit)
    def start(self):
        self.register_hotkey(); self.tray.show_message(APP_NAME, "Started. Click tray icon to show main panel.")
        self.show_main_panel()
    def register_hotkey(self):
        if self.listener:
            try: self.listener.stop()
            except Exception: pass
        def on_activate(): self.bus.start_capture.emit()
        try:
            self.listener = pynput_keyboard.GlobalHotKeys({self.config.hotkey: on_activate})
            self.listener.start()
        except Exception as e:
            QMessageBox.warning(None, "快捷键注册失败", f"快捷键注册失败：{e}\n你仍然可以通过托盘菜单手动截图翻译。")
    def open_capture_overlay(self):
        try:
            img = grab_full_screen_image()
            self.overlay = CaptureOverlay(img)
            self.overlay.captured.connect(self.on_image_captured)
            self.overlay.show()
        except Exception:
            QMessageBox.critical(None, "截图错误", traceback.format_exc())
    def on_image_captured(self, image, anchor):
        try:
            original, translated, direction = self.translator.process(image)
            if not original:
                self.tray.show_message(APP_NAME, "没有识别到文字。")
                return
            bubble = TranslationBubble(original, translated, direction, self.config.bubble_duration_ms, app_icon=self.tray.icon, config=self.config)
            self.bubbles.append(bubble); bubble.show_near(anchor)
        except Exception:
            QMessageBox.critical(None, "翻译错误", traceback.format_exc())
    def show_main_panel(self):
        self.main_panel.show_panel()
    def open_history(self):
        dialog = HistoryDialog(self.tray.icon); dialog.exec()
    def open_notebook(self):
        dialog = NotebookDialog(self.tray.icon); dialog.exec()
    def open_settings(self):
        dialog = SettingsDialog(self.config); dialog.config_saved.connect(self.on_config_saved); dialog.exec()
    def on_config_saved(self, config):
        self.config = config; self.translator = ScreenshotTranslator(config); self.register_hotkey(); self.tray.show_message(APP_NAME, "设置已保存。")
    def quit(self):
        SPEECH_MANAGER.stop()
        if self.listener:
            try: self.listener.stop()
            except Exception: pass
        self.app.quit()

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "当前系统不支持系统托盘。")
        sys.exit(1)
    controller = AppController(app)
    controller.start()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
