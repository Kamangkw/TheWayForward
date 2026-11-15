# -*- coding: utf-8 -*-
# 直播电视（稳定源）— 映匣 Yingxia TVBox Python 爬虫
# 由 Rex 模组直播电视稳定源 v1.4.18（id tv.live.stable）转写，逻辑照搬。
# 显示文字全简体中文；明文不加密；纯 stdlib + requests，不用 cryptography。
# 没有 Worker：封面直接给原址或走 wsrv，不走 Worker /poster、/logos、/img。
# v1.4.18.5-fix1（2026-11-15，基于 v1.4.18.5 实测修串台）：① URL 交叉去重——同一归一化 URL 被标成
# 2–3 个不同台时，先看 URL path 里的 CCTV 身份 token（cctv4k/8k/5p/cctvN），再按票数、来源顺序
# 定它归谁，输家条目丢弃（同一条流不丢，只是不再挂错台名）；4+ 键共用的门户 URL 不仲裁。
# ② 纪实科教 8K 例外改后缀命中：北京纪实科教8K 也 HOLD，不再并入北京纪实科教。
# ③ 同流 URL 实证别名 +5 对：CETV-3→中国教育3、文化精品→央视精品、TVB亚洲→TVBS-Asia、
# 福建海峡卫视→海峡卫视、斯诺克专场→斯诺克（CHC高清电影证据不足，HOLD，靠 URL 仲裁）。
# v1.4.18.5（2026-11-15）：去重键 v3（65 组逐组核对：64 并 / 1 不并，并后 2709 台）——
# 归一化加 5 条：去 cctv 前缀（数字紧跟的保留：cctv4k/5+/16）、去 leading 中央新影、去尾台、
# newstv→newtv、4k/8k 进画质后缀（cctv4k/8k 本身保留）；人工别名 +18 对（Jade→TVB翡翠台，
# 目标必须是合并后 canonical 键）；LOGO_FALLBACK 改键 18 条；_norm_url 剥默认端口
# （https:443/http:80，河北组同流 :443/无端口并线）；lk 再记 v2 键（v2 收藏不断链）。
# 去芜存菁：主线取评分最高线，其余好线当备用；坏线/重复线在 _group_channels 里已去。
# 纪实科教 8K 不并（同源分列 + 台标 distinct + 8K 可能独立台，待手机确认）。
# v1.4.18.4（2026-11-15）：去重键 v2（繁简+画质后缀+CCTV 描述+中英别名）+ 15 个死 host 排除 + URL 归一化去重；旧收藏连结靠 lk 兼容。
# v1.4.18（2026-11-14）：来源诊断整段去掉；其余与 v1.4.17 相同。
# 港澳台、台湾已删除（港澳移到单独模组）；3 台大陆有线台回地方第 10 季。

from base.spider import Spider as BaseSpider

import concurrent.futures
import re
import threading
import time
import urllib.parse
from urllib.parse import quote, unquote

import requests

VERSION = "1.4.18.5-fix1"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
PREFIX = "livestable:"
PAGE_SIZE = 100
MAX_LINES = 10
SOURCE_TIMEOUT = (5, 12)
AD_CHECK_TIMEOUT = 5
AD_CHECK_TTL = 600
AD_CHECK_UNKNOWN_TTL = 60

# 数据表：全部逐字取自直播电视稳定源 v1.4.18 JS 原文（抽取脚本 /tmp/extract_tv_data.py）。

SOURCES = [
 {
  "key": "hujingguang-cn",
  "name": "hujingguang",
  "url": "https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/cnTV_AutoUpdate.m3u8",
  "type": "m3u"
 },
 {
  "key": "bestfan-cctv",
  "name": "best-fan",
  "url": "https://raw.githubusercontent.com/best-fan/iptv-sources/main/cn_cctv.m3u8",
  "type": "m3u"
 },
 {
  "key": "bestfan-province",
  "name": "best-fan",
  "url": "https://raw.githubusercontent.com/best-fan/iptv-sources/main/cn_province.m3u8",
  "type": "m3u"
 },
 {
  "key": "iptvorg-cn",
  "name": "iptv-org",
  "url": "https://iptv-org.github.io/iptv/countries/cn.m3u",
  "type": "m3u"
 },
 {
  "key": "iptvorg-hk",
  "name": "iptv-org",
  "url": "https://iptv-org.github.io/iptv/countries/hk.m3u",
  "type": "m3u"
 },
 {
  "key": "iptvorg-tw",
  "name": "iptv-org",
  "url": "https://iptv-org.github.io/iptv/countries/tw.m3u",
  "type": "m3u"
 },
 {
  "key": "fanmingming",
  "name": "范明明",
  "url": "https://live.fanmingming.com/tv/m3u/index.m3u",
  "type": "m3u"
 },
 {
  "key": "zbds",
  "name": "zbds",
  "url": "https://live.zbds.top/tv/iptv4.m3u",
  "type": "m3u"
 },
 {
  "key": "niubihu",
  "name": "niubihu",
  "url": "https://raw.githubusercontent.com/niubihu1/tvbox/main/live.txt",
  "type": "txt"
 },
 {
  "key": "yang-live",
  "name": "yanghanhanyingshi",
  "url": "https://raw.githubusercontent.com/yanghanhanyingshi/iptv/main/live.m3u",
  "type": "m3u"
 },
 {
  "key": "tvapi-result",
  "name": "TVAPI",
  "url": "https://raw.githubusercontent.com/YellowSun-FED/TVAPI/master/output/result.m3u",
  "type": "m3u"
 },
 {
  "key": "suxuang-ipv4",
  "name": "suxuang",
  "url": "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
  "type": "m3u"
 },
 {
  "key": "bestfan-all",
  "name": "best-fan",
  "url": "https://raw.githubusercontent.com/best-fan/iptv-sources/main/cn_all.m3u8",
  "type": "m3u"
 },
 {
  "key": "imdazui-china",
  "name": "imDazui",
  "url": "https://raw.githubusercontent.com/imDazui/Tvlist-awesome-m3u-m3u8/master/m3u/china.m3u",
  "type": "m3u"
 },
 {
  "key": "ngo5-ipv4",
  "name": "ngo5",
  "url": "https://raw.githubusercontent.com/ngo5/IPTV/main/m3u/ipv4.m3u",
  "type": "m3u"
 },
 {
  "key": "iptvorg-zho",
  "name": "iptv-org",
  "url": "https://iptv-org.github.io/iptv/languages/zho.m3u",
  "type": "m3u"
 },
 {
  "key": "fanmingming-itv",
  "name": "范明明",
  "url": "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/itv.m3u",
  "type": "m3u"
 },
 {
  "key": "frankwuzp-cn",
  "name": "frankwuzp",
  "url": "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/tv-ipv4-cn.m3u",
  "type": "m3u"
 },
 {
  "key": "frankwuzp-2202",
  "name": "frankwuzp",
  "url": "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/tv-ipv4-2202.m3u",
  "type": "m3u"
 }
]

# 坏 host（广告／已死 host 的流不进清单；v1.4.18.4 补 15 个 2026-11-15 沙盒探测确认死的：
# 404 全灭：58.248.112.205:8006、cdn6.bkpcp.top、mgtv.ottiptv.cc、i.mjh.nz；
# 连线全拒、0 条通：124.221.146.169、jxcbn.ws-cdn.gitv.tv、dsj.motem.top、
# iptv.666230.xyz、mursor.ottiptv.cc、live.nbs.cn、www.lizhinas.top、
# api.kkitv.itv888.vip、cc06.tv12.xyz、qxlmlive.cbg.cn、zby.130519.xyz。
# 不删：itv.cmvideo.cn（403 是沙盒 IP 问题，手机能播）、IPv6 host（沙盒连不上）、
# 超时 host（慢不是死）、403 host（可能要 Referer）。
BAD_HOSTS = ["264788.xyz", "freetv.fun", "metshop.top", "cttv.vip", "tvbus.cc",
             "124.221.146.169", "58.248.112.205", "jxcbn.ws-cdn.gitv.tv",
             "dsj.motem.top", "iptv.666230.xyz", "mursor.ottiptv.cc",
             "live.nbs.cn", "www.lizhinas.top", "cdn6.bkpcp.top",
             "mgtv.ottiptv.cc", "api.kkitv.itv888.vip", "i.mjh.nz",
             "cc06.tv12.xyz", "qxlmlive.cbg.cn", "zby.130519.xyz"]
WSRV_BAD_HOSTS = ["tb.zbds.top", "epg.iill.top", "epg.51zmt.top", "epg.pw"]
TAIWAN_KEYS = ["台灣", "台湾", "taiwan", "中視", "中视", "ctv", "台視", "台视", "ttv", "華視", "华视", "cts", "公視", "公视", "pts", "民視", "民视", "ftv", "中天", "cti", "東森", "东森", "ebc", "緯來", "纬来", "videoland", "八大", "gtv", "年代", "三立", "sanlih", "客家", "hakka", "原住民", "大愛", "大爱", "daai", "人間衛視", "人间卫视", "bltv", "好消息", "goodtv", "tvbs", "momo", "etmall", "suprememaster", "dalitv"]
GANGAO_KEYS = ["香港", "澳門", "澳门", "澳亞", "澳亚", "澳视", "鳳凰衛視", "凤凰卫视", "鳳凰中文台", "凤凰中文台", "鳳凰資訊台", "凤凰资讯台", "鳳凰香港台", "凤凰香港台", "鳳凰電影台", "凤凰电影台", "鳳凰美洲台", "凤凰美洲台", "鳳凰歐洲台", "凤凰欧洲台", "翡翠", "明珠台", "無綫", "无线", "有線", "有线", "亞視", "亚视", "tvb", "rthk", "rhk", "hoy", "viutv", "viu", "now新聞", "nowtv", "nownews", "hongkong", "phoenix", "jade", "celestial", "asiandrama", "meiah", "petclub", "鳳凰資訊", "凤凰资讯", "鳳凰中文", "凤凰中文", "鳳凰電影", "凤凰电影", "鳳凰香港", "凤凰香港", "tdm", "macau", "macao", "oumun", "蓮花", "莲花"]
MACAU_KEYS = ["澳门", "澳門", "澳视", "澳視", "莲花", "蓮花", "澳亚", "澳亞", "tdm", "macau", "macao", "oumun"]
MAINLAND_CABLE_NAMES = ["石景山有线", "郸城有线频道", "清丰有线频道"]
SEASON_NAMES = ["", "央视", "卫视", "新闻", "体育", "影视", "综艺", "少儿", "教育", "纪实", "地方", "熊猫", "香港", "澳门"]
SEASON_ORDER = [3, 4, 5, 6, 7, 8, 11, 9]
AD_MARKERS = ["cue-out", "scte-35", "scte35"]
CAT_TITLE = {"cctv": "央视频道", "weishi": "卫视频道", "gangtai": "港澳", "other": "地方/其他", "all": "全部直播"}

_FT2JT_FT = "愛龍鳳雲國學頭發裏後個們說話時間來樂熱聽讀書寫買賣車門開關長舊壞醜對錯進遠淺輕細軟鹹沉淪戀寵總嬌兒媽爸親歡慶貴賤貧窮錢銀寶劍槍鳥魚花樹風雨雷電雪霧夢聲歌舞劇戲視頻導員製品量級類種樣號動靜亂辦辭還過讓驚險雙離斷絕敵戰爭奪權勢嚴厲淚傷尋見臉髮體腦腳懷產這邊麼嗎歲歷壓廣廳廁廚彈彎強歸當錄"
_FT2JT_JT = "爱龙凤云国学头发里后个们说话时间来乐热听读书写买卖车门开关长旧坏丑对错进远浅轻细软咸沉沦恋宠总娇儿妈爸亲欢庆贵贱贫穷钱银宝剑枪鸟鱼花树风雨雷电雪雾梦声歌舞剧戏视频导员制品量级类种样号动静乱办辞还过让惊险双离断绝敌战争夺权势严厉泪伤寻见脸发体脑脚怀产这边么吗岁历压广厅厕厨弹弯强归当录"
_FT2JT_EXTRA = [["聞", "闻"], ["衛", "卫"], ["臺", "台"], ["畫", "画"], ["灣", "湾"], ["貓", "猫"], ["飛", "飞"], ["鏢", "镖"], ["圍", "围"], ["雜", "杂"], ["術", "术"], ["點", "点"], ["財", "财"], ["經", "经"], ["豐", "丰"], ["麗", "丽"], ["寧", "宁"], ["濟", "济"], ["陽", "阳"], ["陰", "阴"], ["龜", "龟"], ["幾", "几"], ["會", "会"], ["機", "机"], ["亞", "亚"], ["歐", "欧"], ["際", "际"], ["綜", "综"], ["藝", "艺"], ["娛", "娱"], ["場", "场"], ["軍", "军"], ["貝", "贝"], ["東", "东"], ["遼", "辽"], ["瀋", "沈"]]

