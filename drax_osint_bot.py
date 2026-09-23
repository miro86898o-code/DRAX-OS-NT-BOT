#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#         D R A X   T E L E G R A M   B O T   v6.0
#         11 Sayfa, 200+ Arac + Gercek Sonuclar
# ============================================================

import logging, requests, socket, re, io, os, time, random, string
import hashlib, ssl, glob, asyncio, urllib.parse
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

try:
    import phonenumbers
    from phonenumbers import carrier as pn_carrier, geocoder as pn_geo
    PHONE_OK = True
except ImportError:
    PHONE_OK = False

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    import whois
    WHOIS_OK = True
except ImportError:
    WHOIS_OK = False

try:
    import dns.resolver
    DNS_OK = True
except ImportError:
    DNS_OK = False

# ---------- CONFIG ----------
TOKEN = "8759042618:AAHYtubS0vZYAL3wSTc2CD-fz6OZmi3LkGo"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Drax")

pending_input = {}


# ============================================================
#   YARDIMCILAR
# ============================================================
def _get(url, **kw):
    kw.setdefault("timeout", 12)
    kw.setdefault("headers", HEADERS)
    return requests.get(url, **kw)


def _safe_url(u):
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


# ============================================================
#   SQL TEST (sadece test_*.sql / fake_*.sql)
# ============================================================
SQL_DIR = os.path.dirname(os.path.abspath(__file__))
SQL_MAX = 1000
SQL_CACHE = {}


def _sql_parse(yol):
    t = {}
    try:
        with open(yol, 'r', encoding='utf-8', errors='ignore') as f:
            ic = f.read()
    except:
        return t

    def _pv(s):
        o, c, ins, sc, i = [], '', False, '', 0
        while i < len(s):
            ch = s[i]
            if ins:
                if ch == '\\' and i + 1 < len(s):
                    c += s[i + 1]; i += 2; continue
                elif ch == sc:
                    ins = False
                else:
                    c += ch
            else:
                if ch in ("'", '"'):
                    ins = True; sc = ch
                elif ch == ',':
                    o.append(c.strip()); c = ''
                else:
                    c += ch
            i += 1
        o.append(c.strip()); return o

    pat = re.compile(
        r"INSERT INTO\s+`?(\w+)`?\s*\(([^)]+)\)\s*VALUES\s*(.*?);\s*(?=INSERT|$)",
        re.DOTALL | re.IGNORECASE)
    for m in pat.finditer(ic):
        tb = m.group(1)
        kl = [k.strip().strip('`').lower() for k in m.group(2).split(',')]
        ii = mi = None
        for i, k in enumerate(kl):
            if k == 'id' and ii is None: ii = i
            if k in ('email', 'mail', 'e_mail', 'eposta', 'user_email') and mi is None: mi = i
        if ii is None and mi is None: continue
        t.setdefault(tb, [])
        for rm in re.finditer(r"\(([^()]*(?:\([^()]*\)[^()]*)*)\)", m.group(3)):
            if len(t[tb]) >= SQL_MAX: break
            a = _pv(rm.group(1))
            iv = a[ii] if ii is not None and ii < len(a) else ''
            mv = a[mi] if mi is not None and mi < len(a) else ''
            if iv or mv: t[tb].append([iv, mv])
    return t


def sql_load():
    global SQL_CACHE
    SQL_CACHE = {}
    dosyalar = sorted(glob.glob(os.path.join(SQL_DIR, 'test_*.sql'))) + \
               sorted(glob.glob(os.path.join(SQL_DIR, 'fake_*.sql')))
    if not dosyalar: return 0, 0
    for y in dosyalar:
        try:
            for tb, sl in _sql_parse(y).items():
                SQL_CACHE.setdefault(tb, [])
                k = SQL_MAX - len(SQL_CACHE[tb])
                if k > 0: SQL_CACHE[tb].extend(sl[:k])
        except:
            pass
    return len(SQL_CACHE), sum(len(v) for v in SQL_CACHE.values())


def fn_sql_test(deger):
    if not SQL_CACHE: sql_load()
    if not SQL_CACHE:
        return ("Test SQL dosyasi bulunamadi.\n"
                "Bot klasorune 'test_*.sql' veya 'fake_*.sql' koy.")
    deger = str(deger).strip()
    if deger.startswith('@'): deger = deger[1:]
    sonuc = []
    for tb, sl in SQL_CACHE.items():
        for s in sl:
            if s[0] == deger or s[1].lower() == deger.lower():
                sonuc.append((tb, s[0], s[1]))
    if not sonuc: return f"Sonuc yok: {deger}"
    out = [f"{len(sonuc)} sonuc:"]
    for tb, i, e in sonuc[:30]:
        out.append(f"  [{tb}] ID: {i} | {e}")
    if len(sonuc) > 30:
        out.append(f"  ... ve {len(sonuc)-30} tane daha")
    return "\n".join(out)


_sql_t, _sql_r = sql_load()


# ============================================================
#   TEMEL OSINT
# ============================================================
def fn_email(e):
    if '@' not in e: return "Gecersiz email."
    user, domain = e.split('@', 1)
    out = [f"Hedef: {e}", ""]

    try:
        r = _get(f"https://emailrep.io/{e}")
        if r.status_code == 200:
            d = r.json()
            out.append("[EmailRep]")
            out.append(f"  Reputation: {d.get('reputation','-')}")
            out.append(f"  Suspicious: {d.get('suspicious','-')}")
            out.append(f"  Blacklisted: {d.get('details',{}).get('blacklisted','-')}")
            out.append(f"  Data Breach: {d.get('details',{}).get('data_breach','-')}")
            profs = d.get('details', {}).get('profiles', [])
            if profs: out.append(f"  Profiller: {', '.join(profs)}")
            out.append("")
    except Exception as ex:
        out.append(f"[EmailRep] Hata: {ex}")

    try:
        r = _get(f"https://haveibeenpwned.com/api/v3/breachedaccount/{e}",
                 headers={"User-Agent": "Drax-OSINT"})
        if r.status_code == 200:
            d = r.json()
            out.append(f"[HIBP] {len(d)} sizinti:")
            for x in d[:10]:
                out.append(f"  - {x.get('Name')} ({x.get('BreachDate','-')})")
        elif r.status_code == 404:
            out.append("[HIBP] Sizinti yok.")
        elif r.status_code == 401:
            out.append("[HIBP] API key gerekli (ucretli).")
    except Exception as ex:
        out.append(f"[HIBP] Hata: {ex}")

    out.append("")
    out.append("[Diger]")
    out.append(f"  GitHub: https://github.com/{user}")
    out.append(f"  Gravatar: https://www.gravatar.com/{hashlib.md5(e.lower().encode()).hexdigest()}.json")
    out.append(f"  Google: https://www.google.com/search?q=%22{e}%22")
    return "\n".join(out)


def fn_username(u):
    u = u.strip().lstrip("@")
    sites = {
        "GitHub":       f"https://github.com/{u}",
        "Twitter/X":    f"https://twitter.com/{u}",
        "Instagram":    f"https://www.instagram.com/{u}/",
        "Reddit":       f"https://www.reddit.com/user/{u}",
        "TikTok":       f"https://www.tiktok.com/@{u}",
        "YouTube":      f"https://www.youtube.com/@{u}",
        "Twitch":       f"https://www.twitch.tv/{u}",
        "Medium":       f"https://medium.com/@{u}",
        "SoundCloud":   f"https://soundcloud.com/{u}",
        "Steam":        f"https://steamcommunity.com/id/{u}",
        "Telegram":     f"https://t.me/{u}",
        "VK":           f"https://vk.com/{u}",
        "GitLab":       f"https://gitlab.com/{u}",
        "Keybase":      f"https://keybase.io/{u}",
        "Kaggle":       f"https://www.kaggle.com/{u}",
        "LeetCode":     f"https://leetcode.com/{u}",
        "Pinterest":    f"https://www.pinterest.com/{u}/",
        "Flickr":       f"https://www.flickr.com/people/{u}",
        "DeviantArt":   f"https://www.deviantart.com/{u}",
        "Behance":      f"https://www.behance.net/{u}",
        "Dribbble":     f"https://dribbble.com/{u}",
        "Patreon":      f"https://www.patreon.com/{u}",
        "BitBucket":    f"https://bitbucket.org/{u}/",
        "HackerNews":   f"https://news.ycombinator.com/user?id={u}",
        "ProductHunt":  f"https://www.producthunt.com/@{u}",
        "About.me":     f"https://about.me/{u}",
        "WordPress":    f"https://{u}.wordpress.com",
        "Blogger":      f"https://{u}.blogspot.com",
        "Disqus":       f"https://disqus.com/by/{u}/",
        "TripAdvisor":  f"https://www.tripadvisor.com/members/{u}",
        "Scribd":       f"https://www.scribd.com/{u}",
        "Slideshare":   f"https://www.slideshare.net/{u}",
    }
    found, notfound = [], []

    def chk(item):
        n, url = item
        try:
            r = _get(url, timeout=6, allow_redirects=True)
            txt = r.text.lower()
            bad = ("user not found", "page not found", "doesn't exist",
                   "not found", "hesap bulunamadi", "sayfa bulunamadi",
                   "sorry, nobody on reddit", "no such user")
            if r.status_code == 200 and not any(b in txt for b in bad):
                return (n, url, True)
        except:
            pass
        return (n, url, False)

    with ThreadPoolExecutor(max_workers=25) as ex:
        for n, url, ok in ex.map(chk, sites.items()):
            (found if ok else notfound).append((n, url))

    out = [f"Hedef: {u}", f"Bulunan: {len(found)} / {len(sites)}", ""]
    if found:
        out.append("== BULUNDU ==")
        for n, url in found: out.append(f"  [+] {n}: {url}")
    if notfound:
        out.append("")
        out.append(f"== YOK ({len(notfound)}) ==")
        out.append("  " + ", ".join(n for n, _ in notfound))
    return "\n".join(out)


def fn_nickcheck(u): return fn_username(u)


