import os
import json
import yaml
import time
import random
import logging
import requests
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union, Any

import pytz
from typing import Dict, List, Set, Tuple
from datetime import datetime, timedelta
from urllib.parse import quote
from pathlib import Path

# 配置常量
CONFIG_PATH = "config/config.yaml"
FREQ_WORDS_PATH = "config/frequency_words.txt"
BLOG_DATA_PATH = "blog_data.json"
POSTS_DIR = "posts"
INDEX_HTML_PATH = "index.html"

# 确保必要目录存在
Path(POSTS_DIR).mkdir(exist_ok=True)

# 全局配置缓存（供 HTTP 请求读取参数）
GLOBAL_CFG: Dict = {}

def get_crawler_settings() -> Tuple[int, int]:
    """从配置中读取爬虫的超时与重试次数
    小白解释：这里把“请求超时时间”和“重试次数”读出来，给下面的网络请求用。这样如果网络波动，程序就更稳。
    """
    cfg = GLOBAL_CFG or {}
    crawler = (cfg.get('crawler') or {})
    timeout = int(crawler.get('timeout', 10))
    max_retries = int(crawler.get('max_retries', 3))
    return timeout, max_retries

def http_get(url: str, headers: Optional[Dict[str, str]] = None) -> requests.Response:
    """带自动重试的 HTTP GET 请求封装
    小白解释：请求网页时，可能会失败。这段代码会自动试几次，每次稍微等一下，再试，尽量确保能拿到数据。
    """
    timeout, max_retries = get_crawler_settings()
    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            session = requests.Session()
            session.trust_env = False  # 禁用系统代理，避免环境代理影响
            resp = session.get(url, headers=headers or {}, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:
            last_err = e
            # 简单退避策略：下一次等待时间更长一些
            wait_seconds = 0.8 * (attempt + 1)
            time.sleep(wait_seconds)
    raise RuntimeError(f"请求失败(重试{max_retries}次): {url} - {last_err}")

def get_beijing_time() -> datetime:
    """获取北京时区当前时间"""
    beijing_tz = pytz.timezone('Asia/Shanghai')
    return datetime.now(beijing_tz)

def load_config() -> Dict:
    """加载配置文件"""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"加载配置文件失败: {e}")
        return {}

def load_frequency_words() -> Tuple[List[str], List[str], List[str]]:
    """加载频率词配置"""
    required = []
    keywords = []
    exclude = []
    
    if not os.path.exists(FREQ_WORDS_PATH):
        return required, keywords, exclude
        
    try:
        with open(FREQ_WORDS_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('+'):
                    required.append(line[1:].strip())
                elif line.startswith('!'):
                    exclude.append(line[1:].strip())
                else:
                    keywords.append(line)
    except Exception as e:
        print(f"加载频率词文件失败: {e}")
        
    return required, keywords, exclude

def fetch_weibo_hot() -> List[Dict]:
    """获取微博热搜榜前10条"""
    try:
        url = "https://weibo.com/ajax/side/hotSearch"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://weibo.com/',
            'Cookie': 'SUB=_2AkMSLwF9f8NxqwJRmP0dyGjhaoxwzwDEieKjKM4uJRMxHRl-yj9jqmtbtRB6PDkJ9w8OaqJAbsgjdEWtIcilcZxHG7rw'
        }
        response = http_get(url, headers=headers)
        data = response.json()
        
        news_list = []
        # 只取前10条
        for item in data.get('data', {}).get('realtime', [])[:10]:
            # 获取微博热搜详情页
            detail_url = f"https://s.weibo.com/weibo?q={quote(item.get('word', ''))}"
            try:
                detail_response = http_get(detail_url, headers=headers)
                # 使用正则表达式提取图片URL
                import re
                img_urls = re.findall(r'src="(https://wx\d\.sinaimg\.cn/[^"]+)"', detail_response.text)
                img_url = img_urls[0] if img_urls else ''
            except Exception as e:
                print(f"获取微博热搜图片失败: {e}")
                img_url = ''
            
            hot_value = str(item.get('raw_hot') or item.get('num') or item.get('hot') or '').strip()
            news_list.append({
                'title': item.get('word', ''),
                'url': detail_url,
                'platform': '微博',
                'image_url': img_url,
                'hot_value': hot_value
            })
            time.sleep(1)  # 添加延迟避免请求过快
        return news_list
    except Exception as e:
        print(f"获取微博热搜失败: {e}")
        return []

