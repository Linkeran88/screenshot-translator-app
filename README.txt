截图翻译 Screenshot Translator v26 - 离线翻译增强版

主要功能：
- 框选截图翻译
- Tesseract OCR 本地识别
- Google / DeepL / Microsoft / OpenAI / 自定义 API 翻译源
- 新增 Argos 本地离线翻译渠道
- 语音朗读、翻译历史、记事本摘录
- 修复 pip 走 127.0.0.1:7897 代理导致依赖安装失败的问题

普通启动：
1. 双击 run_windows.bat
2. 按 Ctrl + Shift + X 截图翻译

如果出现 127.0.0.1:7897 或 proxy 连接失败：
1. 先双击 proxy_fix.bat
2. 再双击 run_windows.bat

启用本地离线翻译：
1. 先双击 run_windows.bat，确保基础 App 可以打开
2. 关闭 App
3. 双击 install_offline_translation.bat
4. 等待安装 Argos Translate 和中英离线模型
5. 重新打开 App
6. 打开 设置中心 -> 翻译服务 -> 选择 Argos 本地离线翻译

说明：
- OCR 和语音朗读本身可以离线使用。
- Argos 模型安装成功后，中英翻译可以离线使用。
- 第一次安装 Argos 和语言模型仍然需要网络；安装完成后可以断网使用。
- 如果自动下载模型失败，可以手动下载 .argosmodel 文件，然后拖到 install_argos_model_file.bat 上安装。