def fn_tgtrace(u):
    u = u.replace("@", "").strip()
    out = []
    try:
        r = _get(f"https://t.me/{u}")
        if r.status_code == 200:
            s = BeautifulSoup(r.text, "html.parser")
            t = s.find(class_="tgme_page_title")
            d = s.find(class_="tgme_page_description")
            img = s.find("meta", property="og:image")
            extra = s.find(class_="tgme_page_extra")
            if t: out.append(f"Isim: {t.get_text(strip=True)}")
            if d: out.append(f"Aciklama: {d.get_text(strip=True)[:300]}")
            if extra: out.append(f"Uye/Bilgi: {extra.get_text(strip=True)}")
            if img and img.get("content"): out.append(f"Avatar: {img['content']}")
        else:
            out.append("Kullanici bulunamadi.")
    except Exception as e:
        out.append(f"Hata: {e}")
    out.append(f"Link: https://t.me/{u}")
    return "\n".join(out)


def fn_iplookup(ip):
    try:
        r = _get(f"http://ip-api.com/json/{ip}?fields=66846719&lang=tr").json()
        if r.get("status") == "success":
            return (f"IP: {r.get('query')}\n"
                    f"Ulke: {r.get('country')} ({r.get('countryCode')}) [{r.get('continent','-')}]\n"
                    f"Bolge: {r.get('regionName')}\nSehir: {r.get('city')}\n"
                    f"Posta: {r.get('zip','-')}\nKoordinat: {r.get('lat')}, {r.get('lon')}\n"
                    f"Timezone: {r.get('timezone')}\n"
                    f"ISP: {r.get('isp')}\nOrg: {r.get('org')}\nAS: {r.get('as')}\n"
                    f"Reverse DNS: {r.get('reverse','-')}\n"
                    f"Proxy/VPN: {'EVET' if r.get('proxy') else 'Hayir'}\n"
                    f"Hosting: {'EVET' if r.get('hosting') else 'Hayir'}\n"
                    f"Mobil: {'EVET' if r.get('mobile') else 'Hayir'}\n"
                    f"Harita: https://www.google.com/maps?q={r.get('lat')},{r.get('lon')}")
        return f"Hata: {r.get('message')}"
    except Exception as e:
        return f"Hata: {e}"


def fn_iplocate(ip): return fn_iplookup(ip)


def fn_ipport(ip):
    ports = [21, 22, 23, 25, 53, 80, 110, 135, 139, 143, 443, 445, 993, 995,
             1723, 3306, 3389, 5432, 5900, 6379, 8080, 8443, 8888, 27017]
    opened = []

    def scan(p):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        try:
            if s.connect_ex((ip, p)) == 0: opened.append(p)
        except: pass
        finally: s.close()

    try:
        with ThreadPoolExecutor(max_workers=40) as ex:
            list(ex.map(scan, ports))
    except Exception as e:
        return f"Hata: {e}"

    if not opened: return f"Acik port yok ({len(ports)} tarandi)."
    svc = {21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS", 80: "HTTP",
           110: "POP3", 135: "RPC", 139: "NetBIOS", 143: "IMAP", 443: "HTTPS",
           445: "SMB", 993: "IMAPS", 995: "POP3S", 1723: "PPTP", 3306: "MySQL",
           3389: "RDP", 5432: "PostgreSQL", 5900: "VNC", 6379: "Redis",
           8080: "HTTP-Alt", 8443: "HTTPS-Alt", 8888: "HTTP-Alt", 27017: "MongoDB"}
    out = [f"Hedef: {ip}", f"Acik port: {len(opened)} / {len(ports)}", ""]
    for p in sorted(opened):
        out.append(f"  [+] {p}/tcp ({svc.get(p,'?')})")
    return "\n".join(out)


def fn_whois(d):
    if not WHOIS_OK: return "python-whois kurulu degil."
    try:
        w = whois.whois(d)
        out = [f"Domain: {d}", ""]
        for k in ("domain_name", "registrar", "org", "country", "creation_date",
                  "expiration_date", "updated_date", "name_servers", "status", "emails"):
            v = w.get(k)
            if v:
                if isinstance(v, list):
                    v = ", ".join(str(x) for x in v[:5])
                out.append(f"{k}: {str(v)[:200]}")
        return "\n".join(out) if len(out) > 2 else "Sonuc yok."
    except Exception as e:
        return f"Hata: {e}"


def fn_dns(d):
    if not DNS_OK: return "dnspython kurulu degil."
    out = [f"Domain: {d}", ""]
    for rt in ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA", "CAA"]:
        try:
            ans = dns.resolver.resolve(d, rt)
            vals = [str(x) for x in ans][:5]
            out.append(f"{rt}: {', '.join(vals)[:200]}")
        except dns.resolver.NoAnswer:
            pass
        except dns.resolver.NXDOMAIN:
            return f"Domain bulunamadi: {d}"
        except:
            pass
    return "\n".join(out)


def fn_subdomain(d):
    subs = set()
    try:
        r = _get(f"https://crt.sh/?q=%25.{d}&output=json", timeout=20)
        if r.status_code == 200:
            for x in r.json():
                for s in str(x.get('name_value', '')).split('\n'):
                    s = s.strip().lstrip('*.')
                    if s.endswith(d): subs.add(s)
    except:
        pass

    common = ["www", "mail", "ftp", "admin", "blog", "shop", "api", "dev", "test",
              "staging", "portal", "vpn", "cdn", "static", "app", "m", "mobile",
              "old", "new", "beta"]

    def chk(s):
        try:
            socket.gethostbyname(s)
            return s
        except:
            return None

    with ThreadPoolExecutor(max_workers=20) as ex:
        for r in ex.map(chk, [f"{s}.{d}" for s in common]):
            if r: subs.add(r)

    if not subs: return "Subdomain bulunamadi."
    out = [f"Domain: {d}", f"Bulunan: {len(subs)}", ""]
    for s in sorted(subs)[:40]:
        try:
            ip = socket.gethostbyname(s)
        except:
            ip = "-"
        out.append(f"  {s}  ->  {ip}")
    if len(subs) > 40:
        out.append(f"  ... ve {len(subs)-40} tane daha")
    return "\n".join(out)


def fn_ssl(d):
    try:
        c = ssl.create_default_context()
        with socket.create_connection((d, 443), timeout=10) as sock:
            with c.wrap_socket(sock, server_hostname=d) as ss:
                cert = ss.getpeercert()
                cipher = ss.cipher()
                ver = ss.version()
        subj = dict(x[0] for x in cert['subject'])
        iss = dict(x[0] for x in cert['issuer'])
        out = [f"Domain: {d}", ""]
        out.append(f"CN: {subj.get('commonName','-')}")
        out.append(f"Org: {subj.get('organizationName','-')}")
        out.append(f"Ulke: {subj.get('countryName','-')}")
        out.append(f"Saglayici: {iss.get('organizationName','-')}")
        out.append(f"Bitis: {cert.get('notAfter','-')}")
        out.append(f"Baslangic: {cert.get('notBefore','-')}")
        sans = cert.get('subjectAltName', [])
        if sans:
            out.append(f"SAN ({len(sans)}):")
            for _, v in sans[:10]:
                out.append(f"  - {v}")
        out.append(f"TLS: {ver}")
        out.append(f"Cipher: {cipher[0] if cipher else '-'}")
        return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"


def fn_phone(num):
    if not PHONE_OK: return "phonenumbers kurulu degil."
    if not num.startswith('+'): num = '+' + num
    try:
        p = phonenumbers.parse(num, None)
        if not phonenumbers.is_valid_number(p): return "Gecersiz numara."
        out = [f"Numara: {num}", ""]
        out.append(f"Ulke: {pn_geo.description_for_number(p, 'tr') or '-'}")
        out.append(f"Operator: {pn_carrier.name_for_number(p, 'tr') or '-'}")
        out.append(f"Format: {phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.INTERNATIONAL)}")
        out.append(f"E164: {phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.E164)}")
        out.append(f"Ulusal: {phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.NATIONAL)}")
        out.append(f"Ulke kodu: +{p.country_code}")
        out.append(f"Tip: {'Mobil' if phonenumbers.number_type(p) == phonenumbers.PhoneNumberType.MOBILE else 'Sabit/Bilinmiyor'}")
        return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"


def fn_hlr(num): return fn_phone(num)
def fn_phoneinfoga(num): return fn_phone(num)


def fn_leak(q):
    out = [f"Sorgu: {q}", ""]
    try:
        r = _get(f"https://haveibeenpwned.com/api/v3/breachedaccount/{q}",
                 headers={"User-Agent": "Drax"})
        if r.status_code == 200:
            d = r.json()
            out.append(f"[HIBP] {len(d)} sizinti:")
            for x in d[:15]:
                out.append(f"  - {x.get('Name')} | {x.get('BreachDate','-')} | {x.get('PwnCount',0):,} hesap")
        elif r.status_code == 404:
            out.append("[HIBP] Sizinti bulunamadi.")
    except Exception as e:
        out.append(f"[HIBP] Hata: {e}")

    if '@' in q:
        try:
            r = _get(f"https://emailrep.io/{q}")
            if r.status_code == 200:
                d = r.json()
                out.append("")
                out.append("[EmailRep]")
                out.append(f"  Reputation: {d.get('reputation','-')}")
                out.append(f"  Suspicious: {d.get('suspicious','-')}")
                out.append(f"  Data Breach: {d.get('details',{}).get('data_breach','-')}")
        except:
            pass
    return "\n".join(out)


def fn_email_osint(e): return fn_email(e)


