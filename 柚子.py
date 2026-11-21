# -*- coding: utf-8 -*-
"""
youzidj.com 柚子短剧 爬虫（美化导航 / 双线路）
兼容 TVBox / 影视仓 Spider 接口
流程：bootstrap 访客账户 → /api/playback/{videoId} → 带 cookie 的 m3u8/mp4
"""

import re
import json
from html import unescape
from urllib.parse import quote, urljoin

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        pass

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    raise ImportError("请安装: pip install requests")


class Spider(BaseSpider):
    def __init__(self):
        self.host = "https://youzidj.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.host + "/",
            "Origin": self.host,
        }
        self.timeout = 18
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.verify = False
        self._bootstrapped = False

    def getName(self):
        return "柚子短剧"

    def init(self, extend=""):
        self._ensure_account()

    def _ensure_account(self):
        if self._bootstrapped and self.session.cookies.get("eden_account"):
            return True
        try:
            r = self.session.post(
                f"{self.host}/api/account/bootstrap",
                timeout=self.timeout,
                headers={**self.headers, "Accept": "application/json"},
            )
            if r.status_code == 200:
                self._bootstrapped = True
                return True
        except Exception as e:
            print(f"[柚子] bootstrap 失败: {e}")
        return False

    def _get(self, url):
        try:
            r = self.session.get(url, timeout=self.timeout)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception as e:
            print(f"[柚子] 请求失败: {url} -> {e}")
            return ""

    def _abs(self, path):
        if not path:
            return ""
        if path.startswith("//"):
            return "https:" + path
        if path.startswith("http"):
            return path
        return urljoin(self.host, path)

    def _clean(self, t):
        if not t:
            return ""
        t = unescape(t)
        t = re.sub(r"\s+", " ", t).strip()
        return t[:100]

    def _cover_webp(self, path):
        """avif → 更通用的 webp"""
        if not path:
            return ""
        path = re.sub(r"-\d+\.avif", "-480.webp", path)
        path = re.sub(r"-\d+\.webp", "-480.webp", path)
        if path.endswith(".avif"):
            path = path[:-5] + ".webp"
        return self._abs(path)

    def _parse_list(self, html):
        items = []
        if not html:
            return items
        seen = set()
        for m in re.finditer(
            r'aria-label="查看详情：([^"]+)"\s+href="https://youzidj\.com/dramas/([a-z0-9-]+)/season-(\d+)/"',
            html,
        ):
            title, slug, season = self._clean(m.group(1)), m.group(2), m.group(3)
            key = f"{slug}|{season}"
            if key in seen:
                continue
            seen.add(key)
            # 封面：链接后 picture/srcset
            snip = html[m.start(): m.start() + 1200]
            pic = ""
            im = re.search(r'(?:srcset|src)="(/catalogue-art/[^"\s]+)', snip)
            if im:
                pic = self._cover_webp(im.group(1).split()[0] if " " in im.group(1) else im.group(1))
            items.append({
                "vod_id": f"{slug}/season-{season}",
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": f"第{season}季",
            })
        return items

    # ------------------ 首页 ------------------
    def homeContent(self, filter):
        classes = [
            {"type_id": "popular", "type_name": "🔥 最热"},
            {"type_id": "updated", "type_name": "🆕 最新"},
            {"type_id": "home", "type_name": "🏠 首页推荐"},
            {"type_id": "tag:都市", "type_name": "🏙️ 都市"},
            {"type_id": "tag:修仙", "type_name": "⚔️ 修仙"},
            {"type_id": "tag:豪门", "type_name": "👑 豪门"},
            {"type_id": "tag:家庭", "type_name": "🏠 家庭伦理"},
            {"type_id": "tag:校园", "type_name": "🏫 校园"},
            {"type_id": "tag:古装", "type_name": "🏯 古装"},
            {"type_id": "tag:武侠", "type_name": "🗡️ 武侠"},
            {"type_id": "tag:系统", "type_name": "💻 系统流"},
            {"type_id": "tag:NTR", "type_name": "💔 NTR"},
            {"type_id": "tag:人妻", "type_name": "💍 人妻"},
            {"type_id": "tag:办公室", "type_name": "💼 职场"},
        ]
        return {"class": classes, "filters": {}}

    def homeVideoContent(self):
        self._ensure_account()
        html = self._get(f"{self.host}/dramas/?sort=popular")
        return {"list": self._parse_list(html)[:30]}

    # ------------------ 分类 ------------------
    def categoryContent(self, tid, pg, filter, extend):
        self._ensure_account()
        try:
            page = int(pg or 1)
        except Exception:
            page = 1
        tid = str(tid or "popular")

        if tid == "home":
            html = self._get(self.host + "/")
        elif tid.startswith("tag:"):
            kw = tid.split(":", 1)[1]
            url = f"{self.host}/search/?q={quote(kw)}"
            if page > 1:
                url += f"&page={page}"
            html = self._get(url)
        else:
            url = f"{self.host}/dramas/?sort={quote(tid)}"
            if page > 1:
                url += f"&page={page}"
            html = self._get(url)

        lst = self._parse_list(html)
        return {
            "list": lst,
            "page": page,
            "pagecount": 999 if len(lst) >= 12 else page,
            "limit": 24,
            "total": 99999 if len(lst) >= 12 else len(lst),
        }

    # ------------------ 详情 ------------------
    def detailContent(self, ids):
        self._ensure_account()
        if not ids:
            return {"list": []}
        raw = str(ids[0]).strip("/")
        # slug/season-1
        if "/season-" in raw:
            slug, season_part = raw.split("/season-", 1)
            season = re.sub(r"\D", "", season_part) or "1"
        else:
            slug, season = raw, "1"

        url = f"{self.host}/dramas/{slug}/season-{season}/"
        html = self._get(url)
        if not html:
            return {"list": []}

        name = ""
        h1 = re.search(r"<h1[^>]*>([^<]+)</h1>", html, re.I)
        if h1:
            name = self._clean(h1.group(1))
        if not name:
            t = re.search(r"<title>([^<]+)", html)
            if t:
                name = self._clean(re.split(r"[·|]", t.group(1))[0])

        pic = ""
        im = re.search(r'(?:srcset|src)="(/catalogue-art/[^"\s]+)', html)
        if im:
            pic = self._cover_webp(im.group(1).split()[0])
        if not pic:
            im = re.search(r'(?:og:image|twitter:image)"\s*content="([^"]+)"', html)
            if im:
                pic = self._abs(im.group(1))

        content = ""
        desc = re.search(r'<meta name="description" content="([^"]+)"', html)
        if desc:
            content = self._clean(desc.group(1))[:400]

        # 集数
        eps = sorted(set(int(x) for x in re.findall(
            rf'/dramas/{re.escape(slug)}/season-{season}-episode-(\d+)/',
            html,
        )))
        if not eps:
            eps = sorted(set(int(x) for x in re.findall(
                rf'season-{season}-episode-(\d+)/',
                html,
            )))
        if not eps:
            eps = [1]

        # 双线路：MSE(m3u8) + Native
        # id 格式: slug|season|ep|videoId
        # videoId 在每集页，这里先用 ep 号，播放时再解析
        line_mse = []
        line_native = []
        for ep in eps:
            eid = f"{slug}|{season}|{ep}"
            line_mse.append(f"第{ep}集${eid}|mse")
            line_native.append(f"第{ep}集${eid}|native")

        vod = {
            "vod_id": f"{slug}/season-{season}",
            "vod_name": name or slug,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": "",
            "vod_director": "",
            "vod_area": "柚子短剧",
            "vod_year": "",
            "vod_remarks": f"{len(eps)}集",
            "vod_play_from": "线路1(M3U8)$$$线路2(Native)",
            "vod_play_url": "#".join(line_mse) + "$$$" + "#".join(line_native),
        }
        return {"list": [vod]}

    # ------------------ 搜索 ------------------
    def searchContent(self, key, quick=False, pg="1"):
        self._ensure_account()
        try:
            page = int(pg or 1)
        except Exception:
            page = 1
        url = f"{self.host}/search/?q={quote(key.strip())}"
        if page > 1:
            url += f"&page={page}"
        html = self._get(url)
        lst = self._parse_list(html)
        return {
            "list": lst,
            "page": page,
            "pagecount": 999 if len(lst) >= 10 else page,
            "limit": 24,
            "total": 99999 if len(lst) >= 10 else len(lst),
        }

    def _resolve_play(self, slug, season, ep, mode="mse"):
        """打开分集页取 videoId，bootstrap，POST /api/playback"""
        self._ensure_account()
        ep_url = f"{self.host}/dramas/{slug}/season-{season}-episode-{ep}/"
        html = self._get(ep_url)
        if not html:
            return ""
        vm = re.search(r'data-video="([a-f0-9-]{36})"', html)
        if not vm:
            return ""
        video_id = vm.group(1)
        try:
            r = self.session.post(
                f"{self.host}/api/playback/{video_id}?mode={mode}",
                timeout=self.timeout,
                headers={
                    **self.headers,
                    "Accept": "application/json",
                    "Referer": ep_url,
                    "Origin": self.host,
                },
            )
            if r.status_code == 401:
                self._bootstrapped = False
                self._ensure_account()
                r = self.session.post(
                    f"{self.host}/api/playback/{video_id}?mode={mode}",
                    timeout=self.timeout,
                    headers={
                        **self.headers,
                        "Accept": "application/json",
                        "Referer": ep_url,
                        "Origin": self.host,
                    },
                )
            data = r.json()
            path = data.get("url") or ""
            if not path:
                return ""
            return self._abs(path)
        except Exception as e:
            print(f"[柚子] playback 失败: {e}")
            return ""

    # ------------------ 播放 ------------------
    def playerContent(self, flag, id, vipFlags=None):
        """
        id: slug|season|ep|mse  或  slug|season|ep|native
        """
        raw = str(id or "").strip()
        mode = "mse"
        if "|" in raw:
            parts = raw.split("|")
            # slug|season|ep|mode
            if len(parts) >= 4:
                slug, season, ep, mode = parts[0], parts[1], parts[2], parts[3]
            elif len(parts) == 3:
                slug, season, ep = parts
            else:
                slug, season, ep = parts[0], "1", "1"
        else:
            slug, season, ep = raw, "1", "1"

        mode = "native" if "native" in str(mode).lower() else "mse"
        play_url = self._resolve_play(slug, season, ep, mode=mode)
        if not play_url and mode == "mse":
            play_url = self._resolve_play(slug, season, ep, mode="native")

        if not play_url:
            return {
                "parse": 1,
                "url": f"{self.host}/dramas/{slug}/season-{season}-episode-{ep}/",
                "header": json.dumps(self.headers, ensure_ascii=False),
            }

        # 播放需要带上 session cookie
        cookie_header = "; ".join(
            f"{c.name}={c.value}" for c in self.session.cookies
        )
        return {
            "parse": 0,
            "url": play_url,
            "header": json.dumps({
                "User-Agent": self.headers["User-Agent"],
                "Referer": self.host + "/",
                "Origin": self.host,
                "Cookie": cookie_header,
                "Accept": "*/*",
            }, ensure_ascii=False),
        }

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4)(\?|$)", str(url), re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass


if __name__ == "__main__":
    s = Spider()
    print("cats", [c["type_name"] for c in s.homeContent(False)["class"][:6]])
    hv = s.homeVideoContent()
    print("home", len(hv["list"]), hv["list"][0] if hv["list"] else None)
    if hv["list"]:
        d = s.detailContent([hv["list"][0]["vod_id"]])["list"][0]
        print("detail", d["vod_name"], d["vod_remarks"])
        print("from", d["vod_play_from"])
        pid = d["vod_play_url"].split("$$$")[0].split("#")[0].split("$")[-1]
        print("play id", pid)
        pr = s.playerContent("线路1", pid)
        print("play", pr.get("parse"), (pr.get("url") or "")[:100])