def fetch_zhihu_hot() -> List[Dict]:
    """获取知乎热榜前10条"""
    try:
        url = "https://api.zhihu.com/topstory/hot-list"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.zhihu.com/hot',
            'x-api-version': '3.0.91',
            'x-app-za': 'OS=Web',
            'Cookie': '_zap=8b0a6869-a1f4-4bdf-9c83-e1e3a5e29e96; d_c0="AHBXHQPqTBWPTqwf1GgVE8WgX4pVXEHCQxw=|1634483427"; _xsrf=c8b7b8b8-8b0a-4b0f-9c83-e1e3a5e29e96'
        }
        response = http_get(url, headers=headers)
        data = response.json()
        
        news_list = []
        # 只取前10条
        for item in data.get('data', [])[:10]:
            target = item.get('target', {})
            title = target.get('title', '')
            url = target.get('url', '')
            # 获取知乎问题的封面图
            image_url = target.get('image_url', '') or target.get('thumbnail', '')
            if title and url:
                metrics_area = target.get('metrics_area', {})
                if isinstance(metrics_area, dict):
                    metrics_text = metrics_area.get('text', '')
                else:
                    metrics_text = str(metrics_area) if metrics_area else ''
                hot_value = str(item.get('detail_text') or metrics_text or target.get('metrics_text', '') or '').strip()
                news_list.append({
                    'title': title,
                    'url': url,
                    'platform': '知乎',
                    'image_url': image_url,
                    'hot_value': hot_value
                })
        return news_list
    except Exception as e:
        print(f"获取知乎热榜失败: {e}")
        return []

def fetch_bilibili_hot() -> List[Dict]:
    """获取B站热搜榜前10条"""
    try:
        url = "https://api.bilibili.com/x/web-interface/search/square?limit=10"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.bilibili.com/',
            'Cookie': "buvid3=2B1E4817-E425-4C36-87BE-C857EA8DD5CF185003infoc; b_nut=1697509762; i-wanna-go-back=-1; b_ut=7; _uuid=6C2310F99-C106D-84B9-FF65-C3BC376364C185004infoc; buvid4=AB4D8751-2D8A-BAA2-7504-DE584D7DF63E85004-023101613-; DedeUserID=3493279343885079; DedeUserID__ckMd5=60d7119ef6a59181"
        }
        response = http_get(url, headers=headers)
        data = response.json()
        
        news_list = []
        trending_list = data.get('data', {}).get('trending', {}).get('list', [])
        # 只取前10条
        for idx, item in enumerate(trending_list[:10]):
            keyword = item.get('keyword', '')
            # 获取B站搜索结果的第一个视频封面
            search_url = f"https://api.bilibili.com/x/web-interface/search/type?keyword={quote(keyword)}&search_type=video"
            try:
                search_response = http_get(search_url, headers=headers)
                search_data = search_response.json()
                first_video = search_data.get('data', {}).get('result', [{}])[0]
                image_url = first_video.get('pic', '')
            except Exception as e:
                print(f"获取B站视频封面失败: {e}")
                image_url = ''
            hot_value = str(item.get('hot_id') or item.get('hot_score') or '').strip() or f"TOP{idx+1}"
            
            news_list.append({
                'title': keyword,
                'url': f"https://search.bilibili.com/all?keyword={quote(keyword)}",
                'platform': 'B站',
                'image_url': image_url,
                'hot_value': hot_value
            })
            time.sleep(1)  # 添加延迟避免请求过快
        return news_list
    except Exception as e:
        print(f"获取B站热搜失败: {e}")
        return []

def fetch_baidu_hot() -> List[Dict]:
    """获取百度热搜榜前10条"""
    try:
        url = "https://top.baidu.com/api/board?platform=wise&tab=realtime"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://top.baidu.com/board?tab=realtime',
        }
        response = http_get(url, headers=headers)
        data = response.json()
        
        news_list = []
        # 只取前10条
        for item in data.get('data', {}).get('cards', [{}])[0].get('content', [])[:10]:
            hot_value = str(item.get('hotScore') or item.get('hot_score') or item.get('heatScore') or '').strip()
            news_list.append({
                'title': item.get('query', ''),
                'url': f"https://www.baidu.com/s?wd={quote(item.get('query', ''))}",
                'platform': '百度',
                'hot_value': hot_value
            })
        return news_list
    except Exception as e:
        print(f"获取百度热搜失败: {e}")
        return []



def fetch_tieba_hot() -> List[Dict]:
    """获取贴吧热搜榜前10条"""
    try:
        url = "https://tieba.baidu.com/hottopic/browse/topicList"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://tieba.baidu.com/hottopic/browse/topicList',
        }
        response = http_get(url, headers=headers)
        data = response.json()
        
        news_list = []
        # 只取前10条
        for item in data.get('data', {}).get('bang_topic', {}).get('topic_list', [])[:10]:
            hot_value = str(item.get('discuss_num') or item.get('discuss_count') or '').strip()
            news_list.append({
                'title': item.get('topic_name', ''),
                'url': item.get('topic_url', f"https://tieba.baidu.com/hottopic"),
                'platform': '贴吧',
                'hot_value': hot_value
            })
        return news_list
    except Exception as e:
        print(f"获取贴吧热搜失败: {e}")
        return []