# ============================================================
#   SOSYAL MEDYA
# ============================================================
def fn_github(q):
    q = q.strip().lstrip("@")
    try:
        r = _get(f"https://api.github.com/users/{q}",
                 headers={"Accept": "application/vnd.github+json", "User-Agent": "Drax"})
        if r.status_code == 200:
            d = r.json()
            out = [f"GitHub: @{d.get('login')}", ""]
            out.append(f"Isim: {d.get('name','-')}")
            out.append(f"Bio: {d.get('bio','-')}")
            out.append(f"Sirket: {d.get('company','-')}")
            out.append(f"Lokasyon: {d.get('location','-')}")
            out.append(f"Blog: {d.get('blog','-')}")
            out.append(f"Email: {d.get('email','-')}")
            out.append(f"Twitter: {d.get('twitter_username','-')}")
            out.append(f"Repo: {d.get('public_repos',0)} | Gist: {d.get('public_gists',0)}")
            out.append(f"Takipci: {d.get('followers',0)} | Takip: {d.get('following',0)}")
            out.append(f"Kayit: {d.get('created_at','-')}")
            return "\n".join(out)
        elif r.status_code == 404:
            r2 = _get(f"https://api.github.com/search/users?q={q}",
                      headers={"User-Agent": "Drax"})
            if r2.status_code == 200:
                items = r2.json().get('items', [])
                if items:
                    out = [f"'{q}' icin {len(items)} sonuc:", ""]
                    for u in items[:10]:
                        out.append(f"  @{u['login']}  ->  {u['html_url']}")
                    return "\n".join(out)
            return f"Kullanici bulunamadi: {q}"
        return f"Hata: {r.status_code}"
    except Exception as e:
        return f"Hata: {e}"


def fn_reddit(q):
    q_enc = urllib.parse.quote(q)
    try:
        r = _get(f"https://www.reddit.com/search.json?q={q_enc}&limit=15",
                 headers={"User-Agent": "Drax/1.0"})
        if r.status_code == 200:
            d = r.json().get('data', {}).get('children', [])
            if not d: return f"'{q}' icin Reddit sonucu yok."
            out = [f"Reddit: '{q}' - {len(d)} sonuc", ""]
            for x in d[:12]:
                p = x['data']
                out.append(f"r/{p.get('subreddit')}: {p.get('title','')[:80]}")
                out.append(f"  -> https://reddit.com{p.get('permalink','')}")
            return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"
    return f"Reddit: https://www.reddit.com/search/?q={q_enc}"


def fn_twitter(q):
    return f"Twitter/X: https://twitter.com/search?q={urllib.parse.quote(q)}\n(Nitter: https://nitter.net/search?q={urllib.parse.quote(q)})"


def fn_youtube(q):
    q_enc = urllib.parse.quote(q)
    try:
        r = _get(f"https://www.youtube.com/results?search_query={q_enc}", timeout=15)
        vids = re.findall(r'"videoId":"([^"]+)".*?"text":"([^"]{5,120})"', r.text)[:8]
        if vids:
            out = [f"YouTube: '{q}' - {len(vids)} video", ""]
            for vid, title in vids:
                out.append(f"  {title[:80]}")
                out.append(f"    https://youtu.be/{vid}")
            return "\n".join(out)
    except:
        pass
    return f"YouTube: https://www.youtube.com/results?search_query={q_enc}"


def fn_tiktok(u):
    u = u.strip().lstrip("@")
    try:
        r = _get(f"https://www.tiktok.com/@{u}", timeout=10)
        m = re.search(r'"followerCount":(\d+)', r.text)
        f = m.group(1) if m else "?"
        m = re.search(r'"followingCount":(\d+)', r.text)
        fo = m.group(1) if m else "?"
        m = re.search(r'"heartCount":(\d+)', r.text)
        h = m.group(1) if m else "?"
        m = re.search(r'"videoCount":(\d+)', r.text)
        v = m.group(1) if m else "?"
        m = re.search(r'"nickname":"([^"]+)"', r.text)
        n = m.group(1) if m else "?"
        m = re.search(r'"signature":"([^"]*)"', r.text)
        s = m.group(1) if m else "-"
        return (f"TikTok: @{u}\nIsim: {n}\nBio: {s[:200]}\n"
                f"Takipci: {f} | Takip: {fo}\nBegeni: {h} | Video: {v}")
    except Exception as e:
        return f"Hata: {e}"


def fn_instagram(u):
    u = u.strip().lstrip("@")
    try:
        r = _get(f"https://www.instagram.com/{u}/?__a=1&__d=dis", timeout=10)
        if r.status_code == 200 and 'graphql' in r.text:
            d = r.json().get('graphql', {}).get('user', {})
            if d:
                out = [f"Instagram: @{d.get('username')}", ""]
                out.append(f"Isim: {d.get('full_name','-')}")
                out.append(f"Bio: {d.get('biography','-')[:200]}")
                out.append(f"Takipci: {d.get('edge_followed_by',{}).get('count',0)}")
                out.append(f"Takip: {d.get('edge_follow',{}).get('count',0)}")
                out.append(f"Gonderi: {d.get('edge_owner_to_timeline_media',{}).get('count',0)}")
                out.append(f"Private: {d.get('is_private')}")
                out.append(f"Verified: {d.get('is_verified')}")
                return "\n".join(out)
    except:
        pass
    try:
        r = _get(f"https://www.instagram.com/{u}/", timeout=10)
        m = re.search(r'<meta property="og:description" content="([^"]+)"', r.text)
        if m:
            return f"Instagram: @{u}\n{m.group(1)[:400]}"
    except:
        pass
    return f"Instagram: @{u}\nProfil cekilemedi (login gerekiyor olabilir).\nLink: https://www.instagram.com/{u}/"


def fn_telegram_search(u): return fn_tgtrace(u)


def fn_social_search(q):
    q_enc = urllib.parse.quote(q)
    out = [f"Arama: {q}", ""]

    try:
        r = _get(f"https://api.github.com/search/users?q={q_enc}",
                 headers={"User-Agent": "Drax"})
        if r.status_code == 200:
            items = r.json().get('items', [])
            if items:
                out.append(f"[GitHub] {len(items)} kullanici")
                for u in items[:5]:
                    out.append(f"  @{u['login']}  ->  {u['html_url']}")
    except:
        pass

    try:
        r = _get(f"https://www.reddit.com/search.json?q={q_enc}&limit=10",
                 headers={"User-Agent": "Drax/1.0"})
        if r.status_code == 200:
            d = r.json().get('data', {}).get('children', [])
            if d:
                out.append(f"\n[Reddit] {len(d)} sonuc")
                for x in d[:5]:
                    p = x['data']
                    out.append(f"  r/{p.get('subreddit')}: {p.get('title','')[:80]}")
    except:
        pass

    try:
        r = _get(f"https://www.youtube.com/results?search_query={q_enc}", timeout=15)
        vids = re.findall(r'"title":\{"runs":\[\{"text":"([^"]+)".*?"videoId":"([^"]+)"', r.text)[:5]
        if vids:
            out.append(f"\n[YouTube] {len(vids)} video")
            for t, vid in vids:
                out.append(f"  {t[:80]} -> https://youtu.be/{vid}")
    except:
        pass

    out.append("")
    out.append("[Direkt Linkler]")
    out.append(f"  Google: https://www.google.com/search?q={q_enc}")
    out.append(f"  Twitter: https://twitter.com/search?q={q_enc}")
    out.append(f"  LinkedIn: https://www.linkedin.com/search/results/all/?keywords={q_enc}")
    return "\n".join(out)


def fn_yt_channel(u):
    u = u.replace("@", "").strip()
    url = f"https://www.youtube.com/@{u}"
    try:
        r = _get(url, timeout=15)
        if r.status_code != 200: return "Kanal bulunamadi."
        html = r.text
        out = [f"YouTube: @{u}", ""]
        m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
        if m: out.append(f"Kanal: {m.group(1)}")
        m = re.search(r'"subscriberCountText":\{"accessibility".*?"simpleText":"([^"]+)"', html)
        if not m:
            m = re.search(r'"subscriberCountText":\{"simpleText":"([^"]+)"', html)
        if m: out.append(f"Abone: {m.group(1)}")
        m = re.search(r'"videosCountText":\{"runs":\[\{"text":"([^"]+)"', html)
        if m: out.append(f"Video: {m.group(1)}")
        m = re.search(r'"viewCountText":\{"simpleText":"([^"]+)"', html)
        if m: out.append(f"Izlenme: {m.group(1)}")
        m = re.search(r'"joinedDateText":\{"runs":\[\{"text":"([^"]+)"', html)
        if m: out.append(f"Katilma: {m.group(1)}")
        m = re.search(r'"description":"([^"]{1,300})"', html)
        if m: out.append(f"Aciklama: {m.group(1)[:200]}")
        m = re.search(r'"country":\{"simpleText":"([^"]+)"', html)
        if m: out.append(f"Ulke: {m.group(1)}")
        out.append(f"Link: {url}")
        return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"


def fn_pastebin(q):
    return fn_psbdmp(q)


def fn_sherlock(u): return fn_username(u)
def fn_maigret(u): return fn_username(u)
def fn_holehe(e): return fn_email(e)
def fn_blackbird(q): return f"Blackbird CLI: blackbird -u {q}\nhttps://github.com/p1ngul1n0/blackbird"
def fn_whatsmyname(u): return fn_username(u)


def fn_epieos(e):
    if '@' not in e: return "Email gerekli."
    return fn_email(e)


def fn_telegram_checker(n): return fn_phone(n)
def fn_telerecon(q): return fn_tgtrace(q)


def fn_instaloader(u):
    return f"Instaloader CLI ile cekilebilir:\n  instaloader {u}\n\n{fn_instagram(u)}"


def fn_masto(u):
    return f"Masto CLI: masto {u}\nhttps://github.com/C3n7ral051nt4g3ncy/Masto"


# ============================================================
#   TELEFON & EMAIL
# ============================================================
def fn_whatsapp_osint(num):
    c = num.replace("+", "").replace(" ", "")
    return f"WhatsApp: https://wa.me/{c}\nTelegram: https://t.me/+{c}"


def fn_email_valid(e): return fn_email(e)


# ============================================================
#   DOMAIN & DNS
# ============================================================
def fn_crtsh(d):
    try:
        r = _get(f"https://crt.sh/?q=%25.{d}&output=json", timeout=25)
        if r.status_code == 200:
            data = r.json()
            subs = set()
            for x in data:
                for s in str(x.get('name_value', '')).split('\n'):
                    s = s.strip().lstrip('*.')
                    if s.endswith(d): subs.add(s)
            if not subs: return f"Sonuc yok: {d}"
            out = [f"Domain: {d}", f"Subdomain: {len(subs)}", ""]
            for s in sorted(subs)[:50]:
                out.append(f"  {s}")
            if len(subs) > 50:
                out.append(f"  ... ve {len(subs)-50} daha")
            return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"
    return "Sonuc yok."