SEASON_KEY_RE = {
 "3": "新聞|新闻|資訊|资讯|cgtn|鳳凰資訊|凤凰资讯|時事|时事|news",
 "4": "體育|体育|足球|籃球|篮球|高爾夫|高尔夫|網球|网球|乒乓|羽毛球|台球|賽車|赛车|健身|奧運|奥运|世界盃|世界杯|運動|运动|搏擊|搏击|拳擊|拳击|電競|电竞|棋牌|象棋|圍棋|围棋|斯諾克|斯诺克|飛鏢|飞镖|英雄聯盟|英雄联盟|sport|football|soccer|basketball|golf|tennis|espn|eurosport|racing|boxing",
 "5": "電影|电影|影院|劇場|剧场|電視劇|电视剧|影視|影视|影片|院線|院线|movie|movies|cinema|film|hbo|celestial",
 "6": "綜藝|综艺|娛樂|娱乐|音樂|音乐|搞笑|相聲|相声|小品|脫口秀|脱口秀|真人秀|選秀|选秀|演唱會|演唱会|歌曲|歌舞|喜劇|喜剧|曲藝|曲艺|戲曲|戏曲|京劇|京剧|越劇|越剧|黃梅戲|黄梅戏|豫劇|豫剧|秦腔|魔術|魔术|雜技|杂技|舞蹈|明星|偶像|music|mtv|comedy|concert",
 "7": "少兒|少儿|兒童|儿童|卡通|動畫|动画|動漫|动漫|兒歌|儿歌|幼兒|幼儿|幼兒園|幼儿园|小朋友|寶貝|宝贝|萌娃|kids|cartoon|disney|nick|boomerang|baby|junior|toon",
 "8": "教育|科教|課堂|课堂|教學|教学|學習|学习|考試|考试|高考|考研|培訓|培训|講座|讲座|公開課|公开课|大學|大学|學院|学院|學校|学校|education|learning",
 "11": "熊貓|熊猫|panda|ipanda|寵物|宠物|萌寵|萌宠",
 "9": "紀實|纪实|紀錄|纪录|探索|發現|发现|歷史|历史|地理|自然|科普|野生|國家地理|国家地理|人文|考古|軍事|军事|國防|国防|兵器|戰爭|战争|紀錄片|纪录片|探險|探险|宇宙|太空|科學|科学|動物世界|动物世界|人與自然|人与自然|discovery|history|nationalgeographic|natgeo|animal|wildlife|nature|science|documentary"
}
SEASON_GROUP_RE = {
 "3": "新聞|新闻|資訊|资讯|news",
 "4": "體育|体育|賽事|赛事|sports",
 "5": "影視|影视|電影|电影|電視劇|电视剧|劇場|剧场|movies",
 "6": "綜藝|综艺|娛樂|娱乐|音樂|音乐|春晚|entertainment",
 "7": "少兒|少儿|兒童|儿童|卡通|動畫|动画",
 "8": "教育|科教",
 "11": "熊貓|熊猫|panda|寵物|宠物|萌寵|萌宠",
 "9": "紀實|纪实|紀錄|纪录"
}

LOGO_FALLBACK = {
 "&flix": "https://dtil.tmsimg.com/assets/GNLZZGG0022J67W.png?lock=720x540",
 "abntv": "https://i.imgur.com/ciAu5ar.png",
 "amc电影": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/AMC%E7%94%B5%E5%BD%B1.png",
 "antv": "https://static.wikia.nocookie.net/logos/images/1/1a/ANTV_2023.png/revision/latest/scale-to-width-down/512?path-prefix=vi",
 "arirangradio": "https://i.imgur.com/dtfiG9k.png",
 "btn": "https://i.imgur.com/2K6qEvh.jpg",
 "cbnnews": "https://i.imgur.com/9f9YMsA.png",
 "央视精品": "https://i.imgur.com/Paig8gG.png",
 "高尔夫网球": "https://i.imgur.com/iqJJTmH.png",
 "cgtn西班牙语": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/CGTN%E8%A5%BF%E7%8F%AD%E7%89%99%E8%AF%AD.png",
 "cgtn阿拉伯语": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/CGTN%E9%98%BF%E6%8B%89%E4%BC%AF%E8%AF%AD.png",
 "cjonstyle": "https://i.imgur.com/JiSfEBv.png",
 "clarity": "https://i.imgur.com/M87kbVk.png",
 "disneyinternational": "https://plain-apac-prod-public.komododecks.com/202609/07/FAoDDiaq0WPescE65173/image.png",
 "dubaione": "https://i.imgur.com/Dj16oKL.png",
 "ebskids": "https://i.imgur.com/62oo8Bx.png",
 "fifa+": "https://upload.wikimedia.org/wikipedia/commons/9/9c/FIFA%2B_%282025%29.svg",
 "fightnetwork": "https://i.imgur.com/vlKPZHR.png",
 "gbnews": "https://upload.wikimedia.org/wikipedia/en/thumb/3/35/GB_News_Logo.svg/960px-GB_News_Logo.svg.png",
 "home&shopping": "https://i.imgur.com/IcexRXG.png",
 "ionplus": "https://upload.wikimedia.org/wikipedia/commons/6/65/Ion_Plus_2024.svg",
 "kbslivecamdokdo": "https://i.imgur.com/7mZnPO5.png",
 "kbsworld": "https://upload.wikimedia.org/wikipedia/commons/9/98/NewsNetLogo2022.png",
 "kctv": "https://i.imgur.com/IHkZpaI.png",
 "lotteonetv": "https://i.imgur.com/bXe7tYE.png",
 "lovenature": "https://tv.lovenature.com/wp-content/uploads/2024/10/LoveNature2024_Logo_full_colour-copy.png",
 "moviesphere": "https://i.imgur.com/0sfk3yp.png",
 "nhtv": "https://i.imgur.com/DfECkgB.png",
 "now新闻": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/NOW%E6%96%B0%E9%97%BB%E5%8F%B0.png",
 "pop": "https://i.imgur.com/STbfHwE.png",
 "shoppingnt": "https://i.imgur.com/BgbJp5X.png",
 "sky": "https://i.imgur.com/RwMmbtD.png",
 "stadium": "https://i.imgur.com/SnZOiER.png",
 "tastemade": "https://i.imgur.com/xP7Ehn8.png",
 "tbs": "https://thumb.wikimedia.org/wikipedia/commons/thumb/2/2c/TBS_2020.svg/960px-TBS_2020.svg.png",
 "tv3": "https://i.imgur.com/sCr0h4N.png",
 "tvbs": "https://i.imgur.com/4RvCHWP.png",
 "tvbs新闻": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/TVBS%E6%96%B0%E9%97%BB.png",
 "tvchosun2": "https://i.imgur.com/Ev5JoBJ.png",
 "wildearth": "https://i.imgur.com/Vhv5gjN.png",
 "wildplanet": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/WILD%20PLANET.png",
 "万源新闻": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E4%B8%87%E6%BA%90%E6%96%B0%E9%97%BB%E7%BB%BC%E5%90%88.png",
 "三立戏剧": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E4%B8%89%E7%AB%8B%E6%88%8F%E5%89%A7.png",
 "三立": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E4%B8%89%E7%AB%8B%E7%BB%BC%E5%90%88.png",
 "三立都会": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E4%B8%89%E7%AB%8B%E9%83%BD%E4%BC%9A.png",
 "上视东方影视": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E4%B8%8A%E8%A7%86%E4%B8%9C%E6%96%B9%E5%BD%B1%E8%A7%86.png",
 "东森戏剧": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E4%B8%9C%E6%A3%AE%E6%88%8F%E5%89%A7.png",
 "中华特产": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E4%B8%AD%E5%8D%8E%E7%89%B9%E4%BA%A7.png",
 "中国教育3": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E4%B8%AD%E5%9B%BD%E6%95%99%E8%82%B23.png",
 "发现之旅": "https://i.imgur.com/2FJfPDx.png",
 "老故事": "https://i.imgur.com/mICAYWt.png",
 "中学生": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E4%B8%AD%E5%AD%A6%E7%94%9F.png",
 "中视": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E4%B8%AD%E8%A7%86.png",
 "乐山新闻": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E4%B9%90%E5%B1%B1%E6%96%B0%E9%97%BB%E7%BB%BC%E5%90%88.png",
 "优优宝贝": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E4%BC%98%E4%BC%98%E5%AE%9D%E8%B4%9D.png",
 "体坛名栏汇": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E4%BD%93%E5%9D%9B%E5%90%8D%E6%A0%8F%E6%B1%87.png",
 "体育休闲": "https://www.tvchinese.net/uploads/tv/sxtv.jpg",
 "公视": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E5%85%AC%E8%A7%86.png",
 "利州": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E5%88%A9%E5%B7%9E%E7%BB%BC%E5%90%88.png",
 "北京纪实科教": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E5%8C%97%E4%BA%AC%E7%BA%AA%E5%AE%9E%E7%A7%91%E6%95%99.png",
 "台视": "https://upload.wikimedia.org/wikipedia/en/thumb/3/32/TTV_2nd_logo.svg/960px-TTV_2nd_logo.svg.png",
 "国学": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E5%9B%BD%E5%AD%A6%E9%A2%91%E9%81%93.png",
 "宿迁新闻": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E5%AE%BF%E8%BF%81%E6%96%B0%E9%97%BB%E7%BB%BC%E5%90%88.png",
 "崇明电视": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E5%B4%87%E6%98%8E%E7%94%B5%E8%A7%86%E5%8F%B0.png",
 "年代新闻": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E5%B9%B4%E4%BB%A3%E6%96%B0%E9%97%BB.png",
 "徐州新闻": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E5%BE%90%E5%B7%9E%E6%96%B0%E9%97%BB%E7%BB%BC%E5%90%88.png",
 "新片放映厅": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E6%96%B0%E7%89%87%E6%94%BE%E6%98%A0%E5%8E%85.png",
 "早期教育": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E6%97%A9%E6%9C%9F%E6%95%99%E8%82%B2.png",
 "最强综艺趴": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E6%9C%80%E5%BC%BA%E7%BB%BC%E8%89%BA%E8%B6%B4.png",
 "民视": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E6%B0%91%E8%A7%86.png",
 "江苏国际": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E6%B1%9F%E8%8B%8F%E5%9B%BD%E9%99%85.png",
 "江苏城市": "https://www.tvchinese.net/uploads/tv/jscs.jpg",
 "江苏影视": "https://www.tvchinese.net/uploads/tv/jsys.jpg",
 "江苏综艺": "https://www.tvchinese.net/uploads/tv/jszy.jpg",
 "江西少儿": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E6%B1%9F%E8%A5%BF%E5%B0%91%E5%84%BF.png",
 "涟水": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E6%B6%9F%E6%B0%B4%E7%BB%BC%E5%90%88.png",
 "深圳少儿": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E6%B7%B1%E5%9C%B3%E5%B0%91%E5%84%BF.png",
 "环球旅游": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E7%8E%AF%E7%90%83%E6%97%85%E6%B8%B8.png",
 "生态环境": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E7%94%9F%E6%80%81%E7%8E%AF%E5%A2%83.png",
 "福建海峡卫视": "https://i.imgur.com/oNM7aiL.png",
 "经典动画大集合": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E7%BB%8F%E5%85%B8%E5%8A%A8%E7%94%BB%E5%A4%A7%E9%9B%86%E5%90%88.png",
 "经典香港电影": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E7%BB%8F%E5%85%B8%E9%A6%99%E6%B8%AF%E7%94%B5%E5%BD%B1.png",
 "财富天下": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E8%B4%A2%E5%AF%8C%E5%A4%A9%E4%B8%8B.png",
 "赛事最经典": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E8%B5%9B%E4%BA%8B%E6%9C%80%E7%BB%8F%E5%85%B8.png",
 "车迷": "https://i.imgur.com/Qdmw24h.png",
 "重庆少儿": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E9%87%8D%E5%BA%86%E5%B0%91%E5%84%BF.png",
 "重庆新闻": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E9%87%8D%E5%BA%86%E6%96%B0%E9%97%BB.png",
 "黎城": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/%E9%BB%8E%E5%9F%8E%E7%BB%BC%E5%90%88.png",
 "tvb明珠": "https://i.imgur.com/UPdcMkW.png",
 "dw": "https://live.fanmingming.cn/tv/DW.png",
 "农林卫视": "https://i.imgur.com/j4yT8ff.png",
 "凉山彝语": "https://www.tvchinese.net/uploads/tv/liangshantv.jpg",
 "奇妙电视": "https://static.wikia.nocookie.net/logopedia/images/7/73/Fantastic_Television.svg.png",
 "安顺公共": "https://www.tvchinese.net/uploads/tv/anshun.jpg",
 "潮州公共": "https://i.imgur.com/8YIrgB7.png",
 "潮州": "https://i.imgur.com/S7GlCi4.png",
 "点掌财经": "https://i.imgur.com/601hQsF.png",
 "福建东南卫视": "https://i.imgur.com/btIeqQc.png",
 "astroaec": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/AstroAEC.png",
 "astroaod": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/AstroAOD.png",
 "astroqj": "https://i.imgur.com/vmpUnz9.png",
 "astro欢喜": "https://i.imgur.com/fwTP9PS.png",
 "cctv4": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/CCTV-4.png",
 "cctv5+": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/CCTV-5%2B.png",
 "cctv7": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/CCTV-7.png",
 "cgnt新闻": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/CGTN.png",
 "cgtn外语纪录": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/CGTNDOCUMENTARY.png",
 "ch8": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/Channel%208%20HD.png",
 "cpbc": "https://i.imgur.com/Psy4IBg.png",
 "ebs+2": "https://i.imgur.com/pllIMGi.png",
 "ebs1": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/EBS.png",
 "ebse": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/EBS.png",
 "ebsi": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/EBS.png",
 "ewtnafricaasia": "https://i.imgur.com/sua70RO.png",
 "ewtnasiapacific": "https://i.imgur.com/sua70RO.png",
 "hoy78": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/HOY78.png",
 "hoy资讯": "https://i.imgur.com/LNokYLQ.png",
 "江苏卫视": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/Jiangsu.png",
 "kctv광주ch05": "https://i.imgur.com/IHkZpaI.png",
 "live三立": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/SET1.png",
 "mbcandong": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/MBC.png",
 "mbcchuncheon": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/MBC.png",
 "mbcjeju": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/MBC.png",
 "mbcmokpo": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/MBC.png",
 "nownews": "https://i.imgur.com/m6tWo9p.png",
 "rthk31": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/RHK31.png",
 "rhk32": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/RHK32.png",
 "sbscjb": "https://i.imgur.com/zVunmpQ.png",
 "深圳卫视": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/Shenzhen.png",
 "taiwanplus": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/TAIWANPLUS.png",
 "tvbplus": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/TVB%20Plus.png",
 "tvb财经资讯": "https://i.imgur.com/Fkkp7x7.png",
 "tvn1": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/TVN.png",
 "tvn2": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/TVN.png",
 "viu6": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/VIU6.png",
 "viutv1": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/69/ViuTV_logo.svg/960px-ViuTV_logo.svg.png",
 "wionnews": "https://dtil.tmsimg.com/assets/s144087_ld_h15_aa.png?lock=720x540",
 "东森洋片": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/EBC4.png",
 "东森电影": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/EBC3.png",
 "东森": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/EBC1.png",
 "东森超视": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/EBC2.png",
 "八度空间": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/8TV.png",
 "凤凰卫视": "https://raw.githubusercontent.com/wanglindl/TVlogo/main/img/Phoenix1.png",
 "咪咕视频": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/migushipin.png",
 "咪咕视频4k2": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/migushipin.png",
 "天映": "https://i.imgur.com/Mb5ssnu.png",
 "安顺新闻": "https://www.tvchinese.net/uploads/tv/anshun.jpg",
 "房山电视": "https://i.imgur.com/WJeOjFE.png",
 "无线新闻": "https://i.imgur.com/Gwij0Fj.png",
 "无线星河": "https://i.imgur.com/uf0bYFm.png",
 "有线新闻": "https://i.imgur.com/Xyxwrkr.png",
 "民视影剧": "https://i.imgur.com/q8ahtbT.png",
 "澳视卫星": "https://i.imgur.com/iIfZsD6.png",
 "澳门体育": "https://i.imgur.com/AsWLf8S.png",
 "澳门综艺": "https://i.imgur.com/7ml2bfx.png",
 "爱奇艺": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/IQIYI.png",
 "白城新闻": "https://www.tvchinese.net/uploads/tv/baicheng.jpg",
 "福州影视": "https://i.imgur.com/xRP80XS.png",
 "美嘉购物": "https://www.tvchinese.net/uploads/tv/mjgw.jpg",
 "翡翠台backup": "https://raw.githubusercontent.com/wanglindl/TVlogo/main/img/TVB1.png",
 "韩国ebs1": "https://raw.githubusercontent.com/mytv-android/myTVlogo/main/img/EBS.png",
 "韩国ebs2": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/db/EBS_2TV_Logo.svg/960px-EBS_2TV_Logo.svg.png"
}

