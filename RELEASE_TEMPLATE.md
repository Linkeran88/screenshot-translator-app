# Screenshot Translator v1.0.0

## 版本简介

这是截图翻译桌面 App 的首个公开版本，支持截图 OCR、在线翻译、语音朗读、翻译历史和记事本摘录。

## 核心功能

- 全局快捷键截图翻译
- OCR 文字识别
- 多翻译源配置
- 语音朗读与语音选择
- 翻译历史搜索
- 记事本摘录和导出
- 深色毛玻璃界面
- 可调整译文 / 原文区域大小
- 可打包为 Windows exe

## 安装说明

1. 安装 Python 3.10+
2. 安装 Tesseract OCR
3. 下载项目后运行：

```bat
run_windows.bat
```

## 打包说明

```bat
build_windows.bat
```

生成文件位于：

```text
dist\ScreenshotTranslator.exe
```

## 注意事项

- 在线翻译需要联网。
- 第三方翻译 API 需要自行配置 API Key。
- 请勿将 API Key 上传到公开仓库。