def fn_viewdns(d):
    out = [f"Domain: {d}", ""]
    if DNS_OK:
        for rt in ["A", "MX", "NS", "TXT"]:
            try:
                ans = dns.resolver.resolve(d, rt)
                out.append(f"{rt}: {', '.join(str(x) for x in ans)[:200]}")
            except:
                pass
    try:
        ip = socket.gethostbyname(d)
        out.append(f"\nIP: {ip}")
        out.append(f"IP Bilgisi: https://ipinfo.io/{ip}")
    except:
        pass
    return "\n".join(out)


def fn_securitytrails(d): return fn_crtsh(d)
def fn_theharvester(d): return fn_crtsh(d)
def fn_amass(d): return fn_subdomain(d)
def fn_subfinder(d): return fn_subdomain(d)
def fn_assetfinder(d): return fn_subdomain(d)
def fn_findomain(d): return fn_subdomain(d)
def fn_dnsrecon(d): return fn_dns(d)
def fn_fierce(d): return fn_subdomain(d)
def fn_dnsdumpster(d): return fn_crtsh(d)
def fn_whoisxml(d): return fn_whois(d)
def fn_whois_history(d): return fn_whois(d)
def fn_dnslytics(d): return fn_dns(d)
def fn_dnsgoogle(d): return fn_dns(d)
def fn_passivedns(d): return fn_crtsh(d)
def fn_dnshistory(d): return fn_crtsh(d)


# ============================================================
#   IP & AG
# ============================================================
def fn_virustotal(q):
    if re.match(r'^\d+\.\d+\.\d+\.\d+$', q):
        url = f"https://www.virustotal.com/gui/ip-address/{q}"
    elif re.match(r'^[a-fA-F0-9]{32,64}$', q):
        url = f"https://www.virustotal.com/gui/file/{q}"
    else:
        url = f"https://www.virustotal.com/gui/domain/{q}"
    return f"VirusTotal API key olmadan sonuc cekilemiyor.\nManuel kontrol: {url}"


def fn_shodan(q):
    try:
        if not re.match(r'^\d+\.\d+\.\d+\.\d+$', q):
            q = socket.gethostbyname(q)
        r = _get(f"https://internetdb.shodan.io/{q}", timeout=10)
        if r.status_code == 200:
            d = r.json()
            out = [f"IP: {q}", ""]
            out.append(f"Portlar: {', '.join(map(str, d.get('ports',[])))}")
            out.append(f"Hostnames: {', '.join(d.get('hostnames',[])) or '-'}")
            out.append(f"CPE: {', '.join(d.get('cpe',[])) or '-'}")
            out.append(f"Tags: {', '.join(d.get('tags',[])) or '-'}")
            vulns = d.get('vulns', [])
            if vulns:
                out.append(f"Zafiyetler ({len(vulns)}):")
                for v in vulns[:15]:
                    out.append(f"  - {v}")
            return "\n".join(out)
        return f"Bilgi yok: {q}"
    except Exception as e:
        return f"Hata: {e}"


def fn_censys(q):
    if re.match(r'^\d+\.\d+\.\d+\.\d+$', q):
        return fn_shodan(q)
    return "IP gerekli."


def fn_greynoise(ip): return fn_shodan(ip)


def fn_otx(ip):
    try:
        r = _get(f"https://otx.alienvault.com/api/v1/indicators/IPv4/{ip}/general", timeout=12)
        if r.status_code == 200:
            d = r.json()
            out = [f"IP: {ip}", ""]
            out.append(f"Ulke: {d.get('country_name','-')} ({d.get('country_code','-')})")
            out.append(f"ASN: {d.get('asn','-')}")
            out.append(f"Pulse sayisi: {d.get('pulse_info',{}).get('count',0)}")
            pulses = d.get('pulse_info', {}).get('pulses', [])[:5]
            if pulses:
                out.append("Son pulse'lar:")
                for p in pulses:
                    out.append(f"  - {p.get('name','-')[:80]}")
            return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"
    return "Sonuc yok."


def fn_abuseipdb(ip):
    return (f"IP: {ip}\n"
            f"Web kontrol: https://www.abuseipdb.com/check/{ip}\n"
            f"(API key gerekli)")


def fn_ipinfo(ip):
    try:
        r = _get(f"https://ipinfo.io/{ip}/json")
        if r.status_code == 200:
            d = r.json()
            return (f"IP: {d.get('ip')}\n"
                    f"Hostname: {d.get('hostname','-')}\n"
                    f"Sehir: {d.get('city','-')}\nBolge: {d.get('region','-')}\n"
                    f"Ulke: {d.get('country','-')}\nKonum: {d.get('loc','-')}\n"
                    f"Org: {d.get('org','-')}\nTimezone: {d.get('timezone','-')}")
    except Exception as e:
        return f"Hata: {e}"
    return "Sonuc yok."


def fn_threatcrowd(d):
    try:
        r = _get(f"https://www.threatcrowd.org/searchApi/v2/domain/report/?domain={d}", timeout=10)
        if r.status_code == 200:
            data = r.json()
            out = [f"Domain: {d}", ""]
            out.append(f"Resolutions: {len(data.get('resolutions',[]))}")
            for x in data.get('resolutions', [])[:10]:
                out.append(f"  {x.get('ip_address')} ({x.get('last_resolved','-')})")
            out.append(f"Subdomains: {len(data.get('subdomains',[]))}")
            for s in data.get('subdomains', [])[:10]:
                out.append(f"  {s}")
            return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"
    return "Sonuc yok."


def fn_alienvault(ip): return fn_otx(ip)
def fn_threatminer(ip): return fn_otx(ip)
def fn_hybrid(q): return fn_otx(q) if re.match(r'^\d+\.\d+\.\d+\.\d+$', q) else "IP gerekli."
def fn_threatfox(q): return fn_otx(q) if re.match(r'^\d+\.\d+\.\d+\.\d+$', q) else "IP gerekli."


def fn_adsb(q): return "ADS-B Exchange: https://globe.adsbexchange.com/"
def fn_marinetraffic(q): return f"MarineTraffic: https://www.marinetraffic.com/en/ais/index/search/all?keyword={q}"
def fn_flightradar(q): return f"FlightRadar24: https://www.flightradar24.com/data/aircraft/{q}"
def fn_radiogarden(q): return f"RadioGarden: https://radio.garden/search?q={urllib.parse.quote(q)}"


# ============================================================
#   GORSEL
# ============================================================
def fn_reverse_image(url):
    enc = urllib.parse.quote(url, safe='')
    return (f"Google Lens: https://lens.google.com/uploadbyurl?url={enc}\n"
            f"Yandex: https://yandex.com/images/search?url={enc}&rpt=imageview\n"
            f"TinEye: https://tineye.com/search?url={enc}\n"
            f"Bing: https://www.bing.com/images/search?q=imgurl:{enc}\n"
            f"Baidu: https://graph.baidu.com/details?image={enc}")


def fn_google_lens(u): return fn_reverse_image(u)
def fn_yandex_reverse(u): return fn_reverse_image(u)
def fn_tineye(u): return fn_reverse_image(u)
def fn_baidu_image(u): return fn_reverse_image(u)
def fn_karma_decay(u): return fn_reverse_image(u)


def fn_meta(url):
    try:
        r = _get(url, timeout=20, stream=True)
        ctype = r.headers.get("Content-Type", "")
        size = r.headers.get("Content-Length", "?")
        out = [f"URL: {url}", f"Tip: {ctype}", f"Boyut: {size} byte", ""]
        if "image" in ctype and PIL_OK:
            img = Image.open(io.BytesIO(r.content))
            out.append(f"Format: {img.format}")
            out.append(f"Boyut: {img.size[0]}x{img.size[1]}")
            ex = img._getexif()
            if ex:
                out.append("\n== EXIF ==")
                for k, v in list(ex.items()):
                    tag = TAGS.get(k, k)
                    if tag == "GPSInfo":
                        try:
                            g = v
                            def _c(x):
                                return x[0] + x[1] / 60 + x[2] / 3600
                            lat = _c(g[2]); lon = _c(g[4])
                            if g[1] == 'S': lat = -lat
                            if g[3] == 'W': lon = -lon
                            out.append(f"GPS: {lat}, {lon}")
                            out.append(f"  https://maps.google.com/?q={lat},{lon}")
                        except:
                            pass
                        continue
                    out.append(f"{tag}: {str(v)[:150]}")
            else:
                out.append("EXIF yok.")
        return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"


def fn_exiftool(u): return fn_meta(u)
def fn_fotoforensics(u): return fn_reverse_image(u)
def fn_pimeyes(q): return "PimEyes (ucretli): https://pimeyes.com/"


# ============================================================
#   SIZINTI
# ============================================================
def fn_psbdmp(q):
    try:
        r = _get(f"https://psbdmp.ws/api/v3/search/{q}", timeout=10)
        if r.status_code == 200:
            d = r.json()
            if d.get('count', 0) == 0:
                return f"'{q}' icin paste bulunamadi."
            out = [f"Sorgu: {q}", f"Paste sayisi: {d.get('count')}", ""]
            for p in d.get('data', [])[:15]:
                out.append(f"  ID: {p.get('id')} | {p.get('time','-')}")
                out.append(f"    https://pastebin.com/{p.get('id')}")
            return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"
    return "Sonuc yok."


def fn_breachdir(e):
    return f"BreachDirectory: https://breachdirectory.org/\nEmail: {e}\n(API key gerekli)"


def fn_crackstation(h):
    h = h.strip().lower()
    length = len(h)
    tip = {32: "MD5", 40: "SHA1", 64: "SHA256"}.get(length, "?")
    out = [f"Hash: {h}", f"Tip: {tip}", f"Uzunluk: {length}", ""]
    common = {
        "5d41402abc4b2a76b9719d911017c592": "hello",
        "098f6bcd4621d373cade4e832627b4f6": "test",
        "e10adc3949ba59abbe56e057f20f883e": "123456",
        "21232f297a57a5a743894a0e4a801fc3": "admin",
        "25d55ad283aa400af464c76d713c07ad": "12345678",
        "5f4dcc3b5aa765d61d8327deb882cf99": "password",
        "d8578edf8458ce06fbc5bb76a58c5ca4": "qwerty",
        "e99a18c428cb38d5f260853678922e03": "abc123",
        "5baa61e4c9b93f3f0682250b6cf8331b7ee68fd8": "password",
    }
    if h in common:
        out.append(f"[Cozuldu] {common[h]}")
    else:
        out.append("[Cozulemedi] CrackStation: https://crackstation.net/")
    return "\n".join(out)


