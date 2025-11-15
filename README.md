# 每日热点新闻聚合系统

一个自动抓取各大平台热点新闻并生成双语（中英文）网站的Python脚本。

## 功能特点

- 🌐 **多平台支持**: 自动抓取微博、知乎、百度、B站、贴吧、抖音、虎扑等平台的热点新闻
- 🔄 **自动更新**: 可设置定时任务，每日自动获取最新热点
- 🌍 **双语支持**: 支持中英文切换，满足不同语言用户需求
- 🌙 **主题切换**: 支持明暗主题切换，适应不同使用环境
- 📱 **响应式设计**: 适配桌面和移动设备
- 🔍 **搜索过滤**: 支持按关键词、平台、日期筛选新闻
- 📊 **数据归档**: 自动归档历史数据，保持网站整洁

## 项目结构

```
meirixinwen/
├── main.py              # 主程序文件
├── config/
│   ├── config.yaml       # 爬虫配置文件
│   └── frequency_words.txt  # 关键词过滤配置
├── data/                # 数据存储目录
├── posts/               # 每日新闻详情页
├── index.html           # 博客首页
├── about.html           # 关于页面
├── privacy.html         # 隐私政策页面
├── help.html            # 帮助页面
├── requirements.txt      # Python依赖
└── README.md           # 项目说明
```

## 安装与配置

### 1. 环境要求

- Python 3.7+
- pip包管理器

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置文件

编辑 `config/config.yaml` 文件，配置爬虫参数：

```yaml
crawler:
  timeout: 10          # 请求超时时间（秒）
  max_retries: 3       # 最大重试次数
  request_interval: 1   # 请求间隔（秒）

platforms:
  weibo:
    enabled: true       # 是否启用微博爬虫
  zhihu:
    enabled: true       # 是否启用知乎爬虫
  baidu:
    enabled: true       # 是否启用百度爬虫
  # 其他平台配置...
```

### 4. 关键词过滤

编辑 `config/frequency_words.txt` 文件，设置关键词过滤规则：

```
# 必须包含的关键词（以+开头）
+科技
+AI

# 普通关键词（直接写）
人工智能
机器学习

# 排除的关键词（以!开头）
!广告
!推广
```

## 使用方法

### 1. 手动运行

```bash
python main.py
```

### 2. 定时任务

使用cron设置定时任务（每日凌晨2点运行）：

```bash
0 2 * * * cd /path/to/meirixinwen && python main.py
```

### 3. 部署到服务器

推荐使用以下方式部署：

- **GitHub Pages**: 适合静态网站部署
- **Vercel/Netlify**: 支持自动构建和部署
- **云服务器**: 完全控制，可设置定时任务

## 功能说明

### 双语切换

- 点击页面右上角的语言切换按钮（中/EN）可在中英文之间切换
- 系统会记住用户选择，下次访问时自动应用
- 支持跨页面语言同步

### 主题切换

- 点击月亮/太阳图标可切换明暗主题
- 支持系统主题偏好检测
- 用户选择会保存在本地存储中

### 搜索和过滤

- **关键词搜索**: 在搜索框输入关键词，实时过滤新闻
- **平台筛选**: 选择特定平台查看该平台的热点
- **日期筛选**: 选择特定日期查看历史热点

## 数据结构

每条新闻包含以下字段：

```json
{
  "title": "新闻标题",
  "title_en": "News Title",
  "url": "新闻链接",
  "platform": "平台名称",
  "platform_en": "Platform Name",
  "image_url": "图片链接",
  "hot_value": "热度值"
}
```

## 自定义开发

### 添加新平台

1. 在 `main.py` 中添加新的爬取函数：

```python
def fetch_newplatform_hot() -> List[Dict]:
    """获取新平台热搜榜前10条"""
    # 实现爬取逻辑
    return news_list
```

2. 在 `fetch_news()` 函数中调用新函数：

```python
if platform_id == "newplatform":
    newplatform_news = fetch_newplatform_hot()
    if newplatform_news:
        news.extend(newplatform_news)
```

3. 在 `config.yaml` 中添加平台配置：

```yaml
platforms:
  newplatform:
    enabled: true
```

### 自定义翻译

扩展 `TRANSLATION_MAP` 字典添加更多翻译：

```python
TRANSLATION_MAP = {
    "新平台": "New Platform",
    # 添加更多翻译...
}
```

## 注意事项

1. **遵守robots.txt**: 请确保遵守各平台的robots.txt规则
2. **请求频率**: 避免过于频繁的请求，以免被反爬虫机制封禁
3. **数据准确性**: 热点数据仅供参考，请以官方信息为准
4. **法律合规**: 确保使用符合当地法律法规

## 故障排除

### 常见问题

1. **爬取失败**: 检查网络连接和配置文件
2. **翻译不显示**: 确保JavaScript正常加载
3. **样式异常**: 检查Tailwind CSS是否正常加载

### 日志查看

程序运行时会输出详细日志，可用于问题诊断：

```
=== 每日热点新闻聚合系统 ===
开始运行: 2025-01-01 08:00:00
加载配置: 必须词 2 个, 关键词 5 个, 排除词 3 个
获取 weibo 新闻...
获取 zhihu 新闻...
共获取到 70 条原始新闻
过滤后得到 50 条新闻
博客更新完成
```

## 贡献指南

欢迎提交Issue和Pull Request来改进项目：

1. Fork本项目
2. 创建功能分支
3. 提交更改
4. 发起Pull Request

## 许可证

本项目采用MIT许可证，详见LICENSE文件。

## 更新日志

### v2.0.0 (2025-01-14)
- ✨ 新增中英文双语切换功能
- ✨ 新增明暗主题切换
- 🐛 修复爬虫稳定性问题
- 📱 优化移动端显示效果

### v1.0.0 (2025-10-17)
- 🎉 初始版本发布
- 📰 支持多平台热点新闻聚合
- 🔍 支持搜索和过滤功能

## 联系方式

如有问题或建议，请通过以下方式联系：

- 提交Issue: [GitHub Issues](https://github.com/yourusername/meirixinwen/issues)
- 邮箱: your.email@example.com

---

**感谢使用每日热点新闻聚合系统！** 🎉