def fetch_douyin_hot() -> List[Dict]:
    """获取抖音热搜榜前10条"""
    try:
        url = "https://www.douyin.com/aweme/v1/web/hot/search/list/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.douyin.com/',
            'Cookie': 'douyin.com; ttwid=1%7CuU0ZIsyDyN7j3H9Yl0-hh4eNB1oXC-DGBKDZhKoqbVY%7C1697509762%7C1d87722dd4c6e9470e872833c2df88c8f4c669b37ff893d0e3da9aa083a1d43d; passport_csrf_token=cdb9b4d3990db4a34e8b0c67d2db1f75;'
        }
        response = http_get(url, headers=headers)
        data = response.json()
        
        news_list = []
        # 只取前10条
        for item in data.get('data', {}).get('word_list', [])[:10]:
            hot_value = str(item.get('hot_value') or item.get('hot') or '').strip()
            news_list.append({
                'title': item.get('word', ''),
                'url': f"https://www.douyin.com/search/{quote(item.get('word', ''))}",
                'platform': '抖音',
                'hot_value': hot_value
            })
        return news_list
    except Exception as e:
        print(f"获取抖音热搜失败: {e}")
        return []

def fetch_hupu_hot() -> List[Dict]:
    """获取虎扑热搜榜前10条"""
    try:
        url = "https://bbs.hupu.com/api/v1/index/topics"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://bbs.hupu.com/',
            'Cookie': '_dacevid3=b8d6b3b3.b3b3.b3b3.b3b3.b3b3b3b3b3b3; _cnzz_CV1256378648=is-logon%7Clogged-out%7C1697509762'
        }
        response = http_get(url, headers=headers)
        data = response.json()
        
        news_list = []
        # 只取前10条
        for item in data.get('data', {}).get('topics', [])[:10]:
            hot_value = str(item.get('replies') or item.get('reply_count') or item.get('replies_count') or item.get('light_reply') or '').strip()
            news_list.append({
                'title': item.get('title', ''),
                'url': f"https://bbs.hupu.com{item.get('url', '')}",
                'platform': '虎扑',
                'hot_value': hot_value
            })
        return news_list
    except Exception as e:
        print(f"获取虎扑热搜失败: {e}")
        return []

def fetch_news(config: Dict) -> List[Dict]:
    """从各平台直接获取新闻数据"""
    news = []
    platforms = config.get('platforms', {})
    request_interval = config.get('crawler', {}).get('request_interval', 1)
    
    for platform_id, platform_config in platforms.items():
        try:
            if not platform_config.get('enabled', False):
                continue
                
            print(f"获取 {platform_id} 新闻...")
            
            # 直接从各平台获取数据
            if platform_id == "weibo":
                weibo_news = fetch_weibo_hot()
                if weibo_news:
                    news.extend(weibo_news)
            elif platform_id == "baidu":
                baidu_news = fetch_baidu_hot()
                if baidu_news:
                    news.extend(baidu_news)
            elif platform_id == "zhihu":
                zhihu_news = fetch_zhihu_hot()
                if zhihu_news:
                    news.extend(zhihu_news)
            elif platform_id == "bilibili":
                bilibili_news = fetch_bilibili_hot()
                if bilibili_news:
                    news.extend(bilibili_news)
            elif platform_id == "tieba":
                tieba_news = fetch_tieba_hot()
                if tieba_news:
                    news.extend(tieba_news)
            elif platform_id == "douyin":
                douyin_news = fetch_douyin_hot()
                if douyin_news:
                    news.extend(douyin_news)
            
            time.sleep(request_interval)
        except Exception as e:
            print(f"获取 {platform_id} 新闻失败: {e}")
    
    return news

def filter_news(news: List[Dict], required: List[str], keywords: List[str], exclude: List[str]) -> List[Dict]:
    """过滤新闻内容"""
    filtered = []
    
    for item in news:
        title = item.get('title', '').lower()
        
        # 检查排除词
        if any(word.lower() in title for word in exclude):
            continue
            
        # 检查必须包含的词
        if required and not all(word.lower() in title for word in required):
            continue
            
        # 如果没有设置关键词，保留所有非排除词的新闻
        if not keywords:
            filtered.append(item)
            continue
            
        # 如果设置了关键词，只要匹配任一关键词就保留
        if any(word.lower() in title for word in keywords):
            filtered.append(item)
    
    # 如果过滤后的新闻少于10条，放宽过滤条件
    if len(filtered) < 10:
        # 重新过滤，这次只检查排除词
        filtered = []
        for item in news:
            title = item.get('title', '').lower()
            if not any(word.lower() in title for word in exclude):
                filtered.append(item)
            if len(filtered) >= 20:  # 最多保留20条
                break
    
    return filtered