def fn_hashes_com(h): return fn_crackstation(h)
def fn_md5decrypt(h): return fn_crackstation(h)


def fn_dehashed(q):
    return f"Dehashed (ucretli): https://dehashed.com/search?query={q}"


def fn_intelx(q):
    return f"IntelX: https://intelx.io/?s={q}\n(API key gerekli)"


def fn_ahmia(q): return fn_psbdmp(q)


def fn_voidaccess(q):
    return f"VoidAccess CLI: voidaccess {q}\nhttps://github.com/ItzCrazyKns/VoidAccess"


def fn_urlhaus(u):
    return f"URLhaus: https://urlhaus.abuse.ch/browse.php?search={u}"


# ============================================================
#   FRAMEWORK (CLI araclari - komut gosterir)
# ============================================================
def fn_spiderfoot(q): return f"SpiderFoot CLI: python sf.py -s {q} -m all"
def fn_reconng(q): return f"Recon-ng CLI: recon-ng -w {q}"
def fn_maryam(q): return f"Maryam CLI: maryam -d {q}"
def fn_sn0int(q): return f"sn0int CLI: sn0int scan {q}"
def fn_maltego(q): return "Maltego GUI: https://www.maltego.com/"
def fn_trufflehog(u): return f"TruffleHog CLI: trufflehog {u}"
def fn_gitleaks(u): return f"Gitleaks CLI: gitleaks detect --source={u}"
def fn_gowitness(u): return f"GoWitness CLI: gowitness single {u}"
def fn_cyberchef(q): return "CyberChef: https://gchq.github.io/CyberChef/"
def fn_gephi(q): return "Gephi: https://gephi.org/"
def fn_dorkhound(q): return "Dorkhound: https://github.com/six2dez/dorkhound"
def fn_pagodo(q): return "Pagodo: https://github.com/opsdisk/pagodo"
def fn_distill(u): return "Distill (ucretli): https://distill.io/"
def fn_4cat(q): return "4CAT: https://github.com/digitalmethodsinitiative/4cat"
def fn_zeeschuimer(q): return "Zeeschuimer: https://github.com/digitalmethodsinitiative/zeeschuimer"


# ============================================================
#   WEB ARACLARI
# ============================================================
def fn_wayback(u):
    u = u.replace("http://", "").replace("https://", "").rstrip("/")
    try:
        r = _get(f"http://archive.org/wayback/available?url={u}", timeout=10)
        if r.status_code == 200:
            d = r.json()
            snap = d.get('archived_snapshots', {}).get('closest', {})
            out = [f"URL: {u}"]
            if snap:
                out.append(f"En son arsiv: {snap.get('timestamp','-')}")
                out.append(f"Link: {snap.get('url','-')}")
            else:
                out.append("Arsiv yok.")
            out.append(f"Tum arsiv: https://web.archive.org/web/*/{u}")
            return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"
    return f"Wayback: https://web.archive.org/web/*/{u}"


def fn_archive_today(u): return fn_wayback(u)


def fn_urlshort(u):
    if not u.startswith("http"): u = "https://" + u
    try:
        r = requests.post("https://urlsmush.com/api.php", json={"url": u},
                          headers={"Content-Type": "application/json"}, timeout=10)
        if r.status_code == 200:
            d = r.json()
            if d.get('status') == 'success':
                return d.get('data', {}).get('short_url')
    except:
        pass
    return "Kisaltilamadi."


def fn_url_expand(s):
    if not s.startswith("http"): s = "https://" + s
    try:
        r = requests.get(s, allow_redirects=True, timeout=15, headers=HEADERS)
        out = [f"Kisa: {s}", f"Orijinal: {r.url}", ""]
        out.append("Redirect zinciri:")
        for h in r.history:
            out.append(f"  {h.status_code} -> {h.url}")
        out.append(f"Final: {r.status_code} -> {r.url}")
        return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"


def fn_urlscan(q):
    if q.startswith("http"):
        try:
            dom = urllib.parse.urlparse(q).netloc
            r = _get(f"https://urlscan.io/api/v1/search/?q=domain:{dom}")
            if r.status_code == 200:
                d = r.json()
                out = [f"URLScan: {d.get('total',0)} sonuc", ""]
                for x in d.get('results', [])[:10]:
                    out.append(f"  {x.get('page',{}).get('url','-')}")
                return "\n".join(out)
        except:
            pass
    return f"URLScan: https://urlscan.io/search/#{urllib.parse.quote(q)}"


def fn_urlscan_search(q): return fn_urlscan(q)


def fn_builtwith(d):
    if not d.startswith("http"): d = "https://" + d
    try:
        r = _get(d, timeout=15)
        html = r.text.lower()
        headers_d = {k.lower(): v for k, v in r.headers.items()}
        out = [f"URL: {d}", f"Durum: {r.status_code}", ""]
        out.append(f"Server: {headers_d.get('server','-')}")
        out.append(f"Powered-By: {headers_d.get('x-powered-by','-')}")
        out.append(f"Generator: {headers_d.get('x-generator','-')}")
        out.append("")
        out.append("== Tespit Edilen Teknolojiler ==")
        techs = {
            "WordPress": ["wp-content", "wp-includes"],
            "jQuery": ["jquery"],
            "Bootstrap": ["bootstrap"],
            "React": ["react"],
            "Vue.js": ["vue.js", "vue.min"],
            "Angular": ["angular"],
            "Google Analytics": ["google-analytics", "gtag"],
            "Cloudflare": ["cloudflare"],
            "Font Awesome": ["font-awesome", "fontawesome"],
            "Google Fonts": ["fonts.googleapis"],
        }
        found = []
        for t, keys in techs.items():
            if any(k in html for k in keys): found.append(t)
        out.append(", ".join(found) if found else "Tespit edilemedi.")
        return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"


def fn_wappalyzer(u): return fn_builtwith(u)
def fn_whatweb(u): return fn_builtwith(u)


def fn_adminfinder(url):
    if not url.startswith("http"): url = "http://" + url
    url = url.rstrip("/")
    paths = ["/admin", "/administrator", "/admin/login", "/wp-admin", "/wp-login.php",
             "/login", "/cp", "/cpanel", "/phpmyadmin", "/pma", "/yonetim", "/yonetim.php",
             "/panel", "/dashboard", "/manage", "/user/login", "/admin.php", "/adminpanel"]
    found = []

    def chk(p):
        try:
            r = requests.get(url + p, timeout=6, headers=HEADERS, allow_redirects=False)
            if r.status_code in (200, 301, 302, 401, 403):
                return f"[{r.status_code}] {url}{p}"
        except:
            pass
        return None

    with ThreadPoolExecutor(max_workers=15) as ex:
        for r in ex.map(chk, paths):
            if r: found.append(r)

    if not found: return f"Admin panel bulunamadi: {url}"
    out = [f"Hedef: {url}", f"Bulunan: {len(found)}", ""]
    out.extend(found)
    return "\n".join(out)


def fn_crawler(url):
    if not url.startswith("http"): url = "http://" + url
    try:
        r = requests.get(url, timeout=15, headers=HEADERS)
        s = BeautifulSoup(r.text, "html.parser")
        title = s.title.string.strip() if s.title and s.title.string else "-"
        links = set()
        for a in s.find_all("a", href=True):
            h = a["href"]
            if h.startswith(("http://", "https://")):
                links.add(h)
            elif h.startswith("/"):
                links.add(urllib.parse.urljoin(url, h))
        out = [f"URL: {url}", f"Baslik: {title}", f"Link: {len(links)}", ""]
        for l in sorted(links)[:30]:
            out.append(f"  {l}")
        if len(links) > 30:
            out.append(f"  ... ve {len(links)-30} daha")
        return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"


def fn_google_dork(q):
    return f"Google: https://www.google.com/search?q={urllib.parse.quote(q)}"


def fn_search_all(q):
    enc = urllib.parse.quote(q)
    return (f"Google: https://www.google.com/search?q={enc}\n"
            f"Bing: https://www.bing.com/search?q={enc}\n"
            f"DuckDuckGo: https://duckduckgo.com/?q={enc}\n"
            f"Yandex: https://yandex.com/search/?text={enc}\n"
            f"Brave: https://search.brave.com/search?q={enc}\n"
            f"Startpage: https://www.startpage.com/sp/search?query={enc}")


def fn_robots(d):
    if not d.startswith("http"): d = "https://" + d
    try:
        r = _get(d.rstrip("/") + "/robots.txt", timeout=10)
        if r.status_code == 200:
            return f"robots.txt:\n\n{r.text[:1500]}"
        return f"robots.txt yok ({r.status_code})"
    except Exception as e:
        return f"Hata: {e}"


def fn_sitemap(d):
    if not d.startswith("http"): d = "https://" + d
    try:
        r = _get(d.rstrip("/") + "/sitemap.xml", timeout=10)
        if r.status_code == 200:
            urls = re.findall(r'<loc>([^<]+)</loc>', r.text)[:30]
            out = [f"Sitemap: {len(urls)}+ URL", ""]
            out.extend(urls)
            return "\n".join(out)
        return f"sitemap.xml yok ({r.status_code})"
    except Exception as e:
        return f"Hata: {e}"


def fn_headers(url):
    if not url.startswith("http"): url = "https://" + url
    try:
        r = requests.head(url, timeout=10, headers=HEADERS, allow_redirects=True)
        out = [f"URL: {r.url}", f"Durum: {r.status_code}", ""]
        for k, v in r.headers.items():
            out.append(f"{k}: {v}")
        return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"


def fn_ssllabs(d): return fn_ssl(d)
def fn_hstshsts(d): return fn_ssl(d)
def fn_screenshot(u): return f"Screenshot: https://image.thum.io/get/width/1200/{u}"
def fn_radiogarden_link(q): return fn_radiogarden(q)


