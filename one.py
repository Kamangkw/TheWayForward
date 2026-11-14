# -*- coding: utf-8 -*-
"""
TVBox / 映匣 Python 源 —— ONE 一个
由 WeBox 原生源 ONE.js（作者 YG）移植为 CatVod Python spider。

接口（与原脚本一致）：
  bootstrap        POST /v2.5/bootstrap                  → token + 域名池（body 为空）
  discovery        POST /v2.5/article/discovery          → 按月 + 按 model(6 长视频 / 3 视频) 取目录
  article/search   POST /v2.5/article/search             → 搜索 / ONE 直播回放
  article/detail   POST /v2.5/article/detail             → 详情、合集选集、直链

要点：
  * 请求体必须 AES-CBC/PKCS7 加密后 base64；明文会被 406 拒绝。
  * 响应可能是 JSON 明文，也可能是同密钥的 base64 密文，两种都兼容。
  * 签名 sign = md5(md5("0.0.0.0.3.{ts}..{uuid}") + SALT)
  * body 为空时不要发 body（Xcdn 对长度 0 的 POST body 返回 403）。
  * 种子域名只用于 bootstrap；拿到 token 后用 domain.api 里的域名。

本地直接跑：
  python3 one.py home
  python3 one.py list newest 1
  python3 one.py list jp 1
  python3 one.py search 关键词
  python3 one.py detail 64503
  python3 one.py play 64503
"""

import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import cmp_to_key
import json
import re
import sys
import time
import uuid
import html

try:
    import requests
except ImportError:                                    # 极简环境兜底
    requests = None

try:
    from Crypto.Cipher import AES
except ImportError:                                    # 映匣 iOS 上 pycryptodome 被打过补丁，理论上都有
    AES = None

try:
    from base.spider import Spider as BaseSpider
except ImportError:                                    # 本地 CLI 单跑时用空基类
    class BaseSpider(object):
        pass


# ==================== 常量 ====================

APP_KEY = "l*bv%Ziq000Biaog"
APP_IV = "8597506002939249"
SIGN_SALT = "m4n2hjPeYWkD6tFpqKF^3HO^h24P@idT"
APP_VERSION = "1.6.0"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

SEED_HOSTS = [
    "https://api.2b37894.com", "https://api.35a46dd.com", "https://api.43b8477.com",
    "https://api.5ce3771.com", "https://api.61c76a0.com", "https://api.632d809.com",
    "https://api.3459381.com", "https://api.em1oifd0.com", "https://api.j7y675.com",
]

VIDEO_MODELS = (6, 3)
ONE_PAGE_SIZE = 24
PAGE_LIMIT = 400                     # 分区筛选最多往回扫多少个月
SESSION_TTL = 6 * 3600
TIMEOUT_BOOTSTRAP = 6
TIMEOUT_API = 12
BAD_HOST_COOLDOWN = 90        # 失败过的域名先冷一会儿

CATEGORIES = [
    {"type_id": "newest", "type_name": "最新视频"},
    {"type_id": "hot", "type_name": "热门视频"},
    {"type_id": "jp", "type_name": "日本"},
    {"type_id": "cn", "type_name": "国产"},
    {"type_id": "us", "type_name": "欧美"},
    {"type_id": "live", "type_name": "ONE 直播"},
]

PARTITIONS = {
    "jp": {"id": "jp", "tag": 2, "title": "日本"},
    "cn": {"id": "cn", "tag": 3, "title": "国产"},
    "us": {"id": "us", "tag": 1, "title": "欧美"},
    "live": {"id": "live", "tag": 4, "title": "ONE 直播"},
}

PLAIN_HOSTS = ["https://imgpw807.s7n7ue8.com", "https://imgpw807.2u7qzt7.com",
               "https://img807.hkq57tt.com", "https://imgsu807.hkq57tt.com"]
ENC_HOSTS = ["gdliren123.com", "u3wwetf.com", "m6qzbb4.com", "bdsy56.com", "gzjsqx.com", "k8b3rsp.com"]
BAD_HOSTS = ["imgsu807.hkq57tt.com"]
IMG_PROXY = "https://wsrv.nl/?url="

TAG_US = re.compile(r"^(欧美|美国|英国|德国|法国|意大利|西班牙|荷兰|瑞典|瑞士|奥地利|波兰|捷克|匈牙利|罗马尼亚|保加利亚|俄罗斯|乌克兰|白俄罗斯|拉脱维亚|立陶宛|爱沙尼亚|巴西|墨西哥|阿根廷|哥伦比亚|秘鲁|智利|古巴|委内瑞拉|拉美|拉丁|加拿大|澳洲|澳大利亚|新西兰|印度|泰国|越南|菲律宾|印尼|马来西亚|阿拉伯|异域|土耳其|迪拜|以色列|伊朗|黑人|金发|白人|碧眼|西方|外国|欧美无码|欧美精品)$")
TAG_JP = re.compile(r"^(日本|日系|日韩|日本无码|日本精品)$")
TAG_CN = re.compile(r"^(国产|国语|华语|国产精品|国产无码|港台|台湾|香港|新加坡)$")

