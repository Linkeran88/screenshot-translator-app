# GitHub 上传教程

本文档教你把「截图翻译 Screenshot Translator」上传到 GitHub。

## 上传前检查

上传前建议确认项目目录里至少包含这些文件：

```text
screenshot_translator_app.py
requirements.txt
run_windows.bat
run_windows_debug.bat
build_windows.bat
app_icon.png
app_icon.ico
README.md
.gitignore
```

不要上传这些内容：

```text
__pycache__/
build/
dist/
*.spec
*.pyc
本地配置文件
API Key
Token
密码
```

## 方法一：网页上传，适合新手

### 1. 创建 GitHub 仓库

1. 登录 GitHub。
2. 点击右上角 `+`。
3. 选择 `New repository`。
4. 填写仓库名，例如：

```text
screenshot-translator-app
```

5. 推荐选择 `Public` 或 `Private`。
6. 可以先不要勾选 `Add a README file`，因为项目里已经有 `README.md`。
7. 点击 `Create repository`。

### 2. 上传项目文件

1. 进入刚创建的仓库。
2. 点击 `Add file`。
3. 点击 `Upload files`。
4. 把项目文件拖进去。
5. 填写提交说明，例如：

```text
Initial release: screenshot translator desktop app
```

6. 点击 `Commit changes`。

### 3. 推荐上传方式

如果文件较少，可以直接网页上传。

如果项目文件较多，或者以后要持续更新，推荐使用 Git 命令行上传。

## 方法二：Git 命令行上传，推荐长期维护使用

### 1. 安装 Git

先安装 Git：

```text
https://git-scm.com/downloads
```

安装完成后，在项目目录右键打开终端，或者打开 Git Bash。

### 2. 初始化仓库

进入项目目录：

```bat
cd 你的项目目录
```

初始化 Git：

```bash
git init
```

### 3. 添加文件

```bash
git add .
```

### 4. 提交代码

```bash
git commit -m "Initial release: screenshot translator desktop app"
```

### 5. 关联 GitHub 远程仓库

把下面地址替换成你的 GitHub 仓库地址：

```bash
git remote add origin https://github.com/你的用户名/screenshot-translator-app.git
```

### 6. 设置主分支并推送

```bash
git branch -M main
git push -u origin main
```

## 后续更新代码

每次修改代码后，执行：

```bash
git status
git add .
git commit -m "Update app features"
git push
```

## 推荐的提交信息

```text
Initial release: screenshot translator desktop app
Add OCR enhancement settings
Add translation history and notebook
Fix dark theme dropdown style
Update app icon
Improve resizable translation window
```

## GitHub Release 发布方式

如果你已经打包出 `.exe`，可以通过 Release 发布：

1. 打开 GitHub 仓库。
2. 进入 `Releases`。
3. 点击 `Draft a new release`。
4. 新建标签，例如：

```text
v1.0.0
```

5. Release 标题可以写：

```text
Screenshot Translator v1.0.0
```

6. 上传打包好的：

```text
ScreenshotTranslator.exe
```

7. 点击 `Publish release`。

## Release 文案示例

```md
# Screenshot Translator v1.0.0

首个公开版本。

## 功能

- 截图翻译
- OCR 文字识别
- 多翻译源配置
- 语音朗读
- 翻译历史搜索
- 记事本摘录
- 深色毛玻璃 UI
- Windows exe 打包

## 使用

下载 `ScreenshotTranslator.exe` 后双击运行。

首次使用前请安装 Tesseract OCR。
```

## 安全提醒

上传 GitHub 前请检查：

- 不要上传 OpenAI API Key
- 不要上传 DeepL API Key
- 不要上传 Microsoft Translator Key
- 不要上传任何 `.env` 文件
- 不要上传本地生成的配置文件

如果不确定，可以先运行：

```bash
git status
```

查看将要提交哪些文件。