# ============================================================
#   GENERATOR & MISC
# ============================================================
def fn_genpass(n):
    try:
        n = int(n)
    except:
        n = 16
    if n < 4 or n > 128: n = 16
    chars = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    out = [f"Uzunluk: {n}", ""]
    for i in range(5):
        out.append("  " + "".join(random.choice(chars) for _ in range(n)))
    return "\n".join(out)


def fn_ua(n):
    try:
        n = int(n)
    except:
        n = 5
    if n < 1 or n > 30: n = 5
    tmpl = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{c}.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{f}.0) Gecko/20100101 Firefox/{f}.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{s}.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{c}.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    ]
    out = []
    for _ in range(n):
        t = random.choice(tmpl)
        out.append(t.format(c=random.randint(115, 131), f=random.randint(115, 130), s=random.randint(15, 18)))
    return "\n\n".join(out)


def fn_fake(g):
    g = (g or "E").upper()
    male = ["Mehmet", "Ahmet", "Ali", "Emre", "Mustafa", "Hasan", "Burak", "Onur", "Kerem", "Deniz"]
    female = ["Ayse", "Zeynep", "Elif", "Merve", "Fatma", "Eda", "Selin", "Derya", "Ece", "Busra"]
    last = ["Yilmaz", "Demir", "Kaya", "Sahin", "Celik", "Yildiz", "Aydin", "Ozturk", "Arslan", "Dogan"]
    cities = ["Istanbul", "Ankara", "Izmir", "Bursa", "Antalya", "Adana", "Konya"]
    fn_ = random.choice(male if g == "E" else female)
    ln = random.choice(last)
    out = [f"Ad: {fn_} {ln}",
           f"Cinsiyet: {'Erkek' if g=='E' else 'Kadin'}",
           f"Yas: {random.randint(18,65)}",
           f"Sehir: {random.choice(cities)}",
           f"Tel: +90 5{random.randint(10,59)} {random.randint(100,999)} {random.randint(1000,9999)}",
           f"Email: {fn_.lower()}.{ln.lower()}{random.randint(1,99)}@gmail.com",
           f"TC: {random.randint(10000000000,99999999999)}",
           f"Dogum: {random.randint(1,28):02d}.{random.randint(1,12):02d}.{random.randint(1960,2005)}"]
    return "\n".join(out)


def fn_hash(t):
    return (f"Metin: {t}\n\n"
            f"MD5:    {hashlib.md5(t.encode()).hexdigest()}\n"
            f"SHA1:   {hashlib.sha1(t.encode()).hexdigest()}\n"
            f"SHA256: {hashlib.sha256(t.encode()).hexdigest()}\n"
            f"SHA512: {hashlib.sha512(t.encode()).hexdigest()}")


def fn_hashid(h):
    h = h.strip()
    types = {32: "MD5", 40: "SHA-1", 56: "SHA-224", 64: "SHA-256", 96: "SHA-384",
             128: "SHA-512", 8: "CRC32", 16: "MySQL old / CRC"}
    return f"Hash: {h}\nUzunluk: {len(h)}\nTahmini tip: {types.get(len(h),'Bilinmiyor')}"


def fn_qr(d):
    enc = urllib.parse.quote(d)
    return f"QR Kod: https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={enc}"


def fn_mac(m):
    try:
        r = _get(f"https://api.macvendors.com/{m}", timeout=10)
        if r.status_code == 200:
            return f"MAC: {m}\nUretici: {r.text}"
        if r.status_code == 404:
            return f"MAC: {m}\nUretici bulunamadi."
    except Exception as e:
        return f"Hata: {e}"
    return "Sonuc yok."


def fn_imei(i): return f"IMEI: {i}\nTAC: {i[:8]}\nKontrol: https://www.imei.info/?imei={i}"


def fn_bitcoin(a):
    try:
        r = _get(f"https://blockchain.info/rawaddr/{a}", timeout=12)
        if r.status_code == 200:
            d = r.json()
            return (f"BTC: {a}\n"
                    f"Bakiye: {d.get('final_balance',0)/1e8:.8f} BTC\n"
                    f"Alinan: {d.get('total_received',0)/1e8:.8f} BTC\n"
                    f"Gonderilen: {d.get('total_sent',0)/1e8:.8f} BTC\n"
                    f"Islem: {d.get('n_tx',0)}")
    except Exception as e:
        return f"Hata: {e}"
    return "Sonuc yok."


def fn_etherscan(a): return f"ETH: {a}\nhttps://etherscan.io/address/{a}"
def fn_bscscan(a): return f"BSC: {a}\nhttps://bscscan.com/address/{a}"


def fn_geo(lat_lon):
    p = lat_lon.replace(",", " ").split()
    if len(p) >= 2:
        return (f"Konum: {p[0]}, {p[1]}\n"
                f"Google Maps: https://www.google.com/maps?q={p[0]},{p[1]}\n"
                f"OSM: https://www.openstreetmap.org/?mlat={p[0]}&mlon={p[1]}\n"
                f"Yandex: https://yandex.com/maps/?ll={p[1]},{p[0]}&z=15")
    return "Kullanim: 41.0082 28.9784"


def fn_zodiac(b):
    b = b.lower()
    m = {"koc": "21 Mart - 20 Nisan", "boga": "21 Nisan - 20 Mayis",
         "ikizler": "21 Mayis - 21 Haziran", "yengec": "22 Haziran - 22 Temmuz",
         "aslan": "23 Temmuz - 22 Agustos", "basak": "23 Agustos - 22 Eylul",
         "terazi": "23 Eylul - 22 Ekim", "akrep": "23 Ekim - 21 Kasim",
         "yay": "22 Kasim - 21 Aralik", "oglak": "22 Aralik - 20 Ocak",
         "kova": "21 Ocak - 18 Subat", "balik": "19 Subat - 20 Mart"}
    t = m.get(b)
    return f"{b.title()}: {t}" if t else "Gecersiz burc. koc/boga/ikizler/..."


def fn_cam(cc):
    cc = cc.upper().strip()
    try:
        r = _get(f"http://www.insecam.org/en/bycountry/{cc}/", timeout=15)
        if r.status_code == 200:
            ips = re.findall(r'href="(/en/view/\d+)"', r.text)[:20]
            if not ips: return f"{cc} icin kamera bulunamadi."
            out = [f"Ulke: {cc}", f"Kamera: {len(ips)}+", ""]
            for i in ips:
                out.append(f"  http://www.insecam.org{i}")
            return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"
    return "Sonuc yok."


# ============================================================
#   EKSTRA
# ============================================================
def fn_company(c):
    out = [f"Arama: {c}", ""]
    try:
        r = _get(f"https://api.opencorporates.com/v0.4/companies/search?q={urllib.parse.quote(c)}&per_page=10")
        if r.status_code == 200:
            comps = r.json().get('results', {}).get('companies', [])
            if comps:
                out.append(f"[OpenCorporates] {len(comps)} sonuc:")
                for x in comps[:8]:
                    c2 = x.get('company', {})
                    out.append(f"  {c2.get('name','-')} ({c2.get('jurisdiction_code','-')})")
                    out.append(f"    Numara: {c2.get('company_number','-')}")
                    out.append(f"    Durum: {c2.get('current_status','-')}")
    except Exception as e:
        out.append(f"[OpenCorp] Hata: {e}")
    return "\n".join(out)


def fn_crunchbase(c): return fn_company(c)
def fn_opencorporates(c): return fn_company(c)
def fn_mersis(c): return fn_company(c)


def fn_nvd(cve):
    try:
        r = _get(f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve.upper()}", timeout=15)
        if r.status_code == 200:
            d = r.json()
            v = d.get('vulnerabilities', [])
            if not v: return f"{cve} bulunamadi."
            c = v[0]['cve']
            out = [f"CVE: {c.get('id')}", f"Durum: {c.get('vulnStatus','-')}"]
            for d2 in c.get('descriptions', []):
                if d2.get('lang') == 'en':
                    out.append(f"Aciklama: {d2.get('value','')[:400]}")
                    break
            metrics = c.get('metrics', {})
            for k in ('cvssMetricV31', 'cvssMetricV30', 'cvssMetricV2'):
                if k in metrics:
                    m = metrics[k][0].get('cvssData', {})
                    out.append(f"CVSS: {m.get('baseScore')} ({m.get('baseSeverity','-')})")
                    break
            return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"
    return "Sonuc yok."


def fn_circl(cve):
    try:
        r = _get(f"https://cve.circl.lu/api/cve/{cve.upper()}", timeout=12)
        if r.status_code == 200:
            d = r.json()
            out = [f"CVE: {d.get('id')}", f"CVSS: {d.get('cvss','-')}"]
            out.append(f"Ozet: {d.get('summary','-')[:400]}")
            refs = d.get('references', [])[:5]
            if refs:
                out.append("Referanslar:")
                for r2 in refs:
                    out.append(f"  {r2}")
            return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"
    return "Sonuc yok."


def fn_exploitdb(q):
    return f"Exploit-DB: https://www.exploit-db.com/search?q={urllib.parse.quote(q)}"


def fn_mitre(q):
    return ("MITRE ATT&CK: https://attack.mitre.org/\n"
            f"Arama: {q}")


def fn_github_adv(q):
    try:
        r = _get(f"https://api.github.com/advisories?query={urllib.parse.quote(q)}&per_page=10",
                 headers={"Accept": "application/vnd.github+json", "User-Agent": "Drax"})
        if r.status_code == 200:
            d = r.json()
            if not d: return f"'{q}' icin advisory yok."
            out = [f"GitHub Advisory: {len(d)} sonuc", ""]
            for x in d[:8]:
                out.append(f"  {x.get('ghsa_id')} | {x.get('severity','-')} | {x.get('summary','')[:70]}")
            return "\n".join(out)
    except Exception as e:
        return f"Hata: {e}"
    return "Sonuc yok."