REMOVED_KEYS = {"港台电视31": 1, "港台电视32": 1, "台湾+": 1, "龙华洋片": 1, "龙华经典": 1, "龙华戏剧": 1, "龙华日韩": 1}

DEAD_LOGO_URLS = {
 "https://live.fanmingming.cn/tv/TVB生活台.png": 1,
 "https://live.fanmingming.cn/tv/TVB娱乐新闻台.png": 1,
 "https://live.fanmingming.cn/tv/NOWNEWS.png": 1,
 "https://live.fanmingming.cn/tv/澳门体育.png": 1,
 "https://live.fanmingming.cn/tv/澳门综艺.png": 1,
 "https://live.fanmingming.cn/tv/民视影剧台.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/HOY TV.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/澳视澳门.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/台湾+.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/翡翠台 backup.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/HOY资讯台.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/VIUTV1.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/有线新闻.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/凤凰卫视.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/TVB星河.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/纬来育乐.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/东森综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/东森超视.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/东森电影.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/纬来电影.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/东森洋片.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/三立新闻.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/凤凰香港.png": 1,
 "https://live.fanmingming.cn/tv/HOY TV.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/凤凰卫视台.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/无线新闻.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/无线星河.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/TVB Plus.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/澳视卫星.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/咪咕视频4K.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/咪咕视频4K-2.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/RHK 31.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/RHK 32.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/Viu6.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/华丽翡翠台.png": 1,
 "https://gitee.com/suxuang/TVlogo/raw/main/img/千禧经典.png": 1,
 "https://gitee.com/suxuang/TVlogo/raw/main/img/HOY78.png": 1,
 "https://gitee.com/suxuang/TVlogo/raw/main/img/ASTROAOD.png": 1,
 "https://live.fanmingming.cn/tv/八度空间.png": 1,
 "https://live.fanmingming.cn/tv/CH5.png": 1,
 "https://live.fanmingming.cn/tv/CH8.png": 1,
 "https://live.fanmingming.cn/tv/CHU.png": 1,
 "https://live.fanmingming.cn/tv/千禧经典台.png": 1,
 "https://live.fanmingming.cn/tv/天映频道.png": 1,
 "https://live.fanmingming.cn/tv/Astro AEC.png": 1,
 "https://live.fanmingming.cn/tv/爱奇艺.png": 1,
 "https://live.fanmingming.cn/tv/Astro QJ.png": 1,
 "https://live.fanmingming.cn/tv/Astro欢喜台.png": 1,
 "https://live.fanmingming.cn/tv/亚洲武侠.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/无线新闻.png": 1,
 "https://isus.cc/share/logo/TVBPlus.png": 1,
 "https://live.fanmingming.cn/tv/澳视卫星.png": 1,
 "https://live.fanmingming.cn/tv/华丽翡翠.png": 1,
 "https://live.fanmingming.cn/tv/Astro AOD.png": 1,
 "https://live.fanmingming.cn/tv/TVB Plus.png": 1,
 "https://live.fanmingming.cn/tv/华丽翡翠台.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/CCTV中学生.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/NEWTV中国功夫.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/NEWTV武搏世界.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/NEWTV精品记录.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/iNews新闻台.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/上视纪实人文.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/乐游.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/乐游频道.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/四海钓鱼.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/河北4K.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/生活时尚.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/睛彩广场.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/睛彩竞技.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/黑龙江视.png": 1,
 "https://gitee.com/suxuang/logo/raw/master/mylogo/龙华电影.png": 1,
 "https://live.fanmingming.cn/tv/七台河民生社教.png": 1,
 "https://live.fanmingming.cn/tv/三明综合.png": 1,
 "https://live.fanmingming.cn/tv/上海卫视.png": 1,
 "https://live.fanmingming.cn/tv/东莞生活资讯.png": 1,
 "https://live.fanmingming.cn/tv/中华功夫.png": 1,
 "https://live.fanmingming.cn/tv/乐家购物.png": 1,
 "https://live.fanmingming.cn/tv/北京淘BABY.png": 1,
 "https://live.fanmingming.cn/tv/北京萌宠TV.png": 1,
 "https://live.fanmingming.cn/tv/北京超清.png": 1,
 "https://live.fanmingming.cn/tv/十堰新闻.png": 1,
 "https://live.fanmingming.cn/tv/南平综合.png": 1,
 "https://live.fanmingming.cn/tv/宁德新闻综合.png": 1,
 "https://live.fanmingming.cn/tv/平潭综合.png": 1,
 "https://live.fanmingming.cn/tv/德阳公共.png": 1,
 "https://live.fanmingming.cn/tv/德阳新闻综合.png": 1,
 "https://live.fanmingming.cn/tv/搜狐剧场.png": 1,
 "https://live.fanmingming.cn/tv/攀枝花新闻综合.png": 1,
 "https://live.fanmingming.cn/tv/昭化综合.png": 1,
 "https://live.fanmingming.cn/tv/沙湾融媒.png": 1,
 "https://live.fanmingming.cn/tv/河北公共.png": 1,
 "https://live.fanmingming.cn/tv/河北影视.png": 1,
 "https://live.fanmingming.cn/tv/河北杂技.png": 1,
 "https://live.fanmingming.cn/tv/河北睛彩.png": 1,
 "https://live.fanmingming.cn/tv/河北经济.png": 1,
 "https://live.fanmingming.cn/tv/河南戏曲.png": 1,
 "https://live.fanmingming.cn/tv/河源公共.png": 1,
 "https://live.fanmingming.cn/tv/河源综合.png": 1,
 "https://live.fanmingming.cn/tv/泉州新闻综合.png": 1,
 "https://live.fanmingming.cn/tv/漳州新闻综合.png": 1,
 "https://live.fanmingming.cn/tv/睛彩中原.png": 1,
 "https://live.fanmingming.cn/tv/石家庄城市服务.png": 1,
 "https://live.fanmingming.cn/tv/石家庄文化娱乐.png": 1,
 "https://live.fanmingming.cn/tv/石家庄新闻综合.png": 1,
 "https://live.fanmingming.cn/tv/福州新闻综合.png": 1,
 "https://live.fanmingming.cn/tv/福建乡村振兴公共.png": 1,
 "https://live.fanmingming.cn/tv/移动戏曲.png": 1,
 "https://live.fanmingming.cn/tv/绵阳科技.png": 1,
 "https://live.fanmingming.cn/tv/绵阳综合.png": 1,
 "https://live.fanmingming.cn/tv/莆田综合.png": 1,
 "https://live.fanmingming.cn/tv/西安新闻.png": 1,
 "https://live.fanmingming.cn/tv/西安都市.png": 1,
 "https://live.fanmingming.cn/tv/象视界.png": 1,
 "https://live.fanmingming.cn/tv/赣州公共.png": 1,
 "https://live.fanmingming.cn/tv/赣州教育.png": 1,
 "https://live.fanmingming.cn/tv/赣州新闻.png": 1,
 "https://live.fanmingming.cn/tv/辽宁体育.png": 1,
 "https://live.fanmingming.cn/tv/辽宁影视剧.png": 1,
 "https://live.fanmingming.cn/tv/辽宁教育青少.png": 1,
 "https://live.fanmingming.cn/tv/长宁综合.png": 1,
 "https://live.fanmingming.cn/tv/长沙女性.png": 1,
 "https://live.fanmingming.cn/tv/长沙政法.png": 1,
 "https://live.fanmingming.cn/tv/陕西秦腔.png": 1,
 "https://live.fanmingming.cn/tv/陕西银龄.png": 1,
 "https://live.fanmingming.cn/tv/鹿泉二套.png": 1,
 "https://live.fanmingming.cn/tv/龙岩综合.png": 1,
 "https://live.fanmingming.com/tv/NEWTV武博世界.png": 1,
 "https://live.fanmingming.com/tv/NEWTV精品综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/CN卡通.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/JJ斗地主.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/NewTV动作电影.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/NewTV惊悚悬疑.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/七龙珠.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/三国演义.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/上海新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/上海滩.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/上海纪实.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/东海新闻.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/中华小当家.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/临颍综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/义马新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/五台综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/仙剑奇侠传.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/任丘文娱.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/佳木斯新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/偃师新闻.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/光山综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/兰考新闻.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/内乡综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/内蒙经济.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/内黄综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/北京卡酷少儿.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/北京科教.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/北海新闻.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/北海经济科教.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/南京信息.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/南京十八.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/南京娱乐.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/南京少儿.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/南京生活.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/南通新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/卡酷动画.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/卫辉综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/叙永综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/叶县.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/吉林生活.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/吉林都市.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播10.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播11.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播12.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播13.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播14.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播15.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播16.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播17.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播18.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播19.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播2.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播20.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播21.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播22.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播23.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播24.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播25.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播26.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播27.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播28.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播29.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播3.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播30.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播31.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播32.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播33.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播34.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播35.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播36.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播37.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播38.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播4.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播5.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播6.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播7.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播8.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/咪咕直播9.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/唐河一套.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/固始综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/天映经典.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/天津体育.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/天津文艺.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/天津新闻.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/天津都市.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/天龙八部.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/娄底综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/宁夏经济.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/宁波TV1.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/宁波TV2.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/宁波TV3.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/宁波TV4.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/安徽导视.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/安顺新闻.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/宜兴新闻.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/宜阳综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/宝丰综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/宝宝动画.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/宾阳综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/宿州公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/宿州新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/宿松新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/宿迁公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/封神榜.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/射雕英雄传.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/少儿动画.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/山东居家购物.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/嵩县综合新闻.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/巩义新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/常州公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/常州生活.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/常州都市.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/开封文化旅游.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/开封新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/徐州公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/徐州新聞綜合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/扬州邗江.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/扶沟综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/数码时代.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/新乡县电视台.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/新县综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/新安新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/新白娘子传奇.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/新蔡综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/方城一套.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/无锡娱乐.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/无锡新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/无锡生活.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/无锡经济.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/无锡都市资讯.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/日照公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/日照新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/日照科教.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/昆明公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/昆明科学教育.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/普陀新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/朝阳新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/杭州导视.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/杭州少体.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/杭州影视.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/杭州明珠.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/杭州生活.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/杭州综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/杭州青少.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/松阳新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/桐柏新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/武乡新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/武汉新闻.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/水浒传.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/汉源综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/汕头文旅.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/江宁新闻.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/江苏体育.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/江苏公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/江苏教育.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/江门侨乡生活.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/江门综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/沁阳新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/沭阳综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/河北少儿科教.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/泌阳新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/泗洪新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/洛阳文旅.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/洛阳科教.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/洛阳综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/济公游记.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/济源电视一套.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/海南自贸.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/涟水电视台综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/涡阳新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/淅川电视.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/淘剧场.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/淘娱乐.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/淘电影.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/淮安影院娱乐.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/淮安新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/淮阴综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/清河新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/渑池新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/温县综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/湖北公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/湖北垄上.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/湖北影视.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/湖北教育.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/湖北生活.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/湖北经视.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/湖北综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/湖南金鹰纪实.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/溧水新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/滁州公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/滁州新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/滁州科教.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/滑县新闻.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/漫画解说.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/潢川综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/潮流音乐.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/濮阳公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/火影忍者.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/灵宝新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/炫动卡通.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/焦作公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/焦作教育.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/焦作综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/爱体育.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/爱动漫.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/爱电竞.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/猫和老鼠.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/甘南综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/甘肃公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/甘肃少儿.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/登封综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/睢宁三农.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/睢宁综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/睢宁资讯.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/石棉综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/祁县新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/福州综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/禹州公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/禹州综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/秦安综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/笑傲江湖.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/筠连综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/经典动漫.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/经典电影.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/茂名公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/茂名综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/菏泽新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/菏泽经济生活.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/蜡笔小新.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/衡山.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/西华综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/西宁生活服务.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/西游记.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/许昌公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/超级体育.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/辽宁经济.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/连云港公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/连云港新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/邓州新闻.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/邯郸公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/郏县综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/郸城新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/鄢陵综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/酒泉综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/金山电视台.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/银川公共.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/银川文体.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/银川生活.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/长沙新闻.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/闯关东.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/陕西农林.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/雅安雨城.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/青州综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/青春动漫.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/青海综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/青神综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/音乐广播.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/项城新闻.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/鹤壁综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/鹤岗新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/鹿泉一套.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/鹿鼎记.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/黄山公共生活.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/黄山新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/黑龙江影视.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/黑龙江新闻法治.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/齐齐哈尔新闻综合.png": 1,
 "https://raw.githubusercontent.com/fanmingming/live/main/tv/龙祥电影.png": 1,
 "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/btvjishi.png": 1,
 "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/cctvyswhjp.png": 1,
 "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/cetv1.png": 1,
 "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/cetv2.png": 1,
 "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/cetv3.png": 1,
 "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/cetv4.png": 1,
 "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/chc.png": 1,
 "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/chcjtyy.png": 1,
 "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/jjkt.png": 1,
 "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/newtvjsdy.png": 1,
 "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/newtvrbjx.png": 1,
 "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/shan1xi.png": 1,
 "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/shanxi.png": 1,
 "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/tvs-2.png": 1,
 "https://raw.githubusercontent.com/frankwuzp/iptv-cn/main/xiamen.png": 1,
 "https://tb.zbds.top/logo/1987年春晚.png": 1,
 "https://tb.zbds.top/logo/1988年春晚.png": 1,
 "https://tb.zbds.top/logo/1989年春晚.png": 1,
 "https://tb.zbds.top/logo/1993年春晚.png": 1,
 "https://tb.zbds.top/logo/1994年春晚.png": 1,
 "https://tb.zbds.top/logo/1995年春晚.png": 1,
 "https://tb.zbds.top/logo/1996年春晚.png": 1,
 "https://tb.zbds.top/logo/2000年春晚.png": 1,
 "https://tb.zbds.top/logo/2001年春晚.png": 1,
 "https://tb.zbds.top/logo/2002年春晚.png": 1,
 "https://tb.zbds.top/logo/2003年春晚.png": 1,
 "https://tb.zbds.top/logo/2004年春晚.png": 1,
 "https://tb.zbds.top/logo/2005年春晚.png": 1,
 "https://tb.zbds.top/logo/2006年春晚.png": 1,
 "https://tb.zbds.top/logo/2007年春晚.png": 1,
 "https://tb.zbds.top/logo/2009年春晚.png": 1,
 "https://tb.zbds.top/logo/2010年春晚.png": 1,
 "https://tb.zbds.top/logo/2013年春晚.png": 1,
 "https://tb.zbds.top/logo/2014年春晚.png": 1,
 "https://tb.zbds.top/logo/2018年春晚.png": 1,
 "https://tb.zbds.top/logo/2025年春晚.png": 1,
 "https://tb.zbds.top/logo/AMC音乐.png": 1,
 "https://tb.zbds.top/logo/七台河新闻综合.png": 1,
 "https://tb.zbds.top/logo/万州三峡移民.png": 1,
 "https://tb.zbds.top/logo/万荣综合.png": 1,
 "https://tb.zbds.top/logo/三明新闻综合.png": 1,
 "https://tb.zbds.top/logo/上虞文化影院.png": 1,
 "https://tb.zbds.top/logo/东丰.png": 1,
 "https://tb.zbds.top/logo/中国村庄.png": 1,
 "https://tb.zbds.top/logo/九台.png": 1,
 "https://tb.zbds.top/logo/云霄综合.png": 1,
 "https://tb.zbds.top/logo/井研综合.png": 1,
 "https://tb.zbds.top/logo/亳州农村.png": 1,
 "https://tb.zbds.top/logo/人与自然.png": 1,
 "https://tb.zbds.top/logo/人在囧途.png": 1,
 "https://tb.zbds.top/logo/人在囧途之泰囧.png": 1,
 "https://tb.zbds.top/logo/人在囧途之港囧.png": 1,
 "https://tb.zbds.top/logo/任丘综合.png": 1,
 "https://tb.zbds.top/logo/伊犁哈萨克.png": 1,
 "https://tb.zbds.top/logo/伊犁经济法制.png": 1,
 "https://tb.zbds.top/logo/伊犁维吾尔.png": 1,
 "https://tb.zbds.top/logo/余姚综合.png": 1,
 "https://tb.zbds.top/logo/余杭未来E.png": 1,
 "https://tb.zbds.top/logo/余杭综合.png": 1,
 "https://tb.zbds.top/logo/倩女幽魂人间道.png": 1,
 "https://tb.zbds.top/logo/倩女幽魂妖魔道.png": 1,
 "https://tb.zbds.top/logo/倩女幽魂道道道.png": 1,
 "https://tb.zbds.top/logo/六安公共.png": 1,
 "https://tb.zbds.top/logo/六安新闻综合.png": 1,
 "https://tb.zbds.top/logo/兴隆综合.png": 1,
 "https://tb.zbds.top/logo/兵团五师双河影.png": 1,
 "https://tb.zbds.top/logo/兵团五师双河新闻综合.png": 1,
 "https://tb.zbds.top/logo/兵团八师石河子新闻综合.png": 1,
 "https://tb.zbds.top/logo/双辽.png": 1,
 "https://tb.zbds.top/logo/双辽综合.png": 1,
 "https://tb.zbds.top/logo/句容党建.png": 1,
 "https://tb.zbds.top/logo/句容影院.png": 1,
 "https://tb.zbds.top/logo/句容生活.png": 1,
 "https://tb.zbds.top/logo/名山综合.png": 1,
 "https://tb.zbds.top/logo/哈尔滨资讯.png": 1,
 "https://tb.zbds.top/logo/哈尔滨都市咨询.png": 1,
 "https://tb.zbds.top/logo/嘉兴新闻综合.png": 1,
 "https://tb.zbds.top/logo/嘉峪关综合.png": 1,
 "https://tb.zbds.top/logo/固镇新闻.png": 1,
 "https://tb.zbds.top/logo/地理中国.png": 1,
 "https://tb.zbds.top/logo/大宁综合.png": 1,
 "https://tb.zbds.top/logo/天祝综合.png": 1,
 "https://tb.zbds.top/logo/太谷新闻综合.png": 1,
 "https://tb.zbds.top/logo/夹江新闻综合.png": 1,
 "https://tb.zbds.top/logo/奎屯哈萨克语.png": 1,
 "https://tb.zbds.top/logo/奎屯汉语.png": 1,
 "https://tb.zbds.top/logo/寒战.png": 1,
 "https://tb.zbds.top/logo/嵊泗综合.png": 1,
 "https://tb.zbds.top/logo/常熟民生.png": 1,
 "https://tb.zbds.top/logo/平湖民生休闲.png": 1,
 "https://tb.zbds.top/logo/平遥新闻综合.png": 1,
 "https://tb.zbds.top/logo/广元公共.png": 1,
 "https://tb.zbds.top/logo/广安公共.png": 1,
 "https://tb.zbds.top/logo/广德生活.png": 1,
 "https://tb.zbds.top/logo/庆元新闻综合.png": 1,
 "https://tb.zbds.top/logo/庆元综合.png": 1,
 "https://tb.zbds.top/logo/开化新闻综合.png": 1,
 "https://tb.zbds.top/logo/张掖新闻综合.png": 1,
 "https://tb.zbds.top/logo/我不是药神.png": 1,
 "https://tb.zbds.top/logo/拆弹专家1.png": 1,
 "https://tb.zbds.top/logo/拆弹专家2.png": 1,
 "https://tb.zbds.top/logo/敦化一套.png": 1,
 "https://tb.zbds.top/logo/文山州公共.png": 1,
 "https://tb.zbds.top/logo/文山州新闻综合.png": 1,
 "https://tb.zbds.top/logo/文成新闻综合.png": 1,
 "https://tb.zbds.top/logo/新昌新闻综合.png": 1,
 "https://tb.zbds.top/logo/新昌生活.png": 1,
 "https://tb.zbds.top/logo/新沂新闻.png": 1,
 "https://tb.zbds.top/logo/新沂生活.png": 1,
 "https://tb.zbds.top/logo/新野综合.png": 1,
 "https://tb.zbds.top/logo/旺苍新闻综合.png": 1,
 "https://tb.zbds.top/logo/昌黎综合.png": 1,
 "https://tb.zbds.top/logo/易门综合.png": 1,
 "https://tb.zbds.top/logo/晋江电视台.png": 1,
 "https://tb.zbds.top/logo/松潘新闻综合.png": 1,
 "https://tb.zbds.top/logo/松阳综合.png": 1,
 "https://tb.zbds.top/logo/柳河.png": 1,
 "https://tb.zbds.top/logo/桦甸.png": 1,
 "https://tb.zbds.top/logo/武汉一台新闻综合.png": 1,
 "https://tb.zbds.top/logo/永城综合.png": 1,
 "https://tb.zbds.top/logo/永昌综合.png": 1,
 "https://tb.zbds.top/logo/江津新闻.png": 1,
 "https://tb.zbds.top/logo/汪清.png": 1,
 "https://tb.zbds.top/logo/汶川新闻综合.png": 1,
 "https://tb.zbds.top/logo/沐川综合.png": 1,
 "https://tb.zbds.top/logo/泸县新闻综合.png": 1,
 "https://tb.zbds.top/logo/津南一套.png": 1,
 "https://tb.zbds.top/logo/浙江休闲台.png": 1,
 "https://tb.zbds.top/logo/浙江教育.png": 1,
 "https://tb.zbds.top/logo/浙江生活.png": 1,
 "https://tb.zbds.top/logo/浙江留学.png": 1,
 "https://tb.zbds.top/logo/浙江遂昌.png": 1,
 "https://tb.zbds.top/logo/海宁新闻综合.png": 1,
 "https://tb.zbds.top/logo/清河经济综艺.png": 1,
 "https://tb.zbds.top/logo/湖州公共民生.png": 1,
 "https://tb.zbds.top/logo/湖州文化娱乐.png": 1,
 "https://tb.zbds.top/logo/湖州新闻综合.png": 1,
 "https://tb.zbds.top/logo/滦平新闻.png": 1,
 "https://tb.zbds.top/logo/滨海新闻综合.png": 1,
 "https://tb.zbds.top/logo/灌阳新闻综合.png": 1,
 "https://tb.zbds.top/logo/烟台公共.png": 1,
 "https://tb.zbds.top/logo/玛纳斯.png": 1,
 "https://tb.zbds.top/logo/玛纳斯综合.png": 1,
 "https://tb.zbds.top/logo/珲春新闻.png": 1,
 "https://tb.zbds.top/logo/璧山综合.png": 1,
 "https://tb.zbds.top/logo/甘南县综合.png": 1,
 "https://tb.zbds.top/logo/甘孜综合.png": 1,
 "https://tb.zbds.top/logo/番禺综合.png": 1,
 "https://tb.zbds.top/logo/白山公共.png": 1,
 "https://tb.zbds.top/logo/白银综合.png": 1,
 "https://tb.zbds.top/logo/磐石.png": 1,
 "https://tb.zbds.top/logo/祁门综合.png": 1,
 "https://tb.zbds.top/logo/绍兴公共.png": 1,
 "https://tb.zbds.top/logo/绍兴电视台公共.png": 1,
 "https://tb.zbds.top/logo/缙云新闻综合.png": 1,
 "https://tb.zbds.top/logo/缙云综合.png": 1,
 "https://tb.zbds.top/logo/舒兰新闻.png": 1,
 "https://tb.zbds.top/logo/舒兰新闻综合.png": 1,
 "https://tb.zbds.top/logo/航拍中国第二季.png": 1,
 "https://tb.zbds.top/logo/荥经综合.png": 1,
 "https://tb.zbds.top/logo/荥阳综合.png": 1,
 "https://tb.zbds.top/logo/营山电视台.png": 1,
 "https://tb.zbds.top/logo/萧山新闻综合.png": 1,
 "https://tb.zbds.top/logo/萧山生活.png": 1,
 "https://tb.zbds.top/logo/衡水公共.png": 1,
 "https://tb.zbds.top/logo/衡阳新闻综合.png": 1,
 "https://tb.zbds.top/logo/衢江新闻综合.png": 1,
 "https://tb.zbds.top/logo/西峰综合.png": 1,
 "https://tb.zbds.top/logo/让子弹飞.png": 1,
 "https://tb.zbds.top/logo/象山综合.png": 1,
 "https://tb.zbds.top/logo/辉南新闻.png": 1,
 "https://tb.zbds.top/logo/辉南新闻综合.png": 1,
 "https://tb.zbds.top/logo/通化县.png": 1,
 "https://tb.zbds.top/logo/通海电视台.png": 1,
 "https://tb.zbds.top/logo/遂昌综合.png": 1,
 "https://tb.zbds.top/logo/邢台生活.png": 1,
 "https://tb.zbds.top/logo/邢台综合.png": 1,
 "https://tb.zbds.top/logo/邯郸公共频道.png": 1,
 "https://tb.zbds.top/logo/邯郸新闻.png": 1,
 "https://tb.zbds.top/logo/金川乡村.png": 1,
 "https://tb.zbds.top/logo/金川新闻综合.png": 1,
 "https://tb.zbds.top/logo/铜梁综合.png": 1,
 "https://tb.zbds.top/logo/铜陵新闻综合.png": 1,
 "https://tb.zbds.top/logo/长子综合.png": 1,
 "https://tb.zbds.top/logo/长沙新闻综合.png": 1,
 "https://tb.zbds.top/logo/长白山电视台.png": 1,
 "https://tb.zbds.top/logo/靖宇.png": 1,
 "https://tb.zbds.top/logo/靖江新闻综合.png": 1,
 "https://tb.zbds.top/logo/韩国EBS少儿.png": 1,
 "https://tb.zbds.top/logo/韩国电影1.png": 1,
 "https://tb.zbds.top/logo/韩国电影2.png": 1,
 "https://tb.zbds.top/logo/音乐欣赏.png": 1,
 "https://tb.zbds.top/logo/飞碟之谜01.png": 1,
 "https://tb.zbds.top/logo/飞碟之谜02.png": 1,
 "https://tb.zbds.top/logo/黑龙江新闻.png": 1,
 "https://tb.zbds.top/logo/龙井.png": 1,
 "https://tb.zbds.top/logo/龙游生活娱乐.png": 1,
 "https://tb.zbds.top/logo/龙门飞甲.png": 1
}

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": UA, "Accept": "*/*"})
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=8)
_CACHE_LOCK = threading.Lock()
_SOURCE_CACHE = {}
_SOURCE_STATUS = {}
_GROUPED_CACHE = {}
_GROUPED_INFLIGHT = {}
_AD_CHECK_CACHE = {}
_AD_LOGGED = set()
_LOG = []
_STAGE = []

_FT2JT = dict(zip(_FT2JT_FT, _FT2JT_JT))
for _a, _b in _FT2JT_EXTRA:
    _FT2JT[_a] = _b
_SEASON_KEY_RE = {int(k): re.compile(v, re.IGNORECASE) for k, v in SEASON_KEY_RE.items()}
_SEASON_GROUP_RE = {int(k): re.compile(v, re.IGNORECASE) for k, v in SEASON_GROUP_RE.items()}

# 首页分类：全部直播 + 央视 + 卫视 + 9 个内容季（第 1 季是央视、第 2 季是卫视，不重复列）
_CLASSES = [
("all", "全部直播"),
("cctv", "央视频道"),
("weishi", "卫视频道"),
("s3", "新闻"), ("s4", "体育"), ("s5", "影视"), ("s6", "综艺"),
("s7", "少儿"), ("s8", "教育"), ("s9", "纪实"), ("s10", "地方"), ("s11", "熊猫"),
("s12", "香港"), ("s13", "澳门"),
]

_RELAY_IPS = {
"63.141.230.178", "107.150.60.122", "173.208.212.130",
"192.151.150.154", "198.204.228.26", "204.12.221.218",
"69.30.245.50", "38.75.136.137",
}
_OFFICIAL_HOSTS = (
"cntv", "cctv", "mgtv", "bilibili", "bdstatic.com",
"ivi.bupt.edu.cn", "ottrrs.hl.chinamobile.com", "live.fanmingming.cn",
)
# _normTitle stripped 标点集合（与 JS 正则字符类一致，空白另用 isspace 判断）
_NORM_STRIP = set("　，。、！？：；·—_()（）[]《》〈〉\"'.!?:;,/\\-")
_CLASS_STRIP_RE = re.compile(r"[\s\-_·•()（）\[\]]+")
_SUFFIX_RE = re.compile(r"(綜合|高清|標清|标清|超清|藍光|蓝光|uhd|fhd|4k|hd)$")


def _text(v):
    return "" if v is None else str(v).strip()


def _log_line(msg):
    try:
        _LOG.append(time.strftime("%H:%M:%S") + " " + msg)
        del _LOG[:-200]
    except Exception:
        pass


def _log_stage(msg):
    try:
        _STAGE.append(msg)
        del _STAGE[:-8]
    except Exception:
        pass


def _host_of(url):
    try:
        return (str(url or "").lower().split("/")[2] or "").split(":")[0]
    except Exception:
        return ""


def _is_bad_host(url):
    h = _host_of(url)
    if not h:
        return False
    return any(b in h for b in BAD_HOSTS)


def _resolve_logo(logo, playlist_url):
    try:
        l = _text(logo)
        if not l:
            return ""
        if re.match(r"^https?://", l, re.I):
            return l
        if l.startswith("//"):
            return "https:" + l
        base = str(playlist_url or "")
        m = re.match(r"^(https?://[^/]+)(/.*)?$", base, re.I)
        if not m:
            return l
        origin = m.group(1)
        if l.startswith("/"):
            return origin + l
        d = base[:base.rfind("/") + 1]
        return d + l
    except Exception:
        return ""


def _poster_url(raw):
    # 没填 Worker：模组自己转图。imgur 走原生 320px 缩图；wsrv 拉不到的站直连原图；其余走 wsrv fit=contain 300x450。
    if not raw:
        return ""
    m = re.match(r"^https?://i\.imgur\.com/([A-Za-z0-9]+)\.(png|jpe?g|gif|webp)(\?.*)?$", raw, re.I)
    if m:
        return "https://i.imgur.com/" + m.group(1) + "m." + m.group(2)
    host = (raw.split("/")[2] if "/" in raw else "").split(":")[0]
    if host in WSRV_BAD_HOSTS:
        return raw
    no_scheme = re.sub(r"^https?://", "", raw, flags=re.I)
    return "https://images.weserv.nl/?url=" + quote(no_scheme, safe="") + "&w=300&h=450&fit=contain"


def _placeholder_cover(name):
    return "https://placehold.jp/2e2e3e/ffffff/300x450.png?text=" + quote(_text(name) or "直播", safe="")


def _parse_m3u(body, source_name, playlist_url):
    out = []
    if not body:
        return out
    lines = str(body).splitlines()
    for i, line in enumerate(lines):
        line = line.strip()
        if not line.startswith("#EXTINF"):
            continue
        m = re.search(r'tvg-logo="([^"]*)"', line) or re.search(r"tvg-logo='([^']*)'", line)
        logo = _resolve_logo(m.group(1) if m else "", playlist_url)
        gm = re.search(r'group-title="([^"]*)"', line)
        group = gm.group(1) if gm else source_name
        name = line[line.rfind(",") + 1:].strip()
        url = ""
        for j in range(i + 1, len(lines)):
            u = lines[j].strip()
            if not u:
                continue
            if u.startswith("#"):
                break
            url = u.split("$")[0].strip()
            break
        if not url or not name:
            continue
        if url.startswith("rtmp://"):
            continue
        if _is_bad_host(url):
            continue
        out.append({"n": name, "l": logo, "u": url, "g": group, "s": source_name})
    return out


def _parse_txt(body, source_name):
    out = []
    if not body:
        return out
    group = source_name
    for line in str(body).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith(",#genre#"):
            group = line[:-8].strip() or source_name
            continue
        idx = line.find(",")
        if idx < 0:
            continue
        name = line[:idx].strip()
        url = line[idx + 1:].split("$")[0].strip()
        if not name or not url:
            continue
        if url.startswith("rtmp://"):
            continue
        if not (url.startswith("http://") or url.startswith("https://")):
            continue
        if _is_bad_host(url):
            continue
        out.append({"n": name, "l": "", "u": url, "g": group, "s": source_name})
    return out


def _norm_name(n):
    s = re.sub(r"\s+", " ", str(n or "").lower()).strip()
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\s*\([^)]*\)\s*$", "", s)
        s = re.sub(r"\s*\[[^\]]*\]\s*$", "", s).strip()
    return s


def _norm_title(s):
    s = str(s or "").lower()
    return "".join(c for c in (_FT2JT.get(c, c) for c in s) if c not in _NORM_STRIP and not c.isspace())


def _class_name(n):
    return _CLASS_STRIP_RE.sub("", str(n or "").lower())


# 去重键 v3（v1.4.18.5）：两级去重——台名严格归一化（HerbertHe 归一化链思路：
# 繁转简→小写→删括号内容→去分隔符→去画质后缀→CCTV 描述归一→中英别名映射）
# + v3 五条：去 cctv 前缀（数字紧跟保留）、去 leading 中央新影、去尾台、newstv→newtv、
# 4k/8k 进画质后缀（cctv4k/8k 本身保留）。根因：旧键不做繁简转换；后缀表缺简体“综合”；没有 HEVC/50FPS/“频道”后缀处理；
# CCTV-N 后面的描述词没归一；英文别名没映射；“4k”无条件 strip 把 CCTV-4K 的键算成 cctv。
_CCTV_DESC = {"综合", "综艺", "体育", "体育赛事", "电影", "新闻", "纪录",
              "戏曲", "科教", "少儿", "音乐", "财经", "中文国际", "国际",
              "电视剧", "社会与法", "农业农村", "国防军事", "奥林匹克",
              "军事农业", "农业", "军事"}
# 画质/变体后缀：循环去尾。4k/8k 只在前面是数字时才算画质后缀
# （CCTV-4K/8K 是台名本身；“CCTV 16 4K”里 4k 前面是 16 才是后缀）。
_QUALITY_SUFFIXES = ["真4k", "真8k", "超高清", "高清", "标清", "超清", "蓝光",
                     "综合", "綜合", "hevc", "h265", "h264", "50fps", "60fps",
                     "fps", "uhd", "fhd", "hd", "频道"]
# 中英别名：英文台名 -> 中文台名（两边都走 _base_key 归一化后建表；2026-11-15 实测 67 对，两边都在库里）。
_EN_ALIAS_PAIRS = [
    ("Hunan TV", "湖南卫视"),
    ("Jiangsu Satellite TV", "江苏卫视"),
    ("Zhejiang Satellite TV", "浙江卫视"),
    ("Dragon TV", "东方卫视"),
    ("Dragon TV International", "东方卫视"),
    ("Anhui TV", "安徽卫视"),
    ("Beijing Satellite TV", "北京卫视"),
    ("Guangdong Satellite TV", "广东卫视"),
    ("Shandong Satellite TV", "山东卫视"),
    ("Shenzhen Satellite TV", "深圳卫视"),
    ("Sichuan Satellite TV", "四川卫视"),
    ("Yunnan Satellite TV", "云南卫视"),
    ("Ningxia Satellite Channel", "宁夏卫视"),
    ("Yanbian Satellite TV", "延边卫视"),
    ("Bingtuan Satellite TV", "兵团卫视"),
    ("Jiangsu City Channel", "江苏城市频道"),
    ("Jiangsu Educational Channel", "江苏教育频道"),
    ("Jiangsu Movie Channel", "江苏影视频道"),
    ("Jiangsu Public & News Channel", "江苏公共新闻频道"),
    ("Jiangsu Sports & Leisure Channel", "江苏体育休闲频道"),
    ("Jiangsu Variety Channel", "江苏综艺频道"),
    ("Hunan Economy Channel", "湖南经济频道"),
    ("Hunan News Channel", "湖南新闻频道"),
    ("Hunan Politics & Law Channel", "湖南政法频道"),
    ("Hunan Womens Channel", "湖南女性频道"),
    ("Zhejiang International Channel", "浙江国际频道"),
    ("BRTV Kaku Childrens Channel", "北京卡酷少儿频道"),
    ("Documentary Humanities Channel", "纪实人文频道"),
    ("CCTV-4 Europe", "CCTV4欧洲"),
    ("CCTV-4 America", "CCTV4美洲"),
    ("CCTV-World Geography SD", "CCTV-世界地理"),
    ("CCTV-Billiards", "CCTV-央视台球"),
    ("CCTV-Golf & Tennis", "CCTV-高尔夫网球"),
    ("CCTV-Health", "CCTV-卫生健康"),
    ("CCTV-Nostalgia Theater", "CCTV-怀旧剧场"),
    ("CCTV-Storm Football", "CCTV-风云足球"),
    ("CCTV-Storm Music", "CCTV-风云音乐"),
    ("CCTV-Storm Theater", "CCTV-风云剧场"),
    ("CCTV-The First Theater", "CCTV-第一剧场"),
    ("CCTV-Weapon & Technology", "CCTV-兵器科技"),
    ("CCTV-Women's Fashion SD", "CCTV-女性时尚"),
    ("You Man Cartoon Channel", "优漫卡通频道"),
    ("Anshun Comprehensive News Channel", "安顺新闻综合"),
    ("Chaozhou Public Channel", "潮州公共"),
    ("Chifeng Comprehensive News Chanel", "赤峰新闻综合"),
    ("Chuzhou News Channel", "滁州新闻"),
    ("Chuzhou Public Channel", "滁州公共"),
    ("Chuzhou Science & Education Channel", "滁州科教"),
    ("Dongguan Comprehensive News Channel", "东莞新闻综合"),
    ("Fujian Comprehensive Channel", "福建综合"),
    ("Harbin Comprehensive News Channel", "哈尔滨新闻综合"),
    ("Harbin Movie Channel", "哈尔滨影视"),
    ("Jingmen Comprehensive News Channel", "荆门新闻综合"),
    ("Xuzhou Economic Life Channel", "徐州经济生活"),
    ("Jiangxi Children's Channel", "江西少儿"),
    ("Jiangxi TV", "江西卫视"),
    ("Jilin Lifestyle Channel", "吉林生活"),
    ("Jilin Rural Channel", "吉林乡村"),
    ("Sichuan TV Women and Children Channel", "四川妇女儿童"),
    ("Guizhou TV", "贵州卫视"),
    ("Hebei TV", "河北卫视"),
    ("Qinghai TV", "青海卫视"),
    ("Tianjin TV", "天津卫视"),
    ("Xi'an Business Information Channel", "西安商务资讯"),
    ("Xi'an Silk Road Channel", "西安丝路"),
    ("Phoenix Chinese Channel", "凤凰中文"),
    ("Phoenix InfoNews Channel", "凤凰资讯"),
]
# v3 新增别名 18 对（2026-11-15 逐组核对后定；别名目标必须是合并后的 canonical 键——
# 如 ("Jade", "TVB翡翠台")，写 ("Jade", "翡翠台") 会失败：Jade→“翡翠”成单条）。
# 别名表每次从（新键，旧键）对重建，不可复制旧表沿用。
_EN_ALIAS_PAIRS_NEW = [
    ("CCTV-Culture of Quality SD", "央视精品"),
    ("CCTV-央视文化精品", "央视精品"),
    ("RHK31", "RTHK31"),
    ("CND Film Discovery Channel", "中央新影-发现之旅"),
    ("Celestial Movies", "天映频道"),
    ("TVB News", "无线新闻"),
    ("TVB无线新闻", "无线新闻"),
    ("BRTV卡酷少儿", "卡酷少儿"),
    ("CGNT 记录频道", "CGTN外语纪录"),
    ("TDM-Macau Satellite", "澳视卫星"),
    ("TDM Sports", "澳门体育"),
    ("TDM Entertainment", "澳门综艺"),
    ("EBS 2", "韩国EBS2"),
    ("河北", "河北卫视"),
    ("明珠台", "TVB明珠台"),
    ("翡翠台", "TVB翡翠台"),
    ("TVB无线星河", "无线星河"),
    ("Jade", "TVB翡翠台"),
]
# URL 实证别名 5 对（2026-11-15：同一归一化 URL 在两源以两名出现，2 条以上同流 URL 佐证；
# 写在这里而不是 _EN_ALIAS_PAIRS_NEW，避免与 v3 的 18 对混淆；目标同样必须是 canonical 键）。
_EN_ALIAS_PAIRS_URL = [
    ("CETV-3", "中国教育3"),
    ("文化精品", "央视精品"),
    ("TVBS亚洲", "TVBS-Asia"),
    ("福建海峡卫视", "海峡卫视"),
    ("斯诺克专场", "斯诺克"),
]


def _key_join(n):
    s = "".join(_FT2JT.get(c, c) for c in str(n or "").lower())
    s = re.sub(r"\s+", " ", s).strip()
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\s*\([^)]*\)\s*$", "", s)
        s = re.sub(r"\s*\[[^\]]*\]\s*$", "", s)
        s = re.sub("\\s*\uff08[^\uff09]*\uff09\\s*$", "", s)
        s = re.sub("\\s*\u3010[^\u3011]*\u3011\\s*$", "", s).strip()
    return re.sub(r"[\s\-_·•/]+", "", s)


def _strip_quality(s, v3=False):
    # v3=True 时 4k/8k 也进画质后缀，但整条就是 cctv4k/cctv8k 时保留（裸 4K 是台名）。
    qs = _QUALITY_SUFFIXES + (["4k", "8k"] if v3 else [])
    changed = True
    while changed:
        changed = False
        for q in qs:
            if v3 and q in ("4k", "8k") and s in ("cctv4k", "cctv8k"):
                continue
            if s.endswith(q) and len(s) > len(q):
                s = s[:-len(q)]
                changed = True
                break
        if changed:
            continue
        m = re.search(r"\d+(2160p|1080p|720p|576p|540p|480p)$", s)
        if m and len(s) > len(m.group(0)):
            s = s[: -len(m.group(0))]
            changed = True
            continue
        m = re.search(r"\d(4k|8k)$", s)
        if m and len(s) > len(m.group(0)):
            s = s[: -len(m.group(1))]
            changed = True
            continue
    return s


def _base_key_v2(n):
    # v2 键（v1.4.18.4）：只用于 lk 兼容 v2 时期收藏的连结，不参与新分组。
    s = _strip_quality(_key_join(n))
    if s == "cctv奥林匹克":
        return "cctv16"
    m = re.match(r"^cctv(\d+)(\+?)(.*)$", s)
    if m and (not m.group(3) or m.group(3) in _CCTV_DESC):
        return "cctv" + m.group(1) + m.group(2)
    return s


def _base_key(n):
    # v3 键：v2 基础上加 5 条——去 cctv 前缀（数字紧跟的保留：cctv4k/5+/16）、
    # 去 leading 中央新影、去尾台（长度>1）、newstv→newtv、4k/8k 进画质后缀。
    j = _key_join(n)
    if j.endswith("纪实科教8k"):
        return "纪实科教8k"  # 例外（2026-11-15 核对 HOLD，后缀命中）：北京纪实科教8K 也一样，8K 可能是独立台，不并入纪实科教；待手机确认。
    s = _strip_quality(j, v3=True)
    if s == "cctv奥林匹克":
        return "cctv16"
    m = re.match(r"^cctv(\d+)(\+?)(.*)$", s)
    if m and (not m.group(3) or m.group(3) in _CCTV_DESC):
        return "cctv" + m.group(1) + m.group(2)
    if s.startswith("cctv") and len(s) > 4 and not s[4].isdigit():
        s = s[4:]
    if s.startswith("中央新影"):
        s = s[4:]
    if s.endswith("台") and len(s) > 1:
        s = s[:-1]
    s = s.replace("newstv", "newtv")
    return s


_EN_ALIAS_V2 = {}
for _en, _zh in _EN_ALIAS_PAIRS:
    _EN_ALIAS_V2[_base_key_v2(_en)] = _base_key_v2(_zh)


_EN_ALIAS = {}
for _en, _zh in _EN_ALIAS_PAIRS + _EN_ALIAS_PAIRS_NEW + _EN_ALIAS_PAIRS_URL:
    _EN_ALIAS[_base_key(_en)] = _base_key(_zh)


_LEGACY_KEY_CACHE = {}


def _legacy_dedupe_key(n):
    # 旧去重键（v1.4.18.3 之前）：只留给旧收藏连结兼容（lk），新分组不用它。
    # 纯函数，按原名缓存（同一台名在 19 源里反复出现，约 2.7 倍重复）。
    try:
        return _LEGACY_KEY_CACHE[n]
    except KeyError:
        pass
    s = re.sub(r"[\s\-_·•]+", "", _norm_name(n))
    prev = None
    while prev != s:
        prev = s
        s = _SUFFIX_RE.sub("", s)
    _LEGACY_KEY_CACHE[n] = s
    return s


_DEDUPE_KEY_V2_CACHE = {}


def _dedupe_key_v2(n):
    try:
        return _DEDUPE_KEY_V2_CACHE[n]
    except KeyError:
        pass
    k = _base_key_v2(n)
    k = _EN_ALIAS_V2.get(k, k)
    _DEDUPE_KEY_V2_CACHE[n] = k
    return k


_DEDUPE_KEY_CACHE = {}


def _dedupe_key(n):
    try:
        return _DEDUPE_KEY_CACHE[n]
    except KeyError:
        pass
    k = _base_key(n)
    k = _EN_ALIAS.get(k, k)
    _DEDUPE_KEY_CACHE[n] = k
    return k


def _norm_url(u):
    # URL 归一化（只做去重键，不改播放地址）：去 fragment、空 query 丢掉、query 参数按名排序、scheme/host 小写、
    # 剥默认端口（https:443 / http:80，RFC 3986 等价；河北组同流 :443/无端口并线）。
    try:
        p = urllib.parse.urlparse(str(u or ""))
        netloc = p.netloc.lower()
        if p.scheme.lower() == "https" and netloc.endswith(":443"):
            netloc = netloc[:-4]
        elif p.scheme.lower() == "http" and netloc.endswith(":80"):
            netloc = netloc[:-3]
        q = sorted(urllib.parse.parse_qsl(p.query, keep_blank_values=True))
        return urllib.parse.urlunparse((p.scheme.lower(), netloc, p.path,
                                        p.params, urllib.parse.urlencode(q), ""))
    except Exception:
        return str(u or "")


def _is_mainland_cable(ch):
    n = ch.get("n") if ch else None
    if not n:
        return False
    k = _dedupe_key(n)
    nn = _norm_title(n)
    for name in MAINLAND_CABLE_NAMES:
        if k == _dedupe_key(name) or nn == _norm_title(name):
            return True
    return False


def _classify_channel(ch):
    n = _class_name(ch.get("n") if ch else "")
    if not n:
        return "other"
    if _is_mainland_cable(ch):
        return "other"
    if ("cctv" in n or "央視" in n or "央视" in n
            or "中央電視台" in n or "中央电视台" in n):
        return "cctv"
    if "brics" not in n:
        for k in TAIWAN_KEYS:
            if k in n:
                return "taiwan"
        for k in GANGAO_KEYS:
            if k in n:
                return "gangtai"
        if re.search(r"(^|[^a-z0-9])j2([^a-z0-9]|$)", n):
            return "gangtai"
    if "衛視" in n or "卫视" in n:
        return "weishi"
    return "other"


def _is_macau(ch):
    n = _class_name(ch.get("n") if ch else "")
    if not n:
        return False
    return any(k in n for k in MACAU_KEYS)


def _classify_season(ch):
    if _is_mainland_cable(ch):
        return 10
    base = _classify_channel(ch)
    if base == "gangtai":
        return 13 if _is_macau(ch) else 12
    if base == "cctv":
        return 1
    if base == "weishi":
        return 2
    raw = str(ch.get("n") or "").lower()
    nn = _norm_title(ch.get("n"))
    if re.search(r"satellite", raw, re.I) or re.search(r"satellite", nn, re.I):
        return 2
    for s in SEASON_ORDER:
        if _SEASON_KEY_RE[s].search(raw) or _SEASON_KEY_RE[s].search(nn):
            return s
    g_raw = str(ch.get("g") or "").lower()
    g_norm = _norm_title(ch.get("g"))
    for s in SEASON_ORDER:
        if _SEASON_GROUP_RE[s].search(g_raw) or _SEASON_GROUP_RE[s].search(g_norm):
            return s
    if re.search(r"央視|央视", g_raw) or re.search(r"央視|央视", g_norm):
        return 1
    return 10


def _stream_score(ch):
    s = 0
    u = str(ch.get("u") or "").lower()
    if u.startswith("https://"):
        s += 10
    parts = u.split("/")
    host = parts[2] if len(parts) > 2 else ""
    if any(h in host for h in _OFFICIAL_HOSTS):
        s += 20
    if host in _RELAY_IPS:
        s -= 10
    if any(h in host for h in ("264788.xyz", "freetv.fun", "metshop.top", "cttv.vip")):
        s -= 30
    for i, src in enumerate(SOURCES):
        if src["name"] == ch.get("s"):
            s += (len(SOURCES) - i)
            break
    return s


def _is_dead_logo(l):
    if not l:
        return False
    if l in DEAD_LOGO_URLS:
        return True
    try:
        d = unquote(l)
        if d != l and d in DEAD_LOGO_URLS:
            return True
    except Exception:
        pass
    return False


# 来源优先级：SOURCES 顺序即配置优先级（越前越可信），URL 仲裁平票时用，不藏在输入顺序里。
_SOURCE_ORDER = {}
for _i, _s in enumerate(SOURCES):
    _SOURCE_ORDER.setdefault(_s["name"], _i)

# URL path token -> 频道键：只有 CCTV 族（实证过的串台 pattern：cctv4k.m3u8 被标成 CCTV4中文国际）。
_CCTV_TOKEN_KEY = {"cctv5p": "cctv5+", "cctv5plus": "cctv5+"}


def _url_slug_winner(url, cand_keys):
    # 名字不能定案时看 URL path：path 里出现某个候选键本身的 CCTV token 且唯一，则该键胜出。
    try:
        path = urllib.parse.urlparse(str(url or "")).path.lower()
    except Exception:
        return ""
    toks = set(re.split(r"[^a-z0-9+]+", path))
    hits = set()
    for t in toks:
        k = _CCTV_TOKEN_KEY.get(t, t)
        if k in cand_keys and k.startswith("cctv"):
            hits.add(k)
    if len(hits) == 1:
        return next(iter(hits))
    return ""


def _resolve_url_conflicts(lst, excluded):
    # 交叉去重（同一 URL、同流不同名）：同一归一化 URL 被标成 2–3 个不同台时，决定它归谁。
    # 优先级：URL slug 身份 > 票数（条目数）> 来源顺序 > 最早条目。输家条目丢弃——流本身不丢，
    # 它仍在胜出者的组里播，只是不再以错台名出现（串台的主因之一：错标线被当成某台的主线）。
    # 4+ 个键共用同一 URL 视为通用门户端点，不仲裁（门户 URL 不作身份证据）。
    by_url = {}
    for idx, ch in enumerate(lst):
        by_url.setdefault(_norm_url(ch["u"]), []).append((idx, ch))
    drop_idx = set()
    decided = 0
    examples = []
    for uk, members in by_url.items():
        keys = {}
        for idx, ch in members:
            k = _dedupe_key(ch["n"])
            if not k or k in excluded:
                continue
            keys.setdefault(k, []).append((idx, ch))
        if len(keys) < 2 or len(keys) >= 4:
            continue
        cand = set(keys)
        winner = _url_slug_winner(members[0][1]["u"], cand)
        reason = "slug"
        if not winner:
            scored = sorted(
                keys.items(),
                key=lambda kv: (-len(kv[1]),
                                min(_SOURCE_ORDER.get(c["s"], 99) for _, c in kv[1]),
                                min(i for i, _ in kv[1])))
            winner = scored[0][0]
            reason = "vote"
        for k, items in keys.items():
            if k != winner:
                for idx, _ in items:
                    drop_idx.add(idx)
        decided += 1
        if len(examples) < 5:
            examples.append("%s 留[%s] 丢%s(%s)" % (uk[:60], winner, sorted(cand - {winner}), reason))
    if decided:
        _log_line("[去重] URL 仲裁 %d 条: %s" % (decided, "；".join(examples)))
    if not drop_idx:
        return lst
    return [ch for idx, ch in enumerate(lst) if idx not in drop_idx]


def _group_channels(lst):
    seen_url = {}
    groups = {}
    order = []
    logo_by_key = {}

    def note_logo(key, l):
        if not key or not l:
            return
        if _is_dead_logo(l):
            return
        lb = logo_by_key.setdefault(key, {"l": "", "li": ""})
        if "i.imgur.com" not in l:
            if not lb["l"]:
                lb["l"] = l
        elif not lb["li"]:
            lb["li"] = l

    def is_taiwan_entry(ch):
        if _classify_channel(ch) == "taiwan":
            return True
        gn = _class_name(ch.get("g"))
        if not gn:
            return False
        return any(_class_name(k) in gn for k in TAIWAN_KEYS)

    tw_keys = {_dedupe_key(ch["n"]) for ch in lst if is_taiwan_entry(ch)}
    lst = _resolve_url_conflicts(lst, tw_keys | set(REMOVED_KEYS))
    for ch in lst:
        key = _dedupe_key(ch["n"])
        if not key:
            continue
        if key in tw_keys or key in REMOVED_KEYS:
            continue
        note_logo(key, ch.get("l"))
        uk = _norm_url(ch["u"])
        if uk in seen_url:
            continue
        seen_url[uk] = True
        if key not in groups:
            groups[key] = {"n": ch["n"], "g": ch["g"], "s": ch["s"], "l": "", "lines": [], "key": key,
                           "lk": sorted({_legacy_dedupe_key(ch["n"]), _dedupe_key_v2(ch["n"])})}
            order.append(key)
        else:
            for lk in (_legacy_dedupe_key(ch["n"]), _dedupe_key_v2(ch["n"])):
                if lk not in groups[key]["lk"]:
                    groups[key]["lk"].append(lk)
        groups[key]["lines"].append({"u": ch["u"], "s": ch["s"], "score": _stream_score(ch)})
    out = []
    for k in order:
        g = groups[k]
        g["lines"].sort(key=lambda x: -x["score"])
        g["u"] = g["lines"][0]["u"]
        g["s"] = g["lines"][0]["s"]
        lb = logo_by_key.get(k, {"l": "", "li": ""})
        if lb["l"]:
            g["l"] = lb["l"]
        elif LOGO_FALLBACK.get(k) and "i.imgur.com" not in LOGO_FALLBACK[k]:
            g["l"] = LOGO_FALLBACK[k]
        if not g["l"]:
            g["l"] = lb["li"] or LOGO_FALLBACK.get(k) or _placeholder_cover(g["n"])
        out.append(g)
    return out

def _source_by_key(key):
    for s in SOURCES:
        if s["key"] == key:
            return s
    return None


def _fetch_source(key):
    with _CACHE_LOCK:
        if key in _SOURCE_CACHE:
            return _SOURCE_CACHE[key]
    src = _source_by_key(key)
    if not src:
        return []
    try:
        r = _SESSION.get(src["url"], timeout=SOURCE_TIMEOUT)
        status = r.status_code
        body = r.content.decode("utf-8", "replace") if status < 400 else ""
        err = "" if status < 400 else "HTTP %d" % status
    except Exception as e:
        status, body, err = 0, "", str(e) or "连线失败"
    if err:
        _SOURCE_STATUS[key] = {"ok": False, "status": status, "error": err, "count": 0}
        _log_line("[%s] 拉取失败: %s @ %s" % (key, err, src["url"]))
        lst = []
    else:
        lst = _parse_txt(body, src["name"]) if src["type"] == "txt" else _parse_m3u(body, src["name"], src["url"])
        _SOURCE_STATUS[key] = {"ok": len(lst) > 0, "status": status,
                               "error": "" if lst else "回包无频道", "count": len(lst)}
        if not lst:
            _log_line("[%s] 回包无频道 @ %s" % (key, src["url"]))
    with _CACHE_LOCK:
        _SOURCE_CACHE[key] = lst
    return lst


def _fetch_category_fresh(cat):
    keys = [s["key"] for s in SOURCES]
    futs = {k: _EXECUTOR.submit(_fetch_source, k) for k in keys}
    all_items = []
    failed = []
    for k in keys:
        try:
            lst = futs[k].result()
        except Exception:
            lst = []
        if not lst:
            st = _SOURCE_STATUS.get(k, {})
            src = _source_by_key(k)
            failed.append({"key": k, "name": src["name"] if src else k,
                           "url": src["url"] if src else "", "error": st.get("error") or "无回应"})
        all_items.extend(lst)
    return {"items": _group_channels(all_items), "failed": failed}


def _fetch_category(cat="all"):
    with _CACHE_LOCK:
        if cat in _GROUPED_CACHE:
            return _GROUPED_CACHE[cat]
        fut = _GROUPED_INFLIGHT.get(cat)
        if fut is None:
            fut = _EXECUTOR.submit(_fetch_category_fresh, cat)
            _GROUPED_INFLIGHT[cat] = fut
    try:
        r = fut.result()
    except Exception:
        with _CACHE_LOCK:
            _GROUPED_INFLIGHT.pop(cat, None)
        raise
    with _CACHE_LOCK:
        _GROUPED_CACHE[cat] = r
        _GROUPED_INFLIGHT.pop(cat, None)
    return r


def _fetch_all_channels():
    return _fetch_category("all")


def _paged(items, pg):
    try:
        p = max(1, int(pg or 1))
    except Exception:
        p = 1
    start = (p - 1) * PAGE_SIZE
    return items[start:start + PAGE_SIZE]


def _channel_to_vod(ch, label):
    g = label or ch.get("g") or ""
    lines = ch.get("lines") or []
    n = len(lines)
    key = ch.get("key") or _dedupe_key(ch["n"])
    return {
        "vod_id": PREFIX + "ch:" + quote(key, safe=""),
        "vod_name": ch["n"],
        "vod_pic": _poster_url(ch.get("l") or ""),
        "vod_remarks": "直播 · " + g + " · " + ch.get("s", "") + (" · %d 条线路" % n if n > 1 else ""),
        "vod_year": "",
        "vod_area": "",
        "vod_tag": g,
    }


def _diag_vod(cat_title, failed):
    first = failed[0] if failed else {}
    detail = " / ".join("%s · %s · %s" % (f.get("name", ""), f.get("url", ""), f.get("error", "")) for f in failed) or "来源无回应"
    err = first.get("error") or "来源无回应"
    return {
        "vod_id": PREFIX + "diag:" + cat_title,
        "vod_name": "错误: " + err,
        "vod_pic": "",
        "vod_remarks": detail + " · 列表载入失败",
        "vod_content": detail,
    }


def _detail_fail_vod(link, reason):
    return {
        "vod_id": PREFIX + "diag:detail",
        "vod_name": "载入失败",
        "vod_pic": "",
        "vod_remarks": "错误: " + reason,
        "vod_content": "错误: " + reason + ((" · " + str(link)[:120]) if link else ""),
    }


def _log_vod():
    body = "[tv_stage]\n" + ("\n".join(_STAGE) if _STAGE else "（无）") + "\n[tv_log]\n" + ("\n".join(_LOG[-20:]) if _LOG else "（无）")
    return {
        "vod_id": PREFIX + "diag:log",
        "vod_name": "诊断日志",
        "vod_pic": "",
        "vod_remarks": "搜寻 log 查看",
        "vod_content": body,
    }


# ---------------- 插播广告标记检测 ----------------
def _has_ad_markers(text):
    t = str(text or "").lower()
    return any(m in t for m in AD_MARKERS)


def _first_variant_url(playlist_text, base_url):
    lines = str(playlist_text or "").splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("#EXT-X-STREAM-INF"):
            for j in range(i + 1, len(lines)):
                u = lines[j].strip()
                if not u:
                    continue
                if u.startswith("#"):
                    break
                return _resolve_logo(u, base_url)
            return ""
    return ""


def _check_playlist_for_ads(url):
    u = str(url or "")
    if not u or re.search(r"\.mp4(\?|#|$)", u, re.I):
        return False
    now = time.time()
    cached = _AD_CHECK_CACHE.get(u)
    if cached:
        ttl = AD_CHECK_UNKNOWN_TTL if cached["r"] is None else AD_CHECK_TTL
        if now - cached["at"] < ttl:
            return cached["r"]
    result = None
    try:
        r = _SESSION.get(u, timeout=AD_CHECK_TIMEOUT)
        status = r.status_code
        body = r.content.decode("utf-8", "replace") if status < 400 else ""
        err = "" if status < 400 else "HTTP %d" % status
    except Exception:
        status, body, err = 0, "", "超时"
    if status and status >= 400:
        result = "dead"
    elif not err and body:
        if _has_ad_markers(body):
            result = True
        else:
            variant = _first_variant_url(body, u)
            if variant:
                try:
                    r2 = _SESSION.get(variant, timeout=AD_CHECK_TIMEOUT)
                    if r2.status_code < 400 and r2.content:
                        result = _has_ad_markers(r2.content.decode("utf-8", "replace"))
                except Exception:
                    pass
            else:
                result = False
    _AD_CHECK_CACHE[u] = {"r": result, "at": now}
    return result


def _pick_clean_lines(ch):
    src = list((ch.get("lines") or [])[:MAX_LINES])
    if not src:
        return {"lines": [], "all_flagged": False}
    unknown = []
    dead = []
    for i, line in enumerate(src):
        r = _check_playlist_for_ads(line["u"])
        if r is True:
            if line["u"] not in _AD_LOGGED:
                _AD_LOGGED.add(line["u"])
                _log_line("[%s] 含插播标记，已切下一条线 · %s" % (ch["n"], str(line["u"])[:80]))
            continue
        if r == "dead":
            if line["u"] not in _AD_LOGGED:
                _AD_LOGGED.add(line["u"])
                _log_line("[%s] 线路已死（HTTP 4xx/5xx），往后排 · %s" % (ch["n"], str(line["u"])[:80]))
            dead.append(line)
            continue
        if r is False:
            kept = [line] + unknown + src[i + 1:] + dead
            return {"lines": kept, "all_flagged": False}
        unknown.append(line)
    if unknown:
        return {"lines": unknown + dead, "all_flagged": False}
    if dead:
        return {"lines": dead, "all_flagged": False}
    key = ch.get("key") or ""
    if ("all:" + key) not in _AD_LOGGED:
        _AD_LOGGED.add("all:" + key)
        _log_line("[%s] 全部线路都有插播标记，照常用最优线" % ch["n"])
    return {"lines": [src[0]], "all_flagged": True}


# ---------------- 播放 ----------------
def _parse_owned_link(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.startswith(PREFIX + "ch:"):
        try:
            k = unquote(s[len(PREFIX + "ch:"):])
            return {"key": k} if k else None
        except Exception:
            return None
    if s.startswith(PREFIX + "play:"):
        try:
            u = unquote(s[len(PREFIX + "play:"):])
            return {"url": u} if re.match(r"^https?://", u, re.I) else None
        except Exception:
            return None
    return {"url": s} if re.match(r"^https?://", s, re.I) else None


def _find_channel_by_key(key):
    if not key:
        return None
    for c in _fetch_all_channels()["items"]:
        if (c.get("key") or _dedupe_key(c["n"])) == key:
            return c
    # 兼容旧收藏：旧版连结用旧去重键（lk 里记了合并前各变体的旧键）。
    for c in _fetch_all_channels()["items"]:
        if key in (c.get("lk") or []):
            return c
    return None


def _detect_format(url):
    if re.search(r"\.mp4(\?|#|$)", url or "", re.I):
        return "mp4"
    return "hls"


def _filter_by_tid(items, tid):
    if tid in (None, "", "all"):
        return items
    if tid == "cctv":
        return [ch for ch in items if _classify_channel(ch) == "cctv"]
    if tid == "weishi":
        return [ch for ch in items if _classify_channel(ch) == "weishi"]
    if isinstance(tid, str) and tid.startswith("s") and tid[1:].isdigit():
        s = int(tid[1:])
        if 1 <= s <= 13:
            return [ch for ch in items if _classify_season(ch) == s]
    return items


def _tid_title(tid):
    if tid == "cctv":
        return "央视频道"
    if tid == "weishi":
        return "卫视频道"
    if isinstance(tid, str) and tid.startswith("s") and tid[1:].isdigit():
        s = int(tid[1:])
        if 1 <= s <= 13:
            return SEASON_NAMES[s]
    return "全部直播"


def _tid_label(tid):
    if tid in (None, "", "all"):
        return None
    return _tid_title(tid)


class Spider(BaseSpider):

    def getName(self):
        return "直播电视（稳定源） v" + VERSION

    def isVideoFormat(self, url):
        u = str(url or "").split("?")[0].split("#")[0].lower()
        return u.endswith((".m3u8", ".m3u", ".mp4", ".ts", ".flv", ".mov", ".mkv"))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def homeContent(self, filter):
        return {
            "class": [{"type_id": tid, "type_name": name} for tid, name in _CLASSES],
            "filters": {},
        }

    def homeVideoContent(self):
        try:
            r = _fetch_all_channels()
            return {"list": [_channel_to_vod(ch, None) for ch in r["items"][:20]]}
        except Exception as e:
            return {"list": [_diag_vod("首页", [{"name": "全部直播", "url": "", "error": str(e)}])]}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = max(1, int(pg or 1))
        except Exception:
            pg = 1
        try:
            r = _fetch_all_channels()
            items = _filter_by_tid(r["items"], tid)
            if not items and r["failed"]:
                return {"list": [_diag_vod(_tid_title(tid), r["failed"])],
                        "page": pg, "pagecount": 1, "total": 1}
            return {"list": [_channel_to_vod(ch, _tid_label(tid)) for ch in _paged(items, pg)],
                    "page": pg,
                    "pagecount": max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE),
                    "total": len(items)}
        except Exception as e:
            _log_stage("列表失败: " + str(e))
            return {"list": [_diag_vod(_tid_title(tid), [{"name": "全部直播", "url": "", "error": str(e)}])],
                    "page": pg, "pagecount": 1, "total": 1}

    def detailContent(self, ids):
        raw = ids[0] if ids else ""
        parsed = _parse_owned_link(raw)
        if not parsed:
            return {"list": [_detail_fail_vod(raw, "连结无效")]}
        try:
            ch = None
            stream_url = ""
            if "key" in parsed:
                ch = _find_channel_by_key(parsed["key"])
                stream_url = ch["u"] if ch else ""
            else:
                stream_url = parsed["url"]
                for c in _fetch_all_channels()["items"]:
                    if c["u"] == stream_url:
                        ch = c
                        break
            if not stream_url:
                return {"list": [_detail_fail_vod(raw, "找不到频道")]}
            lines = (ch.get("lines") or []) if ch else []
            line_count = len(lines) if lines else 1
            ad_note = ""
            if ch and lines:
                pick = _pick_clean_lines(ch)
                if pick["lines"]:
                    stream_url = pick["lines"][0]["u"]
                if pick["all_flagged"]:
                    ad_note = " · 可能插播广告"
            all_ch = _fetch_all_channels()["items"]
            cur_season = _classify_season(ch) if ch else 0
            order = ([cur_season] + [s for s in range(1, 14) if s != cur_season]
                     if cur_season else list(range(1, 14)))
            flags = []
            urls = []
            for s in order:
                season_items = [c for c in all_ch if _classify_season(c) == s]
                flags.append(SEASON_NAMES[s])
                urls.append("#".join(
                    "%s$%s" % (c["n"], PREFIX + "ch:" + quote(c.get("key") or _dedupe_key(c["n"]), safe=""))
                    for c in season_items))
            desc = ""
            if ch:
                desc = ("%s · %s · %s" % (
                    SEASON_NAMES[cur_season],
                    CAT_TITLE.get(_classify_channel(ch), ""), ch.get("s", "")))
                if line_count > 1:
                    desc += " · %d 条线路（播放按顺序试）" % line_count
                desc += ad_note
            else:
                desc = "直播"
            vod = {
                "vod_id": PREFIX + "ch:" + quote((ch.get("key") if ch else "") or _dedupe_key(stream_url), safe=""),
                "vod_name": ch["n"] if ch else "直播频道",
                "vod_pic": _poster_url(ch.get("l") or "") if ch else "",
                "vod_remarks": "直播",
                "vod_content": desc,
                "vod_play_from": "$$$".join(flags),
                "vod_play_url": "$$$".join(urls),
            }
            return {"list": [vod]}
        except Exception as e:
            msg = str(e)
            _log_stage("详情失败: " + msg)
            return {"list": [_detail_fail_vod(raw, msg)]}

    def searchContent(self, key, quick, pg):
        kw = _text(key)
        if kw == "log":
            return {"list": [_log_vod()], "page": 1, "pagecount": 1, "total": 1}
        parts = [_norm_title(p) for p in kw.split() if _norm_title(p)]
        if not parts:
            return {"list": []}
        try:
            pg = max(1, int(pg or 1))
        except Exception:
            pg = 1
        r = _fetch_all_channels()
        hits = [ch for ch in r["items"]
                if all(p in _norm_title(ch["n"]) for p in parts)]
        if not hits and r["failed"]:
            return {"list": [_diag_vod("搜寻", r["failed"])],
                    "page": pg, "pagecount": 1, "total": 1}
        return {"list": [_channel_to_vod(ch, None) for ch in _paged(hits, pg)],
                "page": pg,
                "pagecount": max(1, (len(hits) + PAGE_SIZE - 1) // PAGE_SIZE),
                "total": len(hits)}

    def playerContent(self, flag, id, vipFlags):
        try:
            parsed = _parse_owned_link(id)
            if not parsed:
                _log_stage("取流失败: 连结无效 · " + str(id)[:80])
                return {"parse": 0, "url": "", "header": {"User-Agent": UA}}
            if "key" in parsed:
                ch = _find_channel_by_key(parsed["key"])
                if not ch or not ch.get("lines"):
                    _log_stage("取流失败: 找不到频道 · " + parsed["key"])
                    return {"parse": 0, "url": "", "header": {"User-Agent": UA}}
                pick = _pick_clean_lines(ch)
                if not pick["lines"]:
                    _log_stage("取流失败: 找不到频道 · " + parsed["key"])
                    return {"parse": 0, "url": "", "header": {"User-Agent": UA}}
                lines = pick["lines"]
                _names = [(_l.get("s") or "直播源") for _l in lines]
                _counts = {}
                for _nm in _names:
                    _counts[_nm] = _counts.get(_nm, 0) + 1
                _idx = {}
                _vals = []
                for _nm, _l in zip(_names, lines):
                    if _counts[_nm] > 1:
                        _idx[_nm] = _idx.get(_nm, 0) + 1
                        _nm = "%s %d" % (_nm, _idx[_nm])
                    _vals.append({"n": _nm, "v": _l["u"]})
                return {"parse": 0,
                        "url": {"values": _vals, "position": 0},
                        "header": {"User-Agent": UA}}
            return {"parse": 0, "url": parsed["url"], "header": {"User-Agent": UA}}
        except Exception as e:
            _log_stage("取流失败: " + str(e))
            return {"parse": 0, "url": "", "header": {"User-Agent": UA}}

    def localProxy(self, param):
        url = ""
        headers = {"User-Agent": UA}
        if isinstance(param, dict):
            url = param.get("url") or param.get("u") or ""
            if param.get("referer"):
                headers["Referer"] = param["referer"]
        elif isinstance(param, str):
            url = param
        if not url:
            return [404, "text/plain", b""]
        try:
            r = _SESSION.get(url, headers=headers, timeout=15)
            if r.status_code >= 400:
                return [404, "text/plain", b""]
            mime = (r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
                    or "image/jpeg")
            return [200, mime, r.content]
        except Exception:
            return [404, "text/plain", b""]

    def liveContent(self, url):
        r = _fetch_all_channels()
        groups = {}
        order = []
        for ch in r["items"]:
            cat = _classify_channel(ch)
            gname = CAT_TITLE.get(cat, "地方/其他")
            if gname not in groups:
                groups[gname] = []
                order.append(gname)
            lines = (ch.get("lines") or [])[:MAX_LINES]
            groups[gname].append({
                "name": ch["n"],
                "urls": [l["u"] for l in lines] or [ch["u"]],
            })
        return [{"group": g, "channels": groups[g]} for g in order]

