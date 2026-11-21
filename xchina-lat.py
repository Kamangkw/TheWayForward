#!/usr/bin/python
# coding=utf-8
import re, json, requests
from urllib.parse import quote
from base.spider import Spider

class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.name = "小黄书 xChina"
        self.host = "https://www.xchina.lat"
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
            "Referer": "https://www.xchina.lat/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
        self.categories = [
            ("madouchuanmei", "麻豆传媒"), ("91zhipian", "91制片"), ("tangxin", "糖心Vlog"),
            ("xingbayuanchuang", "杏吧原创"), ("xingkongchuanmei", "星空传媒"), ("huayuyuanchuang", "华语原创"),
            ("jingdongyingye", "精东影业"), ("tianmeichuanmei", "天美传媒"), ("mitaoyingxiang", "蜜桃影像"),
            ("chuanmeijingpin", "传媒精品"), ("huangjiahuaren", "皇家华人"), ("jingpintuijian", "精品推荐"),
            ("zipaitoupai", "自拍偷拍"), ("wanghongzhubo", "网红主播"), ("zhifusiwa", "抖阴视频"),
            ("chiguaheiliao", "51吃瓜"), ("91tanhua", "51探花"), ("chengrentoutiao", "成人头条"),
            ("nvshenxuesheng", "女神学生"), ("wangpumen", "网曝门"), ("sipaixiemi", "私拍泄密"),
            ("haijiaoluanlun", "海角乱仑"), ("zuyutandian", "足浴探店"), ("fanchabiao", "反差婊"),
            ("rihanwuma", "日韩无码"), ("zhongwenzimu", "中文字幕"), ("ribenyouma", "日本有码"),
            ("siwameitui", "丝袜美腿"), ("nvyoumingxing", "女优明星"), ("renqishunv", "人妻熟女"),
            ("koujiaoyanshe", "口交颜射"), ("qiangjianluanlun", "强奸乱仑"), ("ribenjingpin", "日本精品"),
            ("duorenqunjiao", "多人群交"), ("dongnanyaAV", "东南亚AV"), ("hanguoyujie", "韩国御姐"),
            ("weimeigangjie", "唯美港姐"), ("taiwanlamei", "台湾辣妹"), ("hanguozhubo", "韩国主播"),
            ("nvtongxingai", "女同xing爱"), ("luolishaonv", "萝莉少女"), ("sanjilunli", "三级伦理"),
            ("oumeijiqing", "欧美激情"), ("yingheshipin", "硬核视频"), ("oumeijingpin", "欧美精品"),
            ("seqingmingxing", "色情明星"), ("katongdongman", "卡通动漫"), ("chengrendongman", "成人动漫"),
            ("juqingdongman", "剧情动漫"), ("jiqingdongman", "激情动漫"), ("madoushipin", "麻豆视频"),
            ("dalushipin", "大陆视频"), ("AImingxing", "AI明星"), ("yazhoushipin", "日本AV"),
            ("yazhoujingpin", "亚洲精品"), ("oumeishipin", "欧美视频")
        ]

    def init(self, extend=""):
        return True

    def isVideoFormat(self, url):
        formats = [".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".avi"]
        return any(f in url.lower() for f in formats)

    def manualVideoCheck(self):
        return False

    def getName(self):
        return "小黄书 xChina"

    def fetch(self, url):
        try:
            resp = requests.get(url, headers=self.header, timeout=15)
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text if resp.status_code == 200 else ""
        except Exception:
            return ""

    def fix_url(self, url):
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return self.host + url
        return url

    def clean_text(self, text):
        if not text:
            return ""
        import html as _html
        t = _html.unescape(text)
        t = re.sub(r"<[^>]+>", "", t)
        return re.sub(r"\s+", " ", t).strip()

    def _parse_cards(self, html):
        videos = []
        seen = set()
        pat = re.compile(r'<div class="item video">\s*<a href="(/av/\d+-1-1/)" title="([^"]*)">.*?background-image:url\(\'([^\']+)\'\).*?<div class="tags"><div>([^<]*)</div>', re.S)
        for m in pat.finditer(html or ""):
            try:
                href, title, pic, tag = m.group(1), self.clean_text(m.group(2)), m.group(3), self.clean_text(m.group(4))
                if not href or href in seen or not title:
                    continue
                seen.add(href)
                videos.append({"vod_id": href, "vod_name": title, "vod_pic": pic.split("?")[0], "vod_remarks": tag})
            except Exception:
                continue
        return videos

    def _parse_categories(self, html):
        cats = []
        seen = set()
        for slug, name in re.findall(r'href="/vodtype/([^/]+)/"[^>]*>\s*<div class="sub"><span>([^<]+)</span>', html or ""):
            if slug not in seen:
                seen.add(slug)
                cats.append({"type_id": slug, "type_name": name.strip()})
        for slug, name in re.findall(r'href="/vodtype/([^/]+)/"><span class="tag">([^<]+)</span>', html or ""):
            if slug not in seen:
                seen.add(slug)
                cats.append({"type_id": slug, "type_name": name.strip()})
        if not cats:
            cats = [{"type_id": s, "type_name": n} for s, n in self.categories]
        return cats

    def _play_json(self, html):
        i = (html or "").find("player_data=")
        if i < 0:
            return {}
        s = html.find("{", i)
        if s < 0:
            return {}
        depth = 0
        j = s
        while j < len(html):
            c = html[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if depth != 0:
            return {}
        try:
            return json.loads(html[s:j + 1])
        except Exception:
            return {}

    def _norm_play_path(self, vid):
        v = (vid or "").strip()
        if v.startswith("http"):
            v = re.sub(r"^https?://[^/]+", "", v)
        if re.fullmatch(r"\d+", v):
            return "/av/%s-1-1/" % v
        if re.match(r"/av/\d+-1-1/", v):
            return v
        m = re.search(r"/av/(\d+)-1-1/", v)
        if m:
            return "/av/%s-1-1/" % m.group(1)
        return v if v.startswith("/") else "/" + v

    def homeContent(self, filter=False):
        html = self.fetch(self.host + "/")
        return {"class": self._parse_categories(html)}

    def homeVideoContent(self):
        html = self.fetch(self.host + "/")
        return {"list": self._parse_cards(html)}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg <= 1:
            url = "%s/vodtype/%s/" % (self.host, tid)
        else:
            url = "%s/vodtype/%s-%d/" % (self.host, tid, pg)
        html = self.fetch(url)
        videos = self._parse_cards(html)
        pages = [int(x) for x in re.findall(r"/vodtype/%s-(\d+)/" % re.escape(tid), html or "")]
        pagecount = max(pages) if pages else 1
        return {"list": videos, "page": pg, "pagecount": pagecount, "limit": len(videos), "total": pagecount * len(videos) if videos else 0}

    def detailContent(self, ids):
        path = self._norm_play_path(ids[0])
        html = self.fetch(self.host + path)
        title = ""
        m = re.search(r"<h1[^>]*>(.*?)</h1>", html or "", re.S)
        if m:
            title = self.clean_text(m.group(1))
        if not title:
            m = re.search(r'<div class="player-section">.*?<div class="left">([^<]+)</div>', html or "", re.S)
            if m:
                title = self.clean_text(m.group(1))
        if not title:
            m = re.search(r"<title>(.*?)</title>", html or "", re.S)
            if m:
                title = self.clean_text(m.group(1)).split("免费播放")[0].strip()
        data = self._play_json(html)
        m3u8 = (data.get("url") or "").replace("\\/", "/")
        pic = ""
        cards = self._parse_cards(html)
        for c in cards:
            if c["vod_id"] == path:
                pic = c["vod_pic"]
                break
        if not pic and m3u8:
            d = re.search(r"/(\d+/[A-Za-z0-9]+/)index\.m3u8", m3u8)
            hosts = re.findall(r"background-image:url\('(https?://[^/]+)/", html or "")
            if d and hosts:
                pic = hosts[0] + "/" + d.group(1) + "1.jpg"
        return {"list": [{"vod_id": path, "vod_name": title or "小黄书", "vod_pic": pic, "vod_play_from": "小黄书", "vod_play_url": "正片$%s" % path}]}

    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg <= 1:
            url = "%s/vodsearch/-------------.html?wd=%s" % (self.host, quote(key))
        else:
            url = "%s/vodsearch/%s----------%d---/" % (self.host, quote(key), pg)
        html = self.fetch(url)
        videos = self._parse_cards(html)
        pages = [int(x) for x in re.findall(r"/vodsearch/[^\"']*?----------(\d+)---/", html or "")]
        pagecount = max(pages) if pages else 1
        return {"list": videos, "page": pg, "pagecount": pagecount, "limit": len(videos), "total": pagecount * len(videos) if videos else 0}

    def playerContent(self, flag, id, vipFlags):
        path = self._norm_play_path(id)
        html = self.fetch(self.host + path)
        data = self._play_json(html)
        url = (data.get("url") or "").replace("\\/", "/")
        if url and ".m3u8" in url:
            return {"parse": 0, "url": url, "header": ""}
        m = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html or "")
        if m:
            return {"parse": 0, "url": m.group(1), "header": ""}
        return {"parse": 0, "url": "", "header": ""}