# ============================================================
#   DISPATCH
# ============================================================
DISPATCH = {
    "email": fn_email, "username": fn_username, "nickcheck": fn_nickcheck, "tgtrace": fn_tgtrace,
    "iplookup": fn_iplookup, "iplocate": fn_iplocate, "ipport": fn_ipport, "whois": fn_whois,
    "dns": fn_dns, "subdomain": fn_subdomain, "ssl": fn_ssl, "phone": fn_phone, "hlr": fn_hlr,
    "phoneinfoga": fn_phoneinfoga, "leak": fn_leak, "email_osint": fn_email_osint,
    "github": fn_github, "reddit": fn_reddit, "twitter": fn_twitter, "youtube": fn_youtube,
    "tiktok": fn_tiktok, "instagram": fn_instagram, "telegram": fn_telegram_search,
    "social_search": fn_social_search, "yt_channel": fn_yt_channel, "pastebin": fn_pastebin,
    "sherlock": fn_sherlock, "maigret": fn_maigret, "holehe": fn_holehe, "blackbird": fn_blackbird,
    "whatsmyname": fn_whatsmyname, "epieos": fn_epieos, "telegram_checker": fn_telegram_checker,
    "telerecon": fn_telerecon, "instaloader": fn_instaloader, "masto": fn_masto,
    "whatsapp_osint": fn_whatsapp_osint, "email_valid": fn_email_valid,
    "crtsh": fn_crtsh, "dnsdumpster": fn_dnsdumpster, "viewdns": fn_viewdns,
    "securitytrails": fn_securitytrails, "theharvester": fn_theharvester, "amass": fn_amass,
    "subfinder": fn_subfinder, "assetfinder": fn_assetfinder, "findomain": fn_findomain,
    "dnsrecon": fn_dnsrecon, "fierce": fn_fierce,
    "abuseipdb": fn_abuseipdb, "virustotal": fn_virustotal, "shodan": fn_shodan, "censys": fn_censys,
    "greynoise": fn_greynoise, "ipinfo": fn_ipinfo, "otx": fn_otx, "threatcrowd": fn_threatcrowd,
    "adsb": fn_adsb, "marinetraffic": fn_marinetraffic, "flightradar": fn_flightradar,
    "radiogarden": fn_radiogarden, "alienvault": fn_alienvault, "threatminer": fn_threatminer,
    "reverse_image": fn_reverse_image, "google_lens": fn_google_lens, "yandex_reverse": fn_yandex_reverse,
    "tineye": fn_tineye, "baidu_image": fn_baidu_image, "karma_decay": fn_karma_decay,
    "meta": fn_meta, "fotoforensics": fn_fotoforensics, "exiftool": fn_exiftool, "pimeyes": fn_pimeyes,
    "psbdmp": fn_psbdmp, "breachdir": fn_breachdir, "crackstation": fn_crackstation,
    "hashes_com": fn_hashes_com, "md5decrypt": fn_md5decrypt, "dehashed": fn_dehashed,
    "intelx": fn_intelx, "ahmia": fn_ahmia, "voidaccess": fn_voidaccess, "threatfox": fn_threatfox,
    "urlhaus": fn_urlhaus, "hybrid": fn_hybrid,
    "spiderfoot": fn_spiderfoot, "reconng": fn_reconng, "maryam": fn_maryam, "sn0int": fn_sn0int,
    "maltego": fn_maltego, "trufflehog": fn_trufflehog, "gitleaks": fn_gitleaks,
    "gowitness": fn_gowitness, "cyberchef": fn_cyberchef, "gephi": fn_gephi, "dorkhound": fn_dorkhound,
    "pagodo": fn_pagodo, "distill": fn_distill, "4cat": fn_4cat, "zeeschuimer": fn_zeeschuimer,
    "wayback": fn_wayback, "archive_today": fn_archive_today, "urlshort": fn_urlshort,
    "urlscan": fn_urlscan, "builtwith": fn_builtwith, "wappalyzer": fn_wappalyzer, "whatweb": fn_whatweb,
    "adminfinder": fn_adminfinder, "crawler": fn_crawler, "google_dork": fn_google_dork,
    "search_all": fn_search_all, "radiogarden_link": fn_radiogarden_link, "whoisxml": fn_whoisxml,
    "dnslytics": fn_dnslytics, "dnsgoogle": fn_dnsgoogle,
    "genpass": fn_genpass, "ua": fn_ua, "fake": fn_fake, "hash": fn_hash, "hashid": fn_hashid,
    "qr": fn_qr, "mac": fn_mac, "imei": fn_imei, "bitcoin": fn_bitcoin, "etherscan": fn_etherscan,
    "bscscan": fn_bscscan, "geo": fn_geo, "zodiac": fn_zodiac, "url_expand": fn_url_expand, "cam": fn_cam,
    "crunchbase": fn_crunchbase, "opencorporates": fn_opencorporates, "mersis": fn_mersis,
    "company": fn_company, "nvd": fn_nvd, "circl": fn_circl, "exploitdb": fn_exploitdb,
    "mitre": fn_mitre, "github_adv": fn_github_adv, "urlscan_search": fn_urlscan_search,
    "passivedns": fn_passivedns, "dnshistory": fn_dnshistory, "robots": fn_robots, "sitemap": fn_sitemap,
    "headers": fn_headers, "ssllabs": fn_ssllabs, "hstshsts": fn_hstshsts,
    "whois_history": fn_whois_history, "screenshot": fn_screenshot,
    "sql_test": fn_sql_test,
}


def dispatch(action, text):
    try:
        fn = DISPATCH.get(action)
        if fn: return fn(text)
        return "Bilinmeyen arac."
    except Exception as e:
        return f"Hata: {e}"


# ============================================================
#   MENU TANIMLARI
# ============================================================
PAGES = {
    1: ("DRAX - Sayfa 1/11", "Temel OSINT", [
        [("Email", "email"), ("Username", "username"), ("Nick Check", "nickcheck")],
        [("TG Trace", "tgtrace"), ("IP Lookup", "iplookup"), ("IP Konum", "iplocate")],
        [("Port Scan", "ipport"), ("WHOIS", "whois"), ("DNS", "dns")],
        [("Subdomain", "subdomain"), ("SSL", "ssl"), ("Telefon", "phone")],
        [("HLR", "hlr"), ("PhoneInfoga", "phoneinfoga"), ("Leak", "leak")],
        [("Email OSINT", "email_osint")],
    ]),
    2: ("DRAX - Sayfa 2/11", "Sosyal Medya", [
        [("GitHub", "github"), ("Reddit", "reddit"), ("Twitter", "twitter")],
        [("YouTube", "youtube"), ("TikTok", "tiktok"), ("Instagram", "instagram")],
        [("Telegram", "telegram"), ("Sosyal Arama", "social_search"), ("YT Kanal", "yt_channel")],
        [("Pastebin", "pastebin"), ("Sherlock", "sherlock"), ("Maigret", "maigret")],
        [("Holehe", "holehe"), ("Blackbird", "blackbird"), ("WhatsMyName", "whatsmyname")],
        [("Epieos", "epieos"), ("TG Checker", "telegram_checker"), ("Telerecon", "telerecon")],
        [("Instaloader", "instaloader"), ("Masto", "masto")],
    ]),
    3: ("DRAX - Sayfa 3/11", "Telefon & Email", [
        [("WhatsApp OSINT", "whatsapp_osint"), ("Email Valid", "email_valid")],
        [("PhoneInfoga", "phoneinfoga"), ("Telefon HLR", "hlr"), ("Telefon OSINT", "phone")],
    ]),
    4: ("DRAX - Sayfa 4/11", "Domain & DNS", [
        [("CRT.SH", "crtsh"), ("DNSDumpster", "dnsdumpster"), ("ViewDNS", "viewdns")],
        [("SecurityTrails", "securitytrails"), ("theHarvester", "theharvester")],
        [("Amass", "amass"), ("Subfinder", "subfinder"), ("Assetfinder", "assetfinder")],
        [("Findomain", "findomain"), ("DNSRecon", "dnsrecon"), ("Fierce", "fierce")],
        [("Whois XML", "whoisxml"), ("DNSLytics", "dnslytics"), ("DNS Google", "dnsgoogle")],
        [("PassiveDNS", "passivedns")],
    ]),
    5: ("DRAX - Sayfa 5/11", "IP & Ag", [
        [("AbuseIPDB", "abuseipdb"), ("VirusTotal", "virustotal"), ("Shodan", "shodan")],
        [("Censys", "censys"), ("GreyNoise", "greynoise"), ("IPinfo", "ipinfo")],
        [("OTX", "otx"), ("ThreatCrowd", "threatcrowd"), ("AlienVault", "alienvault")],
        [("ThreatMiner", "threatminer"), ("ADS-B", "adsb"), ("MarineTraffic", "marinetraffic")],
        [("FlightRadar", "flightradar"), ("RadioGarden", "radiogarden")],
    ]),
    6: ("DRAX - Sayfa 6/11", "Gorsel & Metadata", [
        [("Ters Gorsel", "reverse_image"), ("Google Lens", "google_lens"), ("Yandex", "yandex_reverse")],
        [("TinEye", "tineye"), ("Baidu", "baidu_image"), ("Karma Decay", "karma_decay")],
        [("EXIF/Meta", "meta"), ("FotoForensics", "fotoforensics"), ("ExifTool", "exiftool")],
        [("PimEyes", "pimeyes")],
    ]),
    7: ("DRAX - Sayfa 7/11", "Sizinti & Dark Web", [
        [("PSBDMP", "psbdmp"), ("BreachDir", "breachdir"), ("CrackStation", "crackstation")],
        [("Hashes.com", "hashes_com"), ("MD5Decrypt", "md5decrypt"), ("Dehashed", "dehashed")],
        [("IntelX", "intelx"), ("Ahmia", "ahmia"), ("VoidAccess", "voidaccess")],
        [("ThreatFox", "threatfox"), ("URLhaus", "urlhaus"), ("Hybrid", "hybrid")],
    ]),
    8: ("DRAX - Sayfa 8/11", "Framework", [
        [("SpiderFoot", "spiderfoot"), ("Recon-ng", "reconng"), ("Maryam", "maryam")],
        [("sn0int", "sn0int"), ("Maltego", "maltego"), ("TruffleHog", "trufflehog")],
        [("Gitleaks", "gitleaks"), ("GoWitness", "gowitness"), ("CyberChef", "cyberchef")],
        [("Gephi", "gephi"), ("Dorkhound", "dorkhound"), ("Pagodo", "pagodo")],
        [("Distill", "distill"), ("4CAT", "4cat"), ("Zeeschuimer", "zeeschuimer")],
    ]),
    9: ("DRAX - Sayfa 9/11", "Web Araclari", [
        [("Wayback", "wayback"), ("Archive.today", "archive_today"), ("URL Kisalt", "urlshort")],
        [("URLScan", "urlscan"), ("BuiltWith", "builtwith"), ("Wappalyzer", "wappalyzer")],
        [("WhatWeb", "whatweb"), ("Admin Finder", "adminfinder"), ("Crawler", "crawler")],
        [("Google Dork", "google_dork"), ("Arama Motoru", "search_all"), ("URL Coz", "url_expand")],
        [("Robots.txt", "robots"), ("Sitemap", "sitemap"), ("SSLLabs", "ssllabs")],
        [("Screenshot", "screenshot"), ("SecHeaders", "headers"), ("Whois History", "whois_history")],
    ]),
    10: ("DRAX - Sayfa 10/11", "Generator & Misc", [
        [("Sifre Uret", "genpass"), ("UA Uret", "ua"), ("Sahte Kimlik", "fake")],
        [("Hash", "hash"), ("HashID", "hashid"), ("QR", "qr")],
        [("MAC", "mac"), ("IMEI", "imei"), ("Bitcoin", "bitcoin")],
        [("Etherscan", "etherscan"), ("BscScan", "bscscan"), ("Geo", "geo")],
        [("Burc", "zodiac"), ("Cam Leak", "cam")],
    ]),
    11: ("DRAX - Sayfa 11/11", "Ekstra + SQL Test", [
        [("Crunchbase", "crunchbase"), ("OpenCorp", "opencorporates"), ("MERSIS", "mersis")],
        [("Sirket Arama", "company"), ("NVD", "nvd"), ("CIRCL", "circl")],
        [("Exploit-DB", "exploitdb"), ("MITRE", "mitre"), ("GitHub Adv", "github_adv")],
        [("VirusTotal", "virustotal"), ("AbuseIPDB", "abuseipdb"), ("Shodan", "shodan")],
        [("IPinfo", "ipinfo"), ("GreyNoise", "greynoise")],
        [("SQL Test", "sql_test")],
    ]),
}