STRONG_US = re.compile(r"(p站|onlyfans|fansly|faphouse|pjgirls|deeper|tushy|vixen|blacked|brazzers|realitykings|bangbros|teamskeet|mylf|chaturbate|cb站|推特|fansone|manyvids)", re.I)
STRONG_CN = re.compile(r"(ai短剧|短剧|探花|门事件|绿播|微密圈|抖音|快手|b站|91|抖阴|杏吧|麻豆|天美|糖心|精东|国语|华语|国产精品)", re.I)

TEXT_US = re.compile(r"(p站|pornhub|onlyfans|fansly|faphouse|pjgirls|deeper|tushy|vixen|blacked|brazzers|realitykings|naught(y|iamerica)|bangbros|teamskeet|mylf|chaturbate|cb站|推特|x站|洋马|白人|金发|碧眼|欧美|美国|英国|德国|法国|俄罗斯|乌克兰|巴西|拉美|拉丁|大洋马|洋妞|老外|外国|bbc|bwc|尼哥|黑大炮|捷克|西班牙|意大利|加拿大|澳洲|印度|泰国|越南|菲律宾|印尼|马来西亚|阿拉伯|异域|土耳其|迪拜|以色列|韩国|韩系|波兰|匈牙利|罗马尼亚|latina|ebony|russian|blonde)", re.I)
TEXT_JP = re.compile(r"(无码|有码|人妻|女优|痴女|素人|日系|日本|和服|风俗|fc2|heyzo|jav|myfans|oppai|s1|sod|falen|moodyz|prestige|ideapocket|ipx|ssni|miaa|madonna|ダスッ|カリビアン|加勒比|一本道|天然むすめ|tokyo\s*hot|10musume|heydouga|无修正|中文字幕|熟女|女教师|痴汉|电车|东京|大阪|温泉)", re.I)
TEXT_CN = re.compile(r"(ai短剧|短剧|探花|门事件|绿播|福利姬|网红|主播|大秀|微密圈|抖音|快手|b站|私拍|旗袍|学生妹|御姐|大圈|传媒|天美|麻豆|星空|糖心|91|抖阴|杏吧|蜜桃|精东|国产|国语|华语|coser|cosplay|推特福利|私人订制|定制合集)", re.I)
CODE_JP = re.compile(r"\b[a-z]{2,5}[-_]\d{2,5}\b", re.I)
JP_KANA = re.compile(r"[\u3040-\u30ff]")
CJK = re.compile(r"[\u3400-\u9fff]")
LAT = re.compile(r"[a-z]", re.I)


# ==================== 工具 ====================

def clean(value):
    text = "" if value is None else str(value)
    text = re.sub(r"<[^>]*>", " ", text)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'), ("&#39;", "'"),
                 ("&lt;", "<"), ("&gt;", ">")):
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip()


def pick(*values):
    for value in values:
        if value is not None and str(value).strip() != "":
            return value
    return ""


def month_start(offset):
    now = time.localtime()
    year, month = now.tm_year, now.tm_mon - int(offset)
    while month <= 0:
        month += 12
        year -= 1
    return "%04d-%02d-01" % (year, month)


def month_label(offset):
    now = time.localtime()
    year, month = now.tm_year, now.tm_mon - int(offset)
    while month <= 0:
        month += 12
        year -= 1
    return "%d年%d月" % (year, month)


def seconds_to_text(sec):
    sec = int(sec or 0)
    if sec <= 0:
        return ""
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)


def duration_seconds(a):
    try:
        value = int(a.get("video_length") or 0)
    except (TypeError, ValueError):
        value = 0
    if value > 0:
        return value
    length = str(a.get("length") or a.get("duration") or "").strip()
    if not length:
        return 0
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", length)
    if m:
        if m.group(3):
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:分钟|分|min)", length, re.I)
    if m:
        return int(round(float(m.group(1)) * 60))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:小时|h)", length, re.I)
    if m:
        return int(round(float(m.group(1)) * 3600))
    m = re.search(r"(\d+)\s*(?:秒|s)$", length, re.I)
    if m:
        return int(m.group(1))
    return 0

def _hash(text):
    value = 0
    for ch in str(text):
        value = (value * 31 + ord(ch)) & 0xFFFFFFFF
    return value


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _model_name(model_id):
    model_id = _int(model_id)
    return {1: "图集", 2: "视频", 3: "视频", 4: "图文", 5: "音频", 6: "长视频"}.get(model_id, "内容")


def _cmp(a, b, sort_mode):
    if sort_mode == "like_number":
        return _int(b.get("like_number")) - _int(a.get("like_number"))
    left, right = str(b.get("published_at") or ""), str(a.get("published_at") or "")
    return (left > right) - (left < right)


# ==================== 加密 ====================