def group_news_by_keywords(news: List[Dict], keywords: List[str]) -> List[Dict]:
    """按关键词分组新闻"""
    groups = []
    used_news = set()  # 用于跟踪已分组的新闻
    
    # 先按关键词分组
    for word in keywords:
        word_news = []
        for item in news:
            title = item.get('title', '').lower()
            item_id = f"{item.get('platform', '')}_{title}"  # 创建唯一标识
            if word.lower() in title and item_id not in used_news:
                word_news.append(item)
                used_news.add(item_id)
        if word_news:
            groups.append({
                'word': word,
                'news': word_news,
                'count': len(word_news)
            })
    
    # 添加未匹配关键词的新闻
    other_news = []
    for item in news:
        title = item.get('title', '').lower()
        item_id = f"{item.get('platform', '')}_{title}"
        if item_id not in used_news:
            other_news.append(item)
    
    if other_news:
        groups.append({
            'word': '其他热点',
            'news': other_news,
            'count': len(other_news)
        })
    
    # 如果没有任何分组，将所有新闻放在"热点新闻"组
    if not groups:
        groups.append({
            'word': '热点新闻',
            'news': news,
            'count': len(news)
        })
    
    # 按新闻数量排序
    return sorted(groups, key=lambda x: x['count'], reverse=True)

