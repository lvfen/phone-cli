"""iOS application bundle ID mappings.

Maps user-friendly app names to iOS bundle identifiers.
These bundle IDs are used with WDA to launch apps on iOS devices.
"""

APP_PACKAGES: dict[str, str] = {
    # Social & Messaging
    "微信": "com.tencent.xin",
    "QQ": "com.tencent.mqq",
    "微博": "com.sina.weibo",
    # E-commerce
    "淘宝": "com.taobao.taobao4iphone",
    "京东": "com.360buy.jdmobile",
    "拼多多": "com.xunmeng.pinduoduo",
    "淘宝闪购": "com.taobao.taobao4iphone",
    "京东秒送": "com.360buy.jdmobile",
    # Lifestyle & Social
    "小红书": "com.xingin.discover",
    "豆瓣": "com.douban.frodo",
    "知乎": "com.zhihu.ios",
    # Maps & Navigation
    "高德地图": "com.autonavi.amap",
    "百度地图": "com.baidu.map",
    # Food & Services
    "美团": "com.meituan.imeituan",
    "大众点评": "com.dianping.dpscope",
    "饿了么": "me.ele.ios",
    "肯德基": "com.yum.kfc",
    # Travel
    "携程": "ctrip.com",
    "铁路12306": "com.MobileTicket",
    "12306": "com.MobileTicket",
    "去哪儿": "com.qunar.iphoneclient",
    "去哪儿旅行": "com.qunar.iphoneclient",
    "滴滴出行": "com.xiaojukeji.didi",
    # Video & Entertainment
    "bilibili": "tv.danmaku.bilianime",
    "抖音": "com.ss.iphone.ugc.Aweme",
    "快手": "com.jiangjia.gif",
    "腾讯视频": "com.tencent.live4iphone",
    "爱奇艺": "com.qiyi.iphone",
    "优酷视频": "com.youku.YouKu",
    "芒果TV": "com.hunantv.imgotv",
    "红果短剧": "com.zijieads.RedFruit",
    # Music & Audio
    "网易云音乐": "com.netease.cloudmusic",
    "QQ音乐": "com.tencent.QQMusic",
    "汽水音乐": "com.ss.iphone.ugc.musicapp",
    "喜马拉雅": "com.gemd.iting",
    # Reading
    "番茄小说": "com.zijieads.DragonRead",
    "番茄免费小说": "com.zijieads.DragonRead",
    "七猫免费小说": "com.kmxs.reader",
    # Productivity
    "飞书": "com.ss.iphone.lark",
    "QQ邮箱": "com.tencent.qqmail",
    # AI & Tools
    "豆包": "com.ss.iphone.IntelligentChat",
    # Health & Fitness
    "keep": "com.gotokeep.keep",
    "美柚": "com.lingan.seeyou",
    # News & Information
    "腾讯新闻": "com.tencent.info",
    "今日头条": "com.ss.iphone.article.News",
    # Real Estate
    "贝壳找房": "com.lianjia.beike",
    "安居客": "com.anjuke.iphone",
    # Finance
    "同花顺": "com.hexin.plat.ios",
    "支付宝": "com.alipay.iphoneclient",
    # Games
    "星穹铁道": "com.miHoYo.hkrpg",
    "崩坏：星穹铁道": "com.miHoYo.hkrpg",
    "恋与深空": "com.papegames.lysk",

    # iOS system apps
    "Settings": "com.apple.Preferences",
    "设置": "com.apple.Preferences",
    "系统设置": "com.apple.Preferences",
    "Safari": "com.apple.mobilesafari",
    "safari": "com.apple.mobilesafari",
    "浏览器": "com.apple.mobilesafari",
    "Photos": "com.apple.mobileslideshow",
    "photos": "com.apple.mobileslideshow",
    "相册": "com.apple.mobileslideshow",
    "图库": "com.apple.mobileslideshow",
    "Camera": "com.apple.camera",
    "camera": "com.apple.camera",
    "相机": "com.apple.camera",
    "Clock": "com.apple.mobiletimer",
    "clock": "com.apple.mobiletimer",
    "时钟": "com.apple.mobiletimer",
    "Calendar": "com.apple.mobilecal",
    "calendar": "com.apple.mobilecal",
    "日历": "com.apple.mobilecal",
    "Contacts": "com.apple.MobileAddressBook",
    "contacts": "com.apple.MobileAddressBook",
    "联系人": "com.apple.MobileAddressBook",
    "通讯录": "com.apple.MobileAddressBook",
    "Notes": "com.apple.mobilenotes",
    "notes": "com.apple.mobilenotes",
    "备忘录": "com.apple.mobilenotes",
    "笔记": "com.apple.mobilenotes",
    "Maps": "com.apple.Maps",
    "maps": "com.apple.Maps",
    "地图": "com.apple.Maps",
    "Messages": "com.apple.MobileSMS",
    "messages": "com.apple.MobileSMS",
    "短信": "com.apple.MobileSMS",
    "信息": "com.apple.MobileSMS",
    "Phone": "com.apple.mobilephone",
    "phone": "com.apple.mobilephone",
    "电话": "com.apple.mobilephone",
    "拨号": "com.apple.mobilephone",
    "Mail": "com.apple.mobilemail",
    "mail": "com.apple.mobilemail",
    "邮件": "com.apple.mobilemail",
    "Music": "com.apple.Music",
    "music": "com.apple.Music",
    "音乐": "com.apple.Music",
    "App Store": "com.apple.AppStore",
    "AppStore": "com.apple.AppStore",
    "应用商店": "com.apple.AppStore",
    "Files": "com.apple.DocumentsApp",
    "files": "com.apple.DocumentsApp",
    "文件": "com.apple.DocumentsApp",
    "Health": "com.apple.Health",
    "health": "com.apple.Health",
    "健康": "com.apple.Health",
    "Wallet": "com.apple.Passbook",
    "wallet": "com.apple.Passbook",
    "钱包": "com.apple.Passbook",
    "Weather": "com.apple.weather",
    "weather": "com.apple.weather",
    "天气": "com.apple.weather",
    "Calculator": "com.apple.calculator",
    "calculator": "com.apple.calculator",
    "计算器": "com.apple.calculator",
    "Reminders": "com.apple.reminders",
    "reminders": "com.apple.reminders",
    "提醒事项": "com.apple.reminders",

    # Third-party international apps
    "Chrome": "com.google.chrome.ios",
    "chrome": "com.google.chrome.ios",
    "Google Chrome": "com.google.chrome.ios",
    "Gmail": "com.google.Gmail",
    "gmail": "com.google.Gmail",
    "Google Maps": "com.google.Maps",
    "googlemaps": "com.google.Maps",
    "GoogleMaps": "com.google.Maps",
    "Google Drive": "com.google.Drive",
    "googledrive": "com.google.Drive",
    "GoogleDrive": "com.google.Drive",
    "Telegram": "ph.telegra.Telegraph",
    "telegram": "ph.telegra.Telegraph",
    "WhatsApp": "net.whatsapp.WhatsApp",
    "Whatsapp": "net.whatsapp.WhatsApp",
    "whatsapp": "net.whatsapp.WhatsApp",
    "Twitter": "com.atebits.Tweetie2",
    "twitter": "com.atebits.Tweetie2",
    "X": "com.atebits.Tweetie2",
    "Reddit": "com.reddit.Reddit",
    "reddit": "com.reddit.Reddit",
    "Tiktok": "com.zhiliaoapp.musically",
    "tiktok": "com.zhiliaoapp.musically",
    "WeChat": "com.tencent.xin",
    "wechat": "com.tencent.xin",
    "Temu": "com.einnovation.temu",
    "temu": "com.einnovation.temu",
}


def get_package_name(app_name: str) -> str | None:
    """
    Get the bundle ID for an app.

    Args:
        app_name: The display name of the app.

    Returns:
        The iOS bundle identifier, or None if not found.
    """
    return APP_PACKAGES.get(app_name)


def get_app_name(package_name: str) -> str | None:
    """
    Get the app name from a bundle ID.

    Args:
        package_name: The iOS bundle identifier.

    Returns:
        The display name of the app, or None if not found.
    """
    for name, package in APP_PACKAGES.items():
        if package == package_name:
            return name
    return None


def list_supported_apps() -> list[str]:
    """
    Get a list of all supported app names.

    Returns:
        List of app names.
    """
    return list(APP_PACKAGES.keys())