def _pad(text):
    raw = text.encode("utf-8")
    pad = 16 - len(raw) % 16
    return raw + bytes([pad]) * pad


def aes_encrypt(text):
    cipher = AES.new(APP_KEY.encode("utf-8"), AES.MODE_CBC, APP_IV.encode("utf-8"))
    return base64.b64encode(cipher.encrypt(_pad(text))).decode("ascii")


def aes_decrypt(payload):
    cipher = AES.new(APP_KEY.encode("utf-8"), AES.MODE_CBC, APP_IV.encode("utf-8"))
    raw = cipher.decrypt(base64.b64decode(payload))
    if raw:
        pad = raw[-1]
        if 1 <= pad <= 16:
            raw = raw[:-pad]
    return raw.decode("utf-8", "replace")


def md5(text):
    return hashlib.md5(str(text).encode("utf-8")).hexdigest()


def enc_query(params):
    if not params:
        return ""
    parts = []
    for key, value in params.items():
        if value is None or value == "":
            continue
        parts.append("%s=%s" % (key, requests.utils.quote(str(value), safe="")))
    return "&".join(parts)


def parse_payload(text):
    if text is None:
        return None
    text = text.strip() if isinstance(text, str) else str(text).strip()
    if not text:
        return None
    if text.startswith("{"):
        try:
            return json.loads(text)
        except ValueError:
            return None
    try:
        plain = aes_decrypt(text)
    except Exception:
        return None
    try:
        return json.loads(plain)
    except ValueError:
        return None


# ==================== 会话与请求 ====================

