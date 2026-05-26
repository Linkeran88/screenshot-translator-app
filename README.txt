截图翻译桌面端 App v22

新增：翻译源渠道选择 / API 配置

支持的翻译源：
- Google 免费源：默认，无需配置 API Key
- DeepL API：需要 DeepL API Key
- Microsoft Translator API：需要 Azure Translator Key 和 Region
- OpenAI API：需要 OpenAI API Key，可配置模型和接口 URL
- 自定义 API：可配置 URL 和 Bearer Token

自定义 API 请求格式：
POST JSON:
{
  "text": "要翻译的文本",
  "source": "en",
  "target": "zh-CN"
}

自定义 API 返回格式支持任意一个字段：
{
  "translation": "译文"
}
或 result / text / translated 字段。

使用：
1. 解压本包
2. 双击 run_windows.bat
3. 打开设置中心，选择翻译服务并填写对应 API 信息
4. 按 Ctrl+Shift+X 截图翻译

说明：
- Google 免费源仍然作为默认方案。
- DeepL / Microsoft / OpenAI / 自定义 API 需要联网和对应 API 权限。
- v22 保留 v20 的中文界面、OCR 增强、历史记录、记事本、语音朗读和导出功能。


Updated in v24:
- Replaced application icon with selected icon option #2 (light glassmorphism style).


v25 更新：
- 翻译页支持右下角拖拽缩放整个窗口。
- 译文/原文中间分隔条变得更大、更明显，支持拖拽调整两个文本区域大小。
- 默认翻译窗口尺寸增大，长文本查看更舒服。