def render_index_html(news_by_date: Dict[str, List[Dict]], config: Dict) -> str:
    """渲染主页HTML"""
    template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <link rel="icon" href="favicon.ico" type="image/x-icon" />
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>每日热点聚合 - 热点新闻分析</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <style>
        .search-highlight { background-color: #fde68a; }
        .platform-weibo { border-left-color: #ff8200; }
        .platform-baidu { border-left-color: #2932e1; }
        .platform-zhihu { border-left-color: #0066ff; }
        .platform-bilibili { border-left-color: #fb7299; }
        .platform-tieba { border-left-color: #2932e1; }
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    <div class="container mx-auto px-4 py-8">
        <header class="mb-8">
            <h1 class="text-4xl font-bold text-gray-800 mb-4">每日热点聚合</h1>
            <div class="flex flex-wrap gap-4 items-center">
                <div class="flex-1">
                    <input type="text" id="searchInput" 
                           placeholder="搜索热点内容..." 
                           class="w-full px-4 py-2 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500">
                </div>
                <div class="flex gap-2">
                    <select id="platformFilter" class="px-4 py-2 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <option value="">全部平台</option>
                        <option value="微博热搜">微博热搜</option>
                        <option value="百度热搜">百度热搜</option>
                        <option value="知乎热榜">知乎热榜</option>
                    </select>
                    <select id="dateFilter" class="px-4 py-2 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <option value="">全部日期</option>
                    </select>
                </div>
            </div>
        </header>
        
        <main id="newsContainer">
"""
    
    # 添加新闻内容
    dates = sorted(news_by_date.keys(), reverse=True)
    current_page = dates[:10]  # 每页显示10天的数据
    
    for date in current_page:
        date_news = news_by_date[date]
        if not date_news:
            continue
            
        template += f"""
            <section class="mb-8" data-date="{date}">
                <h2 class="text-2xl font-semibold text-gray-700 mb-4">{date}</h2>
                <div class="grid gap-4">
"""
        
        for item in date_news:
            platform = item.get('platform', '')
            platform_class = f"platform-{platform.lower().split('热')[0]}"
            
            template += f"""
                    <article class="bg-white rounded-lg shadow-sm p-4 border-l-4 {platform_class} hover:shadow-md transition-shadow duration-200" 
                             data-platform="{platform}">
                        <div class="flex items-start justify-between">
                            <h3 class="text-lg font-medium flex-1">
                                <a href="{item['url']}" target="_blank" class="text-gray-800 hover:text-blue-600 transition-colors duration-200">
                                    {item['title']}
                                </a>
                            </h3>
                            <span class="text-sm text-gray-500 ml-4">{platform}</span>
                        </div>
                    </article>
"""
        
        template += """
                </div>
            </section>
"""
    
    # 添加分页控件
    if len(dates) > 10:
        template += """
            <div class="flex justify-center gap-2 mt-8">
                <button id="prevPage" class="px-4 py-2 rounded-lg bg-blue-500 text-white disabled:bg-gray-300 disabled:cursor-not-allowed">
                    上一页
                </button>
                <span id="pageInfo" class="px-4 py-2">第 1 页</span>
                <button id="nextPage" class="px-4 py-2 rounded-lg bg-blue-500 text-white disabled:bg-gray-300 disabled:cursor-not-allowed">
                    下一页
                </button>
            </div>
"""
    
    # 添加页面底部
    template += """
        </main>
    </div>
    
    <script>
        // 搜索和筛选功能
        const searchInput = document.getElementById('searchInput');
        const platformFilter = document.getElementById('platformFilter');
        const dateFilter = document.getElementById('dateFilter');
        const newsContainer = document.getElementById('newsContainer');
        
        // 初始化日期选项
        const dates = Array.from(document.querySelectorAll('section[data-date]')).map(
            section => section.dataset.date
        );
        dates.forEach(date => {
            const option = document.createElement('option');
            option.value = date;
            option.textContent = date;
            dateFilter.appendChild(option);
        });
        
        // 搜索和筛选处理函数
        function filterNews() {
            const searchText = searchInput.value.toLowerCase();
            const selectedPlatform = platformFilter.value;
            const selectedDate = dateFilter.value;
            
            document.querySelectorAll('section[data-date]').forEach(section => {
                const sectionDate = section.dataset.date;
                const shouldShowSection = !selectedDate || selectedDate === sectionDate;
                let hasVisibleNews = false;
                
                section.querySelectorAll('article').forEach(article => {
                    const title = article.querySelector('h3').textContent.toLowerCase();
                    const platform = article.dataset.platform;
                    
                    const matchesSearch = !searchText || title.includes(searchText);
                    const matchesPlatform = !selectedPlatform || platform === selectedPlatform;
                    const matchesDate = !selectedDate || sectionDate === selectedDate;
                    
                    if (matchesSearch && matchesPlatform && matchesDate) {
                        article.style.display = '';
                        hasVisibleNews = true;
                        
                        // 高亮搜索结果
                        if (searchText) {
                            const titleElement = article.querySelector('h3 a');
                            const originalText = titleElement.textContent;
                            const highlightedText = originalText.replace(
                                new RegExp(searchText, 'gi'),
                                match => `<span class="search-highlight">${match}</span>`
                            );
                            titleElement.innerHTML = highlightedText;
                        }
                    } else {
                        article.style.display = 'none';
                    }
                });
                
                section.style.display = shouldShowSection && hasVisibleNews ? '' : 'none';
            });
        }
        
        // 添加事件监听器
        searchInput.addEventListener('input', filterNews);
        platformFilter.addEventListener('change', filterNews);
        dateFilter.addEventListener('change', filterNews);
        
        // 分页功能
        let currentPage = 1;
        const itemsPerPage = 10;
        const sections = Array.from(document.querySelectorAll('section[data-date]'));
        const totalPages = Math.ceil(sections.length / itemsPerPage);
        
        const prevPageBtn = document.getElementById('prevPage');
        const nextPageBtn = document.getElementById('nextPage');
        const pageInfo = document.getElementById('pageInfo');
        
        function updatePagination() {
            const start = (currentPage - 1) * itemsPerPage;
            const end = start + itemsPerPage;
            
            sections.forEach((section, index) => {
                section.style.display = (index >= start && index < end) ? '' : 'none';
            });
            
            prevPageBtn.disabled = currentPage === 1;
            nextPageBtn.disabled = currentPage === totalPages;
            pageInfo.textContent = `第 ${currentPage} 页`;
        }
        
        if (prevPageBtn && nextPageBtn) {
            prevPageBtn.addEventListener('click', () => {
                if (currentPage > 1) {
                    currentPage--;
                    updatePagination();
                }
            });
            
            nextPageBtn.addEventListener('click', () => {
                if (currentPage < totalPages) {
                    currentPage++;
                    updatePagination();
                }
            });
            
            updatePagination();
        }
    </script>
</body>
</html>
"""
    return template

def render_daily_post_html(news_entry: Dict) -> str:
    """渲染每日详情页HTML"""
    news_list = news_entry.get('news', [])
    update_time = news_entry.get('update_time', '')
    
    # 处理日期，如果update_time为空，使用当前日期
    try:
        date = update_time.split()[0] if update_time else datetime.now().strftime('%Y-%m-%d')
    except (AttributeError, IndexError):
        date = datetime.now().strftime('%Y-%m-%d')
    
    # 按平台分组新闻
    news_by_platform = {}
    for news in news_list:
        platform = news.get('platform', '其他')
        if platform not in news_by_platform:
            news_by_platform[platform] = []
        news_by_platform[platform].append(news)
    
    # 计算布局
    platform_count = len(news_by_platform)
    if platform_count <= 2:
        grid_cols = "grid-cols-2"
    elif platform_count <= 4:
        grid_cols = "grid-cols-2 lg:grid-cols-4"
    else:
        grid_cols = "grid-cols-2 lg:grid-cols-3"
    
    # 生成HTML
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <link rel="icon" href="../favicon.ico" type="image/x-icon" />
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{date} 热点新闻 - 每日热点新闻聚合</title>
    <meta name="robots" content="index,follow" />
    <meta name="googlebot" content="index,follow" />
    <meta name="baiduspider" content="index,follow" />
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/font-awesome@4.7.0/css/font-awesome.min.css" rel="stylesheet">
    
    <style>
        body {{
            font-family: 'Noto Sans SC', sans-serif;
            scroll-behavior: smooth;
        }}
        html {{
            scroll-behavior: smooth;
        }}
    </style>
</head>
<body class="bg-neutral-100 min-h-screen">
    <!-- 导航栏 -->
    <header class="sticky top-0 bg-white/90 backdrop-blur-sm shadow-sm z-50">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-between items-center h-16">
                <div class="flex items-center space-x-8">
                    <a href="../index.html" class="flex items-center text-neutral-500 hover:text-primary transition-colors">
                        <i class="fa fa-arrow-left mr-2"></i>
                        <span>返回首页</span>
                    </a>
                    <div class="flex items-center">
                        <i class="fa fa-newspaper-o text-primary text-2xl mr-2"></i>
                        <span class="text-xl font-bold text-neutral-700">热点聚合</span>
                    </div>
                </div>
            </div>
        </div>
    </header>

    <!-- 主要内容区 -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <!-- 页面标题 -->
        <div class="bg-white rounded-xl shadow-sm p-8 mb-10">
            <h1 class="text-3xl md:text-4xl font-bold text-neutral-700 mb-4">
                {date} 热点新闻汇总
            </h1>
            <div class="flex items-center text-neutral-500">
                <i class="fa fa-clock-o mr-2"></i>
                <span>更新时间：{update_time or date}</span>
            </div>
            <p class="text-sm text-neutral-400 mt-3">
                
            </p>
        </div>

        <!-- 新闻列表 -->
        <div class="grid {grid_cols} gap-6">"""
    
    # 生成每个平台的新闻列表
    for platform, platform_news in news_by_platform.items():
        platform_color = {
            '微博': 'red',
            '知乎': 'blue',
            '百度': 'green',
            'B站': 'pink',
            '贴吧': 'purple',
            '抖音': 'gray'
        }.get(platform, 'blue')
        
        html += f"""
            <div class="bg-white rounded-xl shadow-sm p-6">
                <div class="flex items-center mb-4">
                    <h3 class="text-xl font-bold text-neutral-700">{platform}</h3>
                    <span class="ml-3 px-2.5 py-0.5 bg-{platform_color}-100 text-{platform_color}-600 text-sm rounded-full">
                        {len(platform_news)}条
                    </span>
                </div>
                <ul class="space-y-3 divide-y divide-neutral-200">"""
        
        for news in platform_news:
            title = news.get('title', '')
            url = news.get('url', '#')
            hot_value = str(news.get('hot_value', '')).strip()
            # 小白解释：有些平台没有提供“热度”数值，如果为空就不要显示“热度：”这行，避免看起来像是丢数据
            hot_line = f"""<p class="text-sm text-neutral-500 mt-1">热度：{hot_value}</p>""" if hot_value else ""
            
            html += f"""
                    <li class="pt-3">
                        <a href="{url}"
                           target="_blank"
                           class="group flex items-start hover:bg-neutral-50 p-2 rounded-lg transition-colors">
                            <span class="flex-shrink-0 w-8 h-8 bg-{platform_color}-100 rounded-full flex items-center justify-center text-{platform_color}-600">
                                <i class="fa fa-fire"></i>
                            </span>
                            <div class="ml-4 flex-1">
                                <p class="text-neutral-700 group-hover:text-{platform_color}-600 transition-colors">
                                    {title}
                                </p>
                                {hot_line}
                            </div>
                        </a>
                    </li>"""
        
        html += """
                </ul>
            </div>"""
    
    html += """
        </div>
    </main>

    <!-- 页脚 -->
    <footer class="bg-white mt-12 py-8">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="text-center text-neutral-500">
                <p>© 2025 每日热点新闻聚合 | 
                <a href="https://zxnve.dpdns.org" target="_blank" class="text-blue-400 hover:text-blue-300 transition-colors">
                   导航站主页
                </a>
                </p>
                <p class="mt-2">本网站内容仅记录热搜，不代表任何立场</p>
            </div>
        </div>
    </footer>
</body>
</html>"""
    
    return html

def render_blog_html(blog_entries: List[Dict], blog_config: Dict) -> str:
    """生成博客首页HTML"""
    html = '''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <link rel="icon" href="favicon.ico" type="image/x-icon" />
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>每日热点新闻聚合</title>
        <meta name="robots" content="index,follow" />
        <meta name="googlebot" content="index,follow" />
        <meta name="baiduspider" content="index,follow" />
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
        <link href="https://cdn.jsdelivr.net/npm/font-awesome@4.7.0/css/font-awesome.min.css" rel="stylesheet">
        
        <!-- 配置Tailwind自定义颜色和字体 -->
        <script>
            tailwind.config = {
                theme: {
                    extend: {
                        colors: {
                            primary: '#165DFF',
                            secondary: '#FF7D00',
                            neutral: {
                                100: '#F5F7FA',
                                200: '#E5E6EB',
                                300: '#C9CDD4',
                                400: '#86909C',
                                500: '#4E5969',
                                600: '#272E3B',
                                700: '#1D2129',
                            }
                        },
                        fontFamily: {
                            sans: ['Noto Sans SC', 'sans-serif'],
                        },
                    }
                }
            }
        </script>
        
        <style type="text/tailwindcss">
            @layer utilities {
                .content-auto {
                    content-visibility: auto;
                }
                .text-shadow {
                    text-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                .card-hover {
                    @apply transition-all duration-300 hover:shadow-lg hover:-translate-y-1;
                }
            }
        </style>
        
        <style>
            body {
                font-family: 'Noto Sans SC', sans-serif;
                scroll-behavior: smooth;
            }
            
            /* 平滑滚动 */
            html {
                scroll-behavior: smooth;
            }
            
            /* 加载动画 */
            .skeleton {
                background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
                background-size: 200% 100%;
                animation: loading 1.5s infinite;
            }
            
            @keyframes loading {
                0% { background-position: 200% 0; }
                100% { background-position: -200% 0; }
            }
        </style>
    </head>
    <body class="bg-neutral-100 min-h-screen">
        <!-- 导航栏 -->
        <header class="sticky top-0 bg-white/90 backdrop-blur-sm shadow-sm z-50 transition-all duration-300">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div class="flex justify-between items-center h-16">
                    <div class="flex items-center">
                        <i class="fa fa-newspaper-o text-primary text-2xl mr-2"></i>
                        <span class="text-xl font-bold text-neutral-700">热点聚合</span>
                    </div>
                </div>
            </div>
        </header>

        <!-- 主要内容区 -->
        <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            <!-- 介绍区 -->
            <div class="bg-white rounded-xl shadow-sm p-8 mb-10 text-center transform transition-all hover:shadow-md">
                <h2 class="text-3xl md:text-4xl font-bold text-neutral-700 mb-4">每日热点新闻聚合</h2>
                <p class="text-lg text-neutral-500 max-w-3xl mx-auto">
                    每日整理来自各大平台的热点，帮助您快速了解当下最受关注的话题，一站式掌握全球动态。
                </p>
                <p class="text-sm text-neutral-400 mt-3">
                    
                </p>
            </div>

            <!-- 文章列表 -->
            <div class="space-y-6">
    '''
    
    # 生成文章列表
    for entry in blog_entries:
        date = entry.get('date', '')
        content = entry.get('content', [])
        
        # 获取第一条新闻的图片URL作为封面
        cover_image = ''
        if content and isinstance(content, list) and len(content) > 0:
            first_news = content[0]
            if isinstance(first_news, dict):
                cover_image = first_news.get('image_url', '')
        
        # 如果没有获取到图片，使用默认的随机图片
        if not cover_image:
            cover_image = f"https://picsum.photos/600/400?random={date}"
        
        # 统计不同平台的新闻数量
        platform_counts = {}
        for news in content:
            if isinstance(news, dict):
                platform = news.get('platform', '其他')
                platform_counts[platform] = platform_counts.get(platform, 0) + 1
        
        # 生成平台统计HTML
        platform_stats_html = ''
        for platform, count in platform_counts.items():
            platform_stats_html += f'''
            <div class="flex items-center text-sm text-neutral-500">
                <i class="fa fa-folder-o mr-1"></i>
                <span>{platform} ({count}条)</span>
            </div>
            '''
        
        html += f'''
            <article class="bg-white rounded-xl shadow-sm overflow-hidden card-hover">
                <div class="md:flex">
                    <div class="md:w-1/3">
                        <img src="{cover_image}" alt="新闻图片" class="w-full h-48 md:h-full object-cover">
                    </div>
                    <div class="p-6 md:w-2/3">
                        <div class="flex items-center mb-3">
                            <span class="text-xs font-semibold px-2.5 py-0.5 rounded bg-blue-100 text-primary">综合</span>
                            <span class="ml-auto text-sm text-neutral-400">{date}</span>
                        </div>
                        <h2 class="text-xl md:text-2xl font-bold text-neutral-700 mb-3">
                            <a href="posts/{date}.html" class="hover:text-primary transition-colors">
                                {date} 热点新闻汇总
                            </a>
                        </h2>
                        <p class="text-neutral-500 mb-4 line-clamp-2">
                            今日热点涵盖多个平台热点话题，包括微博、知乎、百度等平台的热搜内容，全方位呈现今日焦点。
                        </p>
                        <div class="flex flex-wrap gap-3 mb-4">
                            {platform_stats_html}
                        </div>
                        <a href="posts/{date}.html" 
                           class="inline-flex items-center text-primary hover:text-primary/80 font-medium transition-colors">
                            查看全部内容
                            <i class="fa fa-angle-right ml-1"></i>
                        </a>
                    </div>
                </div>
            </article>
        '''
    
    html += '''
            </div>
        </main>

        <!-- 页脚 -->
        <footer class="bg-white mt-12 py-8">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div class="text-center text-neutral-500">
                    <p>© 2025 每日热点新闻聚合 | 
                    <a href="https://zxnve.dpdns.org" target="_blank" class="text-blue-400 hover:text-blue-300 transition-colors underline decoration-blue-400/30 hover:decoration-blue-300/50 underline-offset-2 font-medium">
                       导航站主页
                    </a>
                    </p>
                    <p class="mt-2">本网站内容仅记录热搜，不代表任何立场</p>
                </div>
                </div>
            </div>
        </footer>
    </body>
    </html>
    '''
    
    return html

def save_news_to_blog(report_data: Dict):
    """保存新闻数据到博客"""
    current_date = get_beijing_time().strftime("%Y-%m-%d")
    news_entry = {
        "date": current_date,
        "news": report_data.get('all_news', []),
        "content": report_data.get('all_news', []),
        "title": f"{current_date} 热点新闻汇总",
        "update_time": report_data.get('timestamp', current_date)
    }
    
    # 创建数据存储目录
    data_dir = "data"
    archive_dir = os.path.join(data_dir, "archive")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)
    os.makedirs(POSTS_DIR, exist_ok=True)

    # 写入 CNAME（如果配置存在），用于 GitHub Pages 自定义域名
    try:
        cfg = load_config()
        cname = (cfg.get('blog', {}) or {}).get('cname')
        if cname:
            with open("CNAME", "w", encoding="utf-8") as f:
                f.write(str(cname).strip())
    except Exception as e:
        print(f"写入CNAME失败: {e}")

    # 写入 robots.txt，允许所有爬虫抓取与索引（包含广告爬虫）
    try:
        robots_txt = """User-agent: *
Allow: /

# Ads crawlers
User-agent: AdsBot-Google
Allow: /
User-agent: Mediapartners-Google
Allow: /
User-agent: Baiduspider
Allow: /
User-agent: Baiduspider-ads
Allow: /
"""
        with open("robots.txt", "w", encoding="utf-8") as f:
            f.write(robots_txt)
    except Exception as e:
        print(f"写入robots.txt失败: {e}")
    
    # 保存当天数据到独立的JSON文件
    daily_data_path = os.path.join(data_dir, f"{current_date}.json")
    with open(daily_data_path, "w", encoding="utf-8") as f:
        json.dump(news_entry, f, ensure_ascii=False, indent=2)
    
    # 读取所有历史数据
    blog_entries = []
    # 读取data目录下的所有JSON文件
    for file_name in sorted(os.listdir(data_dir), reverse=True):
        if file_name.endswith('.json'):
            file_path = os.path.join(data_dir, file_name)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    entry = json.load(f)
                    blog_entries.append(entry)
            except Exception as e:
                print(f"读取数据文件 {file_name} 失败: {e}")
    
    # 归档超过30天的数据
    current_date_obj = datetime.strptime(current_date, "%Y-%m-%d")
    for entry in blog_entries[:]:
        entry_date = entry["date"]
        entry_date_obj = datetime.strptime(entry_date, "%Y-%m-%d")
        days_diff = (current_date_obj - entry_date_obj).days
        
        if days_diff > 30:
            # 将数据移动到归档目录
            old_path = os.path.join(data_dir, f"{entry_date}.json")
            new_path = os.path.join(archive_dir, f"{entry_date}.json")
            if os.path.exists(old_path):
                os.rename(old_path, new_path)
    
    # 读取博客配置
    blog_config = {
        "title": "每日热点新闻聚合",
        "description": "聚合展示微博、知乎、百度、B站等多个平台的热点新闻",
        "author": "每日新闻聚合系统",
        "language": "zh-CN",
        "theme_color": "#2196f3",
        "background_color": "#ffffff"
    }
    
    # 更新博客首页
    blog_html = render_blog_html(blog_entries, blog_config)
    with open(INDEX_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(blog_html)
    
    # 创建/更新每日详情页
    daily_html = render_daily_post_html(news_entry)
    with open(f"{POSTS_DIR}/{current_date}.html", "w", encoding="utf-8") as f:
        f.write(daily_html)

def main():
    """主函数"""
    print("=== 每日热点新闻聚合系统 ===")
    print(f"开始运行: {get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 加载配置
    config = load_config()
    if not config:
        print("配置文件加载失败，无法继续运行")
        return
    # 设置全局配置，供 HTTP 请求读取爬虫参数
    global GLOBAL_CFG
    GLOBAL_CFG = config
    
    # 加载关键词配置
    required_words, keywords, exclude_words = load_frequency_words()
    print(f"加载配置: 必须词 {len(required_words)} 个, 关键词 {len(keywords)} 个, 排除词 {len(exclude_words)} 个")
    
    # 获取新闻数据
    news = fetch_news(config)
    print(f"共获取到 {len(news)} 条原始新闻")
    
    # 过滤新闻
    filtered_news = filter_news(news, required_words, keywords, exclude_words)
    print(f"过滤后得到 {len(filtered_news)} 条新闻")
    
    if not filtered_news:
        print("没有符合条件的新闻，无需更新博客")
        return
    
    # 按关键词分组
    word_groups = group_news_by_keywords(filtered_news, keywords)
    
    # 准备报告数据
    report_data = {
        "word_groups": word_groups,
        "total": len(filtered_news),
        "timestamp": get_beijing_time().strftime("%Y-%m-%d %H:%M:%S"),
        "all_news": filtered_news
    }
    
    # 保存到博客
    save_news_to_blog(report_data)
    print("博客更新完成")

if __name__ == "__main__":
    main()