PROMPTS = {
    "email": "Email gonder:", "username": "Username gonder:", "nickcheck": "Nick gonder:",
    "tgtrace": "Telegram username:", "iplookup": "IP gonder:", "iplocate": "IP gonder:",
    "ipport": "IP gonder:", "whois": "Domain gonder:", "dns": "Domain gonder:",
    "subdomain": "Domain gonder:", "ssl": "Domain gonder:", "phone": "Telefon (+90...):",
    "hlr": "Telefon:", "phoneinfoga": "Telefon:", "leak": "Email/Tel/Nick:", "email_osint": "Email:",
    "github": "Sorgu:", "reddit": "Sorgu:", "twitter": "Sorgu:", "youtube": "Sorgu:",
    "tiktok": "Kullanici:", "instagram": "Kullanici:", "telegram": "Kullanici:",
    "social_search": "Isim:", "yt_channel": "Kanal:", "pastebin": "Sorgu:",
    "sherlock": "Username:", "maigret": "Username:", "holehe": "Email:",
    "blackbird": "Username:", "whatsmyname": "Username:", "epieos": "Email:",
    "telegram_checker": "Telefon:", "telerecon": "Kanal:", "instaloader": "Kullanici:", "masto": "Kullanici:",
    "whatsapp_osint": "Telefon:", "email_valid": "Email:",
    "crtsh": "Domain:", "dnsdumpster": "Domain:", "viewdns": "Domain:", "securitytrails": "Domain:",
    "theharvester": "Domain:", "amass": "Domain:", "subfinder": "Domain:", "assetfinder": "Domain:",
    "findomain": "Domain:", "dnsrecon": "Domain:", "fierce": "Domain:",
    "whoisxml": "Domain:", "dnslytics": "Domain:", "dnsgoogle": "Domain:", "passivedns": "Domain:",
    "abuseipdb": "IP:", "virustotal": "URL/Hash/IP:", "shodan": "Sorgu:", "censys": "IP/Domain:",
    "greynoise": "IP:", "ipinfo": "IP:", "otx": "IP:", "threatcrowd": "Domain:",
    "alienvault": "IP:", "threatminer": "IP:", "adsb": "Enter:", "marinetraffic": "Gemi:",
    "flightradar": "Ucak:", "radiogarden": "Sehir:",
    "reverse_image": "Gorsel URL:", "google_lens": "Gorsel URL:", "yandex_reverse": "Gorsel URL:",
    "tineye": "Gorsel URL:", "baidu_image": "Gorsel URL:", "karma_decay": "Gorsel URL:",
    "meta": "Dosya URL:", "fotoforensics": "Gorsel URL:", "exiftool": "Dosya URL:", "pimeyes": "Isim:",
    "psbdmp": "Sorgu:", "breachdir": "Email:", "crackstation": "Hash:", "hashes_com": "Hash:",
    "md5decrypt": "Hash:", "dehashed": "Sorgu:", "intelx": "Sorgu:", "ahmia": "Sorgu:",
    "voidaccess": "Sorgu:", "threatfox": "IOC:", "urlhaus": "URL:", "hybrid": "Hash/URL:",
    "spiderfoot": "Hedef:", "reconng": "Hedef:", "maryam": "Hedef:", "sn0int": "Hedef:",
    "maltego": "Hedef:", "trufflehog": "Repo URL:", "gitleaks": "Repo URL:", "gowitness": "URL:",
    "cyberchef": "Veri:", "gephi": "Veri:", "dorkhound": "Sorgu:", "pagodo": "Sorgu:",
    "distill": "URL:", "4cat": "Sorgu:", "zeeschuimer": "URL:",
    "wayback": "URL:", "archive_today": "URL:", "urlshort": "URL:", "urlscan": "Sorgu:",
    "builtwith": "Domain:", "wappalyzer": "URL:", "whatweb": "URL:", "adminfinder": "URL:",
    "crawler": "URL:", "google_dork": "Sorgu:", "search_all": "Sorgu:", "url_expand": "Kisa URL:",
    "robots": "Domain:", "sitemap": "Domain:", "ssllabs": "Domain:", "screenshot": "URL:",
    "headers": "URL:", "whois_history": "Domain:",
    "genpass": "Uzunluk:", "ua": "Kac adet:", "fake": "Cinsiyet E/K:", "hash": "Metin:",
    "hashid": "Hash:", "qr": "Metin/URL:", "mac": "MAC:", "imei": "IMEI:", "bitcoin": "BTC:",
    "etherscan": "ETH:", "bscscan": "BSC:", "geo": "Lat Lon:", "zodiac": "Burc:", "cam": "Ulke kodu:",
    "crunchbase": "Sirket:", "opencorporates": "Sirket:", "mersis": "Sirket:", "company": "Sirket:",
    "nvd": "CVE:", "circl": "CVE:", "exploitdb": "Sorgu:", "mitre": "Sorgu:", "github_adv": "Sorgu:",
    "sql_test": "ID veya @email:",
}


def build_keyboard(page):
    t, d, rows = PAGES[page]
    kb = []
    for row in rows:
        kb.append([InlineKeyboardButton(label, callback_data=f"a:{act}") for label, act in row])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("<< Onceki", callback_data=f"p:{page-1}"))
    if page < 11:
        nav.append(InlineKeyboardButton("Sonraki >>", callback_data=f"p:{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("Kapat", callback_data="close")])
    return InlineKeyboardMarkup(kb)


def page_text(page):
    t, d, _ = PAGES[page]
    return f"*{t}*\n_{d}_\n\nButona tikla, sonra girdigini yaz."


# ============================================================
#   HANDLERS
# ============================================================
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        page_text(1), reply_markup=build_keyboard(1), parse_mode="Markdown")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)


async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id

    if data == "close":
        pending_input.pop(uid, None)
        await q.edit_message_text("Drax kapatildi.")
        return

    if data.startswith("p:"):
        page = int(data.split(":")[1])
        pending_input.pop(uid, None)
        await q.edit_message_text(page_text(page),
                                  reply_markup=build_keyboard(page),
                                  parse_mode="Markdown")
        return

    if data.startswith("a:"):
        action = data.split(":")[1]
        prompt = PROMPTS.get(action, "Girdi:")
        pending_input[uid] = {"action": action}
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Iptal", callback_data="cancel")]])
        await q.edit_message_text(f"*{prompt}*\n\n_Iptal icin butona bas veya /iptal yaz_",
                                  reply_markup=kb, parse_mode="Markdown")
        return

    if data == "cancel":
        pending_input.pop(uid, None)
        await q.edit_message_text("Iptal edildi.")
        return


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in pending_input:
        pending_input.pop(uid, None)
        await update.message.reply_text("Iptal edildi.")
    else:
        await update.message.reply_text("Aktif islem yok.")


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in pending_input: return
    action = pending_input.pop(uid)["action"]
    text = update.message.text.strip()
    if text.lower() in ("iptal", "cancel"):
        await update.message.reply_text("Iptal edildi.")
        return

    msg = await update.message.reply_text(f"Drax | Isleniyor: `{action}`...",
                                          parse_mode="Markdown")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, dispatch, action, text)
    if len(result) > 3800:
        result = result[:3800] + "\n..."
    safe = result.replace('`', "'")
    try:
        await msg.edit_text(f"*Drax | {action}*\n```\n{safe}\n```", parse_mode="Markdown")
    except Exception:
        await msg.edit_text(f"Drax | {action}\n\n{safe}")


# ============================================================
#   MAIN
# ============================================================
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("iptal", cmd_cancel))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    logger.info("=" * 50)
    logger.info("            D R A X   B O T   v6.0")
    logger.info("            11 Sayfa - 200+ Arac")
    logger.info(f"            SQL: {_sql_t} tablo, {_sql_r} kayit")
    logger.info("=" * 50)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