class Spider(BaseSpider):

    def __init__(self):
        try:
            BaseSpider.__init__(self)
        except Exception:
            pass
        self.uuid = str(uuid.uuid4())
        self.host = ""
        self.token = ""
        self.ts = 0
        self.domains = {"api": [], "image": [], "resource": [], "fimg": [], "video": [],
                        "video_hls": [], "audio": [], "vplay": [], "vdl": [], "audl": []}
        self._http = None
        self._pages = {}
        self._page_bytes = 0
        self._feeds = {}
        self._covers = {}
        self._details = {}
        self._probes = {}
        self._bad_hosts = {}
        self._good_hosts = []

    # ---------- 宿主回调 ----------

    def getName(self):
        return "ONE一个"

    def init(self, extend=''):
        self.uuid = str(uuid.uuid4())
        self.host = ""
        self.token = ""
        self.ts = 0
        self.domains = {k: [] for k in self.domains}
        self._pages = {}
        self._page_bytes = 0
        self._feeds = {}
        self._covers = {}
        self._details = {}
        self._probes = {}
        self._bad_hosts = {}
        self._good_hosts = []
        return None

    def isVideoFormat(self, url):
        return ".m3u8" in (url or "") or ".mp4" in (url or "")

    def manualVideoCheck(self):
        return False

    def _session(self):
        if self._http is None:
            self._http = requests.Session()
            self._http.trust_env = True
        return self._http

    def _headers(self, token=None):
        ts = int(time.time())
        return {
            "platform": "3",
            "uuid": self.uuid,
            "timestamp": str(ts),
            "token": self.token if token is None else token,
            "app-version": APP_VERSION,
            "sign": md5(md5("0.0.0.0.3.%d..%s" % (ts, self.uuid)) + SIGN_SALT),
            "user-key": "",
            "ip": "0.0.0.0",
            "User-Agent": UA,
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def _post(self, host, path, params=None, token=None):
        body = None
        query = enc_query(params)
        if query:
            body = aes_encrypt(query)
        url = host + "/v2.5/" + path
        timeout = TIMEOUT_BOOTSTRAP if path == "bootstrap" else TIMEOUT_API
        resp = self._session().post(url, data=body, headers=self._headers(token), timeout=timeout)
        return parse_payload(resp.text)

    def _hosts(self):
        hosts = []
        for candidate in self._good_hosts + [self.host] + list(self.domains.get("api") or []) + SEED_HOSTS:
            if candidate and candidate not in hosts:
                hosts.append(candidate)
        now = time.time()
        fresh = [h for h in hosts if self._bad_hosts.get(h, 0) < now]
        stale = [h for h in hosts if self._bad_hosts.get(h, 0) >= now]
        return fresh + stale

    def _mark_bad(self, host):
        self._bad_hosts[host] = time.time() + BAD_HOST_COOLDOWN
        if host in self._good_hosts:
            self._good_hosts.remove(host)

    def _mark_good(self, host):
        self._bad_hosts.pop(host, None)
        if host in self._good_hosts:
            self._good_hosts.remove(host)
        self._good_hosts.insert(0, host)
        del self._good_hosts[6:]

    def _apply_domains(self, domain):
        if not isinstance(domain, dict):
            return
        mapping = {"api": "api", "image": "image", "resource": "resource", "flutter_img": "fimg",
                   "video": "video", "video_hls": "video_hls", "audio": "audio",
                   "flutter_video_play": "vplay", "flutter_video_download": "vdl", "audio_download": "audl"}
        for source, target in mapping.items():
            value = domain.get(source)
            if isinstance(value, list) and value:
                self.domains[target] = list(value)

    def _try_bootstrap(self, host):
        """单独线程里试一个种子域名，返回 (host, data) 或 None。"""
        try:
            payload = self._post(host, "bootstrap", None, "")
        except Exception:
            return None
        if isinstance(payload, dict) and int(payload.get("code") or 0) == 200 and payload.get("data"):
            return host, payload["data"]
        return None

    def bootstrap(self, force=False):
        if not force and self.token and self.host and time.time() - self.ts < SESSION_TTL:
            return
        hosts = self._hosts()[:8]
        if not hosts:
            raise RuntimeError("ONE 初始化失败：没有可用域名")
        pool = ThreadPoolExecutor(max_workers=min(4, len(hosts)))
        try:
            futures = [pool.submit(self._try_bootstrap, host) for host in hosts]
            for future in as_completed(futures, timeout=TIMEOUT_BOOTSTRAP + 4):
                found = future.result()
                if not found:
                    continue
                host, data = found
                user = data.get("user") or {}
                self.host = host
                self.token = user.get("token") or ""
                self._apply_domains(data.get("domain"))
                self.ts = time.time()
                self._mark_good(host)
                return
        except Exception:
            pass
        finally:
            pool.shutdown(wait=False)
        raise RuntimeError("ONE 初始化失败：域名都连不上，稍后再试")

    def _call(self, path, params=None):
        self.bootstrap()
        refreshed = False
        while True:
            last = None
            for host in self._hosts():
                try:
                    payload = self._post(host, path, params)
                except Exception as error:
                    self._mark_bad(host)
                    last = error
                    continue
                if not payload:
                    self._mark_bad(host)
                    last = RuntimeError("ONE 响应无法解析")
                    continue
                code = int(payload.get("code") or 0)
                if code == 200:
                    if self.host != host:
                        self.host = host
                    self._mark_good(host)
                    return payload.get("data")
                if code == 401:
                    # 种子域名只接受 bootstrap，其他接口要换到 domain.api 里的域名
                    last = RuntimeError("认证失效")
                    continue
                if code in (403, 450):
                    raise RuntimeError("当前账号没有此内容的访问权限")
                raise RuntimeError("ONE 接口返回错误（%s）" % code)
            if last is not None and "认证失效" in str(last) and not refreshed:
                refreshed = True
                self.bootstrap(True)
                continue
            raise RuntimeError("ONE 暂时无法响应，请稍后重试：%s" % last)

    # ==================== 分类判定 ====================

    @staticmethod
    def _tag_list(a):
        out = []
        for item in (a.get("tags") or []):
            if isinstance(item, str):
                value = item
            elif isinstance(item, dict):
                value = item.get("slug") or item.get("name") or item.get("title") or item.get("tag_name") or ""
            else:
                value = ""
            value = re.sub(r"\s+", " ", str(value)).strip()
            if value:
                out.append(value)
        return out

    def _region_by_tags(self, a):
        us = jp = cn = 0
        for tag in self._tag_list(a):
            if TAG_US.match(tag):
                us += 1
            elif TAG_JP.match(tag):
                jp += 1
            elif TAG_CN.match(tag):
                cn += 1
        if us and us >= jp and us >= cn:
            return "us"
        if jp and jp >= cn:
            return "jp"
        return "cn" if cn else ""

    def _classify_by_text(self, a):
        title = str(pick(a.get("title"), a.get("video_name"), "") or "")
        text = title + " " + str(a.get("author") or "")
        low = text.lower()
        if JP_KANA.search(text):
            return "jp"
        if TEXT_US.search(low):
            return "us"
        if CODE_JP.search(low):
            return "jp"
        if TEXT_JP.search(text):
            return "jp"
        if TEXT_CN.search(text):
            return "cn"
        cjk = len(CJK.findall(text))
        lat = len(LAT.findall(text))
        if lat > cjk * 1.5 and lat > 6:
            return "us"
        return "cn"

    def _classify_part(self, a):
        title = str(pick(a.get("title"), a.get("video_name"), "") or "")
        if "[ONE直播" in title:
            return "live"
        if "直播回放" in title and re.search(r"one直播", title, re.I):
            return "live"
        if STRONG_US.search(title):
            return "us"
        if STRONG_CN.search(title):
            return "cn"
        if JP_KANA.search(title):
            return "jp"
        if CODE_JP.search(title):
            return "jp"
        return self._region_by_tags(a) or self._classify_by_text(a)

    # ==================== 图片 ====================

    def _img_hosts(self):
        hosts = []

        def add(values):
            for value in (values or []):
                host = str(value or "").rstrip("/")
                if not host or host in hosts:
                    continue
                if any(bad in host for bad in BAD_HOSTS):
                    continue
                hosts.append(host)

        add(self.domains.get("fimg"))
        add(self.domains.get("resource"))
        add(PLAIN_HOSTS)
        return hosts

    def _abs_image(self, path):
        if not path:
            return ""
        path = str(path)
        if path.startswith("http://") or path.startswith("https://"):
            for enc in ENC_HOSTS:
                if enc in path:
                    match = re.match(r"^https?://[^/]+(/.+)$", path)
                    tail = match.group(1) if match else path
                    hosts = self._img_hosts() or ["https://img807.hkq57tt.com"]
                    return hosts[_hash(tail) % len(hosts)] + tail
            return path
        hosts = self._img_hosts() or ["https://img807.hkq57tt.com"]
        return hosts[_hash(path) % len(hosts)] + ("" if path.startswith("/") else "/") + path

    @staticmethod
    def _gif_to_jpeg(url):
        if not re.search(r"\.gif(\?|$)", str(url), re.I):
            return url
        return IMG_PROXY + requests.utils.quote(url, safe="") + "&output=jpg&w=520"

    def _best_image(self, a):
        candidates = [a.get("thumbnail"), a.get("thumb"), a.get("video_cover"), a.get("cover"), a.get("thumb_tiny")]
        if isinstance(a.get("multi_pic_thumbnail"), list):
            candidates += a["multi_pic_thumbnail"]
        if isinstance(a.get("thumbnail_list"), list):
            candidates += a["thumbnail_list"]
        gif = ""
        for candidate in candidates:
            url = self._abs_image(candidate)
            if not url:
                continue
            if re.search(r"\.gif(\?|$)", url, re.I):
                gif = gif or url
                continue
            return url
        return self._gif_to_jpeg(gif) if gif else ""

    # ==================== 播放线路 ====================

    def _video_hosts(self):
        hosts = []

        def add(values):
            for value in (values or []):
                host = str(value or "").rstrip("/")
                if not host or host in hosts:
                    continue
                if any(bad in host for bad in BAD_HOSTS):
                    continue
                hosts.append(host)

        for key in ("video", "vdl", "vplay", "audl", "audio"):
            add(self.domains.get(key))
        return hosts or ["https://46e9nz.mfpt8g.com", "https://f86xxm.upmf83.com"]

    def _abs_video(self, path, kind=""):
        if not path:
            return ""
        path = str(path)
        if path.startswith("http://") or path.startswith("https://"):
            return path
        key = "video_hls" if kind == "hls" else ("audio" if kind == "audio" else "video")
        hosts = self.domains.get(key) or ["https://46e9nz.mfpt8g.com"]
        return hosts[0] + ("" if path.startswith("/") else "/") + path

    @staticmethod
    def _preview_only(a):
        if not a:
            return True
        if str(a.get("video_download") or ""):
            return False
        video = str(a.get("video_file") or "")
        if not video:
            return bool(str(a.get("preview_video") or ""))
        if str(a.get("preview_video") or "") == video:
            return True
        return bool(re.search(r"preview|sample|_pr\.mp4|-pr\.mp4", video, re.I))

    def _video_lines(self, a, hosts=None):
        lines = []
        hosts = hosts or self._video_hosts()

        def add_mp4(path, label, desc):
            if not path:
                return
            path = str(path)
            direct = path.startswith("http://") or path.startswith("https://")
            limit = 1 if direct else min(len(hosts), 5)
            for index in range(limit):
                url = path if direct else hosts[index] + ("" if path.startswith("/") else "/") + path
                suffix = "（H.265）" if re.search(r"h265", path, re.I) else ""
                lines.append({"name": "%s · 线路 %d%s" % (label, index + 1, suffix), "url": url, "desc": desc})

        preview_only = self._preview_only(a)
        add_mp4(a.get("video_download"), "MP4", "ONE 直连")
        if not preview_only and a.get("video_file") and str(a.get("video_file")) != str(a.get("video_download") or ""):
            add_mp4(a.get("video_file"), "MP4", "ONE 直连")
        elif preview_only:
            add_mp4(a.get("video_file"), "预告 MP4", "预告片，非完整版")
        if not lines or preview_only:
            if a.get("video_hls"):
                lines.append({"name": "HLS 备用", "url": self._abs_video(a["video_hls"], "hls"), "desc": "加密清单，可能无法直接播放"})
            if a.get("video_hls_h265"):
                lines.append({"name": "HLS H.265 备用", "url": self._abs_video(a["video_hls_h265"], "hls"), "desc": "加密清单，可能无法直接播放"})
        if a.get("audio_file"):
            lines.append({"name": "音频", "url": self._abs_video(a["audio_file"], "audio"), "desc": "ONE FM"})
        if a.get("audio_hls"):
            lines.append({"name": "音频 HLS", "url": self._abs_video(a["audio_hls"], "hls"), "desc": "ONE FM · HLS"})
        if not lines and a.get("preview_video"):
            lines.append({"name": "预览", "url": self._abs_video(a["preview_video"]), "desc": "预览片段"})
        return [line for line in lines if line["url"]]

    def _probe(self, path):
        """并发探测各视频域名，返回能连上的域名（快的在前）。结果缓存 5 分钟。"""
        path = str(path or "")
        if not path:
            return self._video_hosts()[:1]
        cached = self._probes.get(path)
        if cached and time.time() - cached[0] < 300:
            return cached[1]
        hosts = self._video_hosts()[:6]

        def one(host):
            url = path if path.startswith("http") else host.rstrip("/") + ("" if path.startswith("/") else "/") + path
            started = time.time()
            try:
                response = requests.get(url, headers={"Range": "bytes=0-1", "User-Agent": UA},
                                        timeout=6, stream=True)
                code = response.status_code
                response.close()
                if code in (200, 206):
                    return host, time.time() - started
            except Exception:
                pass
            return host, None

        usable = []
        if len(hosts) > 1:
            with ThreadPoolExecutor(max_workers=min(6, len(hosts))) as pool:
                for host, cost in pool.map(one, hosts):
                    if cost is not None:
                        usable.append((cost, host))
            usable.sort()
        ranked = [host for _, host in usable] or hosts[:1]
        self._probes[path] = (time.time(), ranked)
        return ranked


    # ==================== 目录分页（按月份聚合，同原脚本） ====================

    def _compact(self, a):
        keys = ("id", "model_id", "title", "video_name", "author", "published_at", "views", "like_number",
                "description", "subtitle", "video_length", "length", "duration", "size", "thumbnail", "thumb",
                "video_cover", "cover", "thumb_tiny", "multi_pic_thumbnail", "thumbnail_list",
                "video_download", "video_file", "preview_video")
        out = {k: a[k] for k in keys if k in a}
        out["tags"] = self._tag_list(a)
        return out

    def _month_page(self, model, offset, page, sort_mode):
        key = "%s:%s:%s:%s" % (month_start(offset), model, sort_mode, page)
        cached = self._pages.get(key)
        if cached and time.time() - cached["ts"] < (120 if int(offset) <= 1 else 12 * 3600):
            return cached["rows"]
        self.bootstrap()
        rows = self._call("article/discovery", {"model_id": model, "published_at": month_start(offset),
                                                "page": page, "size": ONE_PAGE_SIZE, "sort": sort_mode})
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            raise RuntimeError("ONE 目录返回格式不正确，请重试")
        rows = [self._compact(item) for item in rows if isinstance(item, dict)]
        record = {"rows": rows, "ts": time.time(), "bytes": len(json.dumps(rows, ensure_ascii=False)) * 2}
        if cached:
            self._page_bytes -= cached.get("bytes", 0)
        self._pages[key] = record
        self._page_bytes += record["bytes"]
        while self._page_bytes > 4 * 1024 * 1024 and len(self._pages) > 4:
            oldest = min(self._pages, key=lambda k: self._pages[k]["ts"])
            self._page_bytes -= self._pages[oldest].get("bytes", 0)
            self._pages.pop(oldest, None)
        return rows

    def _next_article(self, feed):
        for stream in feed["streams"]:
            if not stream["done"] and stream["at"] >= len(stream["queue"]):
                rows = self._month_page(stream["model"], feed["off"], stream["page"], feed["sort"])
                signature = json.dumps([str(item.get("id")) for item in rows])
                if rows and stream["previous"] == signature:
                    raise RuntimeError("ONE 接口重复返回同一页，请稍后重试")
                stream["previous"] = signature
                stream["queue"] = sorted(rows, key=cmp_to_key(lambda x, y: _cmp(x, y, feed["sort"])))
                stream["at"] = 0
                stream["page"] += 1
                stream["done"] = len(rows) == 0
        chosen = None
        for stream in feed["streams"]:
            if stream["at"] < len(stream["queue"]):
                if chosen is None or _cmp(stream["queue"][stream["at"]], chosen["queue"][chosen["at"]], feed["sort"]) < 0:
                    chosen = stream
        if chosen is None:
            return None
        item = chosen["queue"][chosen["at"]]
        chosen["at"] += 1
        return item

    def _feed_page(self, key, sort_mode, part, page, size):
        feed = self._feeds.get(key)
        if feed is None or page <= 1:
            feed = {"items": [], "seen": set(), "off": 0, "empty": 0, "done": False, "cover": "",
                    "month_found": 0, "sort": sort_mode,
                    "streams": [{"model": m, "page": 1, "queue": [], "at": 0, "done": False, "previous": ""}
                                for m in VIDEO_MODELS]}
            self._feeds[key] = feed
        need = page * size
        while len(feed["items"]) < need and not feed["done"] and feed["off"] < PAGE_LIMIT:
            article = self._next_article(feed)
            if article is None:
                feed["empty"] = 0 if feed["month_found"] else feed["empty"] + 1
                feed["month_found"] = 0
                feed["off"] += 1
                feed["streams"] = [{"model": m, "page": 1, "queue": [], "at": 0, "done": False, "previous": ""}
                                   for m in VIDEO_MODELS]
                if feed["empty"] >= 8:
                    feed["done"] = True
                continue
            feed["month_found"] += 1
            if part and self._classify_part(article) != part:
                continue
            vod_id = str(article.get("id"))
            if vod_id in feed["seen"]:
                continue
            cover = self._best_image(article)
            if not feed["cover"] and cover:
                feed["cover"] = cover
            vod = self._vod_item(article, feed["cover"] if part else "")
            month = month_label(feed["off"]) + (" 热门" if sort_mode == "like_number" else "")
            vod["vod_remarks"] = month + " · " + vod["vod_remarks"]
            feed["seen"].add(vod_id)
            feed["items"].append(vod)
        return feed["items"][(page - 1) * size: page * size]

    def _vod_item(self, a, cover_fallback=""):
        vod_id = str(a.get("id"))
        title = str(pick(a.get("title"), a.get("video_name"), "ONE #" + vod_id))
        live = False
        match = re.match(r"^\[(ONE\s*直播[^\]]*)\]\s*", title, re.I)
        if match:
            title = title[match.end():].strip()
            live = True
        bits = ["直播回放" if live else _model_name(a.get("model_id"))]
        if a.get("author"):
            bits.append(clean(a.get("author")))
        if a.get("published_at"):
            bits.append(str(a.get("published_at"))[:10])
        if a.get("views"):
            bits.append("观看 %s" % a["views"])
        if a.get("like_number"):
            bits.append("赞 %s" % a["like_number"])
        if str(a.get("size") or "").strip():
            bits.append(str(a["size"]).strip())
        seconds = duration_seconds(a)
        if seconds:
            bits.append(seconds_to_text(seconds))
        return {
            "vod_id": vod_id,
            "vod_name": title or ("ONE #" + vod_id),
            "vod_pic": self._best_image(a) or cover_fallback,
            "vod_remarks": " · ".join(bits),
            "vod_content": clean(pick(a.get("description"), a.get("subtitle"))),
        }

    # ==================== 宿主接口 ====================

    def homeContent(self, filter):
        result = {"class": [dict(item) for item in CATEGORIES], "filters": {}, "list": []}
        try:
            result["list"] = self._feed_page("newest", "published_at", "", 1, ONE_PAGE_SIZE)
        except Exception:
            result["list"] = []
        return result

    def homeVideoContent(self):
        try:
            return {"list": self._feed_page("newest", "published_at", "", 1, ONE_PAGE_SIZE)}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or "newest")
        page = max(1, _int(pg, 1))
        if tid == "live":
            self.bootstrap()
            rows = self._call("article/search", {"keyword": "ONE直播", "model_id": 0,
                                                 "series_category": 0, "page": page, "size": ONE_PAGE_SIZE})
            if not isinstance(rows, list):
                raise RuntimeError("回放目录格式无效")
            vods = [self._vod_item(item) for item in rows if isinstance(item, dict)]
        elif tid == "hot":
            vods = self._feed_page("hot", "like_number", "", page, ONE_PAGE_SIZE)
        elif tid in PARTITIONS and tid != "live":
            vods = self._feed_page(tid, "published_at", tid, page, ONE_PAGE_SIZE)
        else:
            vods = self._feed_page("newest", "published_at", "", page, ONE_PAGE_SIZE)
        return {
            "page": page,
            "pagecount": page + 1 if len(vods) >= ONE_PAGE_SIZE else page,
            "limit": ONE_PAGE_SIZE,
            "total": len(vods),
            "list": vods,
        }

    def _article(self, vod_id):
        vod_id = str(vod_id or "").strip()
        if not re.match(r"^\d+$", vod_id):
            raise RuntimeError("内容标识无效")
        cached = self._details.get(vod_id)
        if cached and time.time() - cached[0] < 900:
            return cached[1]
        self.bootstrap()
        data = self._call("article/detail", {"id": vod_id})
        if not isinstance(data, dict) or not data:
            raise RuntimeError("内容不存在")
        self._details[vod_id] = (time.time(), data)
        while len(self._details) > 80:
            self._details.pop(min(self._details, key=lambda k: self._details[k][0]), None)
        return data

    def _episodes(self, a):
        collection = a.get("collection_list")
        if isinstance(collection, list) and collection:
            seen = set()
            episodes = []
            for item in collection:
                if not isinstance(item, dict):
                    continue
                ep_id = str(item.get("id") or "").strip()
                if not re.match(r"^\d+$", ep_id) or ep_id in seen:
                    continue
                seen.add(ep_id)
                name = clean(item.get("video_name") or item.get("title")) or ("第 %d 场" % (len(episodes) + 1))
                episodes.append((name, ep_id))
            if episodes:
                return episodes
        lines = self._video_lines(a)
        if lines:
            return [("预览" if self._preview_only(a) else "正片", str(a.get("id") or ""))]
        return []

    def detailContent(self, ids):
        vod_id = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        if isinstance(vod_id, str) and "," in vod_id:
            vod_id = vod_id.split(",")[0]
        a = self._article(vod_id)
        title = str(pick(a.get("title"), a.get("video_name"), "ONE #" + str(a.get("id"))))
        match = re.match(r"^\[(ONE\s*直播[^\]]*)\]\s*", title, re.I)
        if match:
            title = title[match.end():].strip()
        bits = [_model_name(a.get("model_id"))]
        if a.get("author"):
            bits.append(clean(a.get("author")))
        if a.get("published_at"):
            bits.append(str(a.get("published_at"))[:10])
        if a.get("views"):
            bits.append("观看 %s" % a["views"])
        if a.get("like_number"):
            bits.append("赞 %s" % a["like_number"])
        seconds = duration_seconds(a)
        if seconds:
            bits.append(seconds_to_text(seconds))
        episodes = self._episodes(a)
        path = a.get("video_download") or a.get("video_file") or a.get("preview_video") or ""
        ranked = self._probe(path) if (episodes and path) else []
        from_groups, url_groups = [], []
        for index in range(max(1, min(5, len(ranked)))):
            from_groups.append("ONE" if index == 0 else "ONE%d" % (index + 1))
            url_groups.append("#".join("%s$%s|%d" % (name.replace("$", " ").replace("#", " "), ep_id, index)
                                       for name, ep_id in episodes))
        play_url = "$$$".join(url_groups)
        vod = {
            "vod_id": str(a.get("id")),
            "vod_name": title or ("ONE #" + str(a.get("id"))),
            "vod_pic": self._best_image(a),
            "vod_remarks": " · ".join(b for b in bits if b),
            "vod_content": clean(pick(a.get("description"), a.get("subtitle"), " · ".join(bits))),
            "vod_play_from": "$$$".join(from_groups) or "ONE",
            "vod_play_url": play_url or ("正片$" + str(a.get("id"))),
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg=1):
        keyword = str(key or "").strip()
        if not keyword:
            return {"list": []}
        page = max(1, _int(pg, 1))
        self.bootstrap()
        rows = self._call("article/search", {"keyword": keyword, "model_id": 0,
                                             "series_category": 0, "page": page, "size": ONE_PAGE_SIZE})
        if not isinstance(rows, list):
            raise RuntimeError("搜索格式无效")
        return {"list": [self._vod_item(item) for item in rows if isinstance(item, dict)]}

    def playerContent(self, flag, idx, vipFlags=None):
        raw = str(idx or "").strip()
        vod_id, _, index_text = raw.partition("|")
        vod_id = vod_id.split("#")[0].strip()
        index = _int(index_text, 0)
        a = self._article(vod_id)
        path = a.get("video_download") or a.get("video_file") or a.get("preview_video") or ""
        hosts = self._probe(path) if path else self._video_hosts()
        lines = self._video_lines(a, hosts)
        seen = set()
        usable = []
        for line in lines:
            url = line["url"]
            if not url or url in seen or "/encry/" in url:
                continue
            seen.add(url)
            usable.append(line)
        if not usable:
            return {"parse": 1, "url": "", "header": "", "playUrl": "", "format": "",
                    "jx": 0}
        line = usable[0]
        if index:
            wanted = "· 线路 %d" % (index + 1)
            for candidate in usable:
                if wanted in candidate["name"]:
                    line = candidate
                    break
        return {
            "parse": 0,
            "jx": 0,
            "url": line["url"],
            "header": json.dumps({"User-Agent": UA}, ensure_ascii=False),
            "playUrl": "",
            "format": "m3u8" if re.search(r"\.m3u8(\?|$)", line["url"], re.I) else ("mp3" if line["name"].find("音频") >= 0 else "mp4"),
        }

    # ==================== 本地 CLI ====================

    def _print(self, value):
        sys.stdout.write(json.dumps(value, ensure_ascii=False, indent=1) + "\n")


def _cli(argv):
    spider = Spider()
    command = argv[1] if len(argv) > 1 else "home"
    arg = argv[2] if len(argv) > 2 else ""
    if command == "home":
        spider._print(spider.homeContent(True))
    elif command == "list":
        tid = arg or "newest"
        page = argv[3] if len(argv) > 3 else "1"
        spider._print(spider.categoryContent(tid, page, True, {}))
    elif command == "search":
        spider._print(spider.searchContent(arg, False, argv[3] if len(argv) > 3 else 1))
    elif command == "detail":
        spider._print(spider.detailContent([arg]))
    elif command == "play":
        spider._print(spider.playerContent("ONE", arg))
    elif command == "raw":
        spider._print(spider._article(arg))
    else:
        sys.stderr.write("用法: python3 one.py [home|list <分类> [页]|search <关键词>|detail <id>|play <id>|raw <id>]\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
