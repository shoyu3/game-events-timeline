import requests
import re
import json
import os
import io
import logging
import uuid
import secrets
import string
import base64
import hmac
import hashlib
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, jsonify, make_response, send_file, send_from_directory, request, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from flask_socketio import join_room, leave_room
from PIL import Image, ImageDraw, ImageFont
from apscheduler.schedulers.background import BackgroundScheduler
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from werkzeug.security import generate_password_hash, check_password_hash
from bs4 import BeautifulSoup

user_connections = {}
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.debug = False
app.config["JSON_AS_ASCII"] = False
app.logger.setLevel(logging.ERROR)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

base_dir = app.root_path
# base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, 'events.sqlite3')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins='*')


def cache_control(cache_header):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            response = make_response(f(*args, **kwargs))
            response.headers['Cache-Control'] = cache_header
            return response
        return wrapper
    return decorator


@app.route('/favicon.ico')
@cache_control('max-age=86400')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')


@app.route('/static/<path:path>')
@cache_control('max-age=86400')
def static_file(path):
    response = make_response(app.send_static_file(path))
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


@socketio.on('connect')
def handle_connect():
    token = request.args.get('token')
    if not token:
        return False

    login_token = UserLoginToken.query.filter_by(token=token).first()
    if not login_token:
        return False

    userid = login_token.userid
    user = User.query.filter_by(userid=userid).first()
    if not user:
        return False

    username = user.username

    if userid not in user_connections:
        user_connections[userid] = []

    user_connections[userid].append(request.sid)
    join_room(str(userid))
    # print(f"User {userid} connected with session ID {request.sid}")

    emit('user_connected', {'username': username})


@socketio.on('disconnect')
def handle_disconnect():
    for userid, connections in user_connections.items():
        if request.sid in connections:
            connections.remove(request.sid)
            leave_room(str(userid))
            # print(f"User {userid} disconnected with session ID {request.sid}")
            break


@socketio.on('settings_updated')
def handle_update_settings(data):
    token = request.args.get('token')
    if not token:
        return False

    login_token = UserLoginToken.query.filter_by(token=token).first()
    if not login_token:
        return False

    userid = login_token.userid
    settings = data.get('settings')

    user_settings = UserSettings.query.filter_by(userid=userid).first()
    if user_settings:
        user_settings.settings = json.dumps(settings)
    else:
        user_settings = UserSettings(
            userid=userid, settings=json.dumps(settings))
        db.session.add(user_settings)

    db.session.commit()
    emit('settings_updated', settings, room=str(userid), include_self=False)


def generate_rsa_keys():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    return private_pem, public_pem


private_key_pem, public_key_pem = generate_rsa_keys()


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False)
    title = db.Column(db.String(200))
    game = db.Column(db.String(50))
    data = db.Column(db.Text)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    banner_image = db.Column(db.String(16384))
    event_type = db.Column(db.String(50))

    def __init__(self, **kwargs):
        super(Event, self).__init__(**kwargs)
        self.uuid = self.generate_uuid()

    def generate_uuid(self):
        namespace = uuid.NAMESPACE_DNS
        name = f"{self.game}-{self.title}"
        return str(uuid.uuid3(namespace, name))


class RequestLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    last_request_time = db.Column(db.DateTime)


class RefreshLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    refresh_time = db.Column(db.DateTime, default=datetime.now)


class User(db.Model):
    userid = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)


class UserLoginToken(db.Model):
    tokenid = db.Column(db.Integer, primary_key=True, autoincrement=True)
    userid = db.Column(db.Integer, db.ForeignKey(
        'user.userid'), nullable=False)
    token = db.Column(db.String(256), nullable=False)
    time = db.Column(db.DateTime, nullable=False, default=datetime.now)


class UserSettings(db.Model):
    userid = db.Column(db.Integer, db.ForeignKey(
        'user.userid'), primary_key=True)
    settings = db.Column(db.Text, nullable=False)


def generate_token():
    return secrets.token_hex(16)


def remove_html_tags(text):
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).strip()


def extract_floats(text):
    float_pattern = r'-?\d+\.\d+'
    floats = re.findall(float_pattern, text)
    return [float(f) for f in floats]


def is_time_to_update():
    try:
        log = RequestLog.query.first()
        if not log:
            return True
        now = datetime.now()
        return (now - log.last_request_time) > timedelta(hours=24)
    except Exception as e:
        return True


def update_request_log():
    try:
        log = RequestLog.query.first()
        if not log:
            log = RequestLog(last_request_time=datetime.now())
            db.session.add(log)
        else:
            log.last_request_time = datetime.now()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error updating request log: {e}")


def title_filter(game, title):
    games = {'ys': '原神', 'sr': '崩坏：星穹铁道', 'zzz': '绝区零', 'ww': '鸣潮'}
    if games[game] in title and "版本" in title:
        return True
    if game == "ys":
        return "时限内" in title or (all(keyword not in title for keyword in ["魔神任务", "礼包", "纪行", "铸境研炼", "七圣召唤", "限时折扣"]))
    elif game == "sr":
        return "等奖励" in title and "模拟宇宙" not in title
    elif game == "zzz":
        return "活动说明" in title and "全新放送" not in title and "『嗯呢』从天降" not in title and "特别访客" not in title
    elif game == "ww":
        return title.endswith("活动") and "感恩答谢" not in title and "签到" not in title
    return False


def extract_zzz_character_names(html_content):
    pattern = r"活动期间，限定S级代理人.*?\[(.*?)\(.*?\)\].*?以及A级代理人"
    matches = re.findall(pattern, html_content)
    if matches:
        return matches
    else:
        return ["代理人"]


def extract_zzz_weapon_names(html_content):
    pattern = r"活动期间，限定S级音擎.*?\[(.*?)\(.*?\)\].*?以及A级音擎"
    matches = re.findall(pattern, html_content)
    if matches:
        return matches
    else:
        return ["音擎"]


def extract_clean_time(html_time_str):
    soup = BeautifulSoup(html_time_str, 'html.parser')
    clean_time_str = soup.get_text().strip()
    return clean_time_str


def extract_ys_event_start_time(html_content):
    if "版本更新后" not in html_content:
        pattern = r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}"
        match = re.search(pattern, html_content)
        if match:
            first_datetime = match.group()
            return first_datetime
    soup = BeautifulSoup(html_content, "html.parser")
    reward_time_title = soup.find(
        string="〓获取奖励时限〓") or soup.find(string="〓活动时间〓")
    if reward_time_title:
        reward_time_paragraph = reward_time_title.find_next("p")
        if reward_time_paragraph:
            time_range = reward_time_paragraph.get_text()
            if "~" in time_range:
                text = re.sub("<[^>]+>", "", time_range.split("~")[0].strip())
                return text
            return re.sub("<[^>]+>", "", time_range)
    return ""


def extract_ys_gacha_start_time(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    td_element = soup.find('td', {'rowspan': '3'})
    if td_element is None:
        td_element = soup.find('td', {'rowspan': '5'})
        if td_element is None:
            td_element = soup.find('td', {'rowspan': '9'})
            if td_element is None:
                return ""
            # raise Exception(str(html_content))
    time_texts = []
    for child in td_element.children:
        if child.name == "p":
            span = child.find("span")
            if span:
                time_texts.append(span.get_text())
            else:
                time_texts.append(child.get_text())
        elif child.name == "t":
            span = child.find("span")
            if span:
                time_texts.append(span.get_text())
            else:
                time_texts.append(child.get_text())
    time_range = ' '.join(time_texts)
    # print(time_range)
    if "~" in time_range:
        return time_range.split("~")[0].strip()
    return time_range


def extract_sr_event_start_time(html_content):
    pattern = r"<h1[^>]*>(?:活动时间|限时活动期)</h1>\s*<p[^>]*>(.*?)</p>"
    match = re.search(pattern, html_content, re.DOTALL)
    # logging.info(f'{pattern} {html_content} {match}')

    if match:
        time_info = match.group(1)
        cleaned_time_info = re.sub("&lt;.*?&gt;", "", time_info)
        if "-" in cleaned_time_info:
            return cleaned_time_info.split("-")[0].strip()
        return cleaned_time_info
    else:
        return ""


def extract_sr_gacha_start_time(html_content):
    pattern = r"时间为(.*?)，包含如下内容"
    matches = re.findall(pattern, html_content)
    time_range = re.sub("&lt;.*?&gt;", "", matches[0].strip())
    if "-" in time_range:
        return time_range.split("-")[0].strip()
    return time_range


def extract_zzz_event_start_end_time(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    activity_time_label = soup.find(
        'p', string=lambda text: text and '【活动时间】' in text)
    if activity_time_label:
        activity_time_p = activity_time_label.find_next('p')
        if activity_time_p:
            activity_time_text = activity_time_p.get_text(strip=True)
            if "~" in activity_time_text:
                return activity_time_text.split("~")[0].replace("（服务器时间）", "").strip(), activity_time_text.split("~")[1].replace("（服务器时间）", "").strip()
            return activity_time_text
    return ""


def extract_zzz_gacha_start_end_time(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    table = soup.find("table")
    if table is None:
        raise Exception(html_content)

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")

    # 查找包含时间的行（通常是第一个 <tr> 之后的 <tr>）
    time_row = rows[1] if len(rows) > 1 else None
    if not time_row:
        return "", ""

    # 查找包含时间的单元格（通常是带有 rowspan 的 <td>）
    time_cell = time_row.find("td", {"rowspan": True})
    if not time_cell:
        return "", ""

    # 提取所有时间文本（可能包含多个活动的开始和结束时间）
    time_texts = [p.get_text(strip=True) for p in time_cell.find_all("p")]

    # 如果没有足够的时间信息，返回空字符串
    if len(time_texts) < 2:
        return "", ""

    # 提取第一个活动的时间（通常是第一个 <p>）
    start_time = time_texts[0]

    # 尝试提取结束时间（可能是最后一个 <p> 或倒数第二个 <p>）
    end_time = time_texts[-1] if len(time_texts) >= 2 else ""

    # 清理时间格式（去除多余的空格和换行）
    start_time = re.sub(r"\s+", " ", start_time).strip()
    end_time = re.sub(r"\s+", " ", end_time).strip()

    return start_time, end_time


def extract_ww_event_start_end_time(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    activity_time_header = soup.find(
        'div', string=lambda text: text and '✦活动时间✦' in text)
    if activity_time_header:
        activity_time_div = activity_time_header.find_next_sibling('div')
        if activity_time_div:
            activity_time = activity_time_div.get_text(strip=True)
            if "~" in activity_time:
                return activity_time.split("~")[0].replace("（服务器时间）", "").strip(), activity_time.split("~")[1].replace("（服务器时间）", "").strip()
            return activity_time
    return ""


def update_event_fields(db_event, new_event_data):
    fields_to_update = ['data', 'start_time', 'end_time',
                        'banner_image', 'event_type']  # 'game',
    for field in fields_to_update:
        new_value = getattr(new_event_data, field)
        if field == 'data':
            db_value = json.loads(db_event.data)
            new_value_json = json.loads(new_value)
            if db_value != new_value_json:
                db_event.data = json.dumps(new_value_json)
        else:
            db_value = getattr(db_event, field)
            if db_value != new_value:
                setattr(db_event, field, new_value)
    db.session.commit()


def fetch_and_save_announcements():
    session = requests.Session()
    announcements = fetch_all_announcements(session)
    process_and_save_announcements(announcements)
    global cached_events
    cached_events = None


def fetch_all_announcements(session):
    ann_list_urls = {
        "ys": "https://hk4e-ann-api.mihoyo.com/common/hk4e_cn/announcement/api/getAnnList?game=hk4e&game_biz=hk4e_cn&lang=zh-cn&bundle_id=hk4e_cn&level=1&platform=pc&region=cn_gf01&uid=1",
        "sr": "https://hkrpg-ann-api.mihoyo.com/common/hkrpg_cn/announcement/api/getAnnList?game=hkrpg&game_biz=hkrpg_cn&lang=zh-cn&bundle_id=hkrpg_cn&level=1&platform=pc&region=prod_gf_cn&uid=1",
        "zzz": "https://announcement-api.mihoyo.com/common/nap_cn/announcement/api/getAnnList?game=nap&game_biz=nap_cn&lang=zh-cn&bundle_id=nap_cn&level=1&platform=pc&region=prod_gf_cn&uid=1",
        "ww": "https://aki-gm-resources-back.aki-game.com/gamenotice/G152/76402e5b20be2c39f095a152090afddc/notice.json",
    }
    ann_content_urls = {
        "ys": "https://hk4e-ann-api.mihoyo.com/common/hk4e_cn/announcement/api/getAnnContent?game=hk4e&game_biz=hk4e_cn&lang=zh-cn&bundle_id=hk4e_cn&level=1&platform=pc&region=cn_gf01&uid=1",
        "sr": "https://hkrpg-ann-api.mihoyo.com/common/hkrpg_cn/announcement/api/getAnnContent?game=hkrpg&game_biz=hkrpg_cn&lang=zh-cn&bundle_id=hkrpg_cn&level=1&platform=pc&region=prod_gf_cn&uid=1",
        "zzz": "https://announcement-api.mihoyo.com/common/nap_cn/announcement/api/getAnnContent?game=nap&game_biz=nap_cn&lang=zh-cn&bundle_id=nap_cn&level=1&platform=pc&region=prod_gf_cn&uid=1",
        "ww": "",
    }

    all_announcements = {}
    for game, url in ann_list_urls.items():
        try:
            announcements = fetch_game_announcements(
                session, game, url, ann_content_urls.get(game))
            if announcements:
                all_announcements[game] = announcements
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {game} announcements: {repr(e)}")

    return all_announcements


def fetch_game_announcements(session, game, list_url, content_url=None):
    version_now = "1.0"
    version_begin_time = "2024-11-01 00:00:01"
    response = session.get(list_url, timeout=(5, 30))
    response.raise_for_status()
    data = response.json()

    if game != "ww" and content_url:
        ann_content_response = session.get(content_url, timeout=(5, 30))
        ann_content_response.raise_for_status()
        ann_content_data = ann_content_response.json()
        content_map = {item['ann_id']: item for item in ann_content_data['data']['list']}
        pic_content_map = {
            item['ann_id']: item for item in ann_content_data['data']['pic_list']}
    else:
        content_map = {}
        pic_content_map = {}

    filtered_list = []

    if game == "ys":
        filtered_list = process_ys_announcements(
            data, content_map, version_now, version_begin_time)
    elif game == "sr":
        filtered_list = process_sr_announcements(
            data, content_map, pic_content_map, version_now, version_begin_time)
    elif game == "zzz":
        filtered_list = process_zzz_announcements(
            data, content_map, version_now, version_begin_time)
    elif game == "ww":
        filtered_list = process_ww_announcements(
            session, data, version_now, version_begin_time)

    return filtered_list


def process_ys_announcements(data, content_map, version_now, version_begin_time):
    filtered_list = []

    # Process version announcements
    for item in data["data"]["list"]:
        if item["type_label"] == "游戏公告":
            for announcement in item["list"]:
                clean_title = remove_html_tags(announcement["title"])
                if "版本更新说明" in clean_title:
                    version_now = str(extract_floats(clean_title)[0])
                    announcement["title"] = "原神 " + version_now + " 版本"
                    announcement["bannerImage"] = announcement.get(
                        "banner", "")
                    announcement["event_type"] = "version"
                    version_begin_time = announcement["start_time"]
                    filtered_list.append(announcement)
                    break

    # Process event and gacha announcements
    for item in data["data"]["list"]:
        if item["type_label"] == "活动公告":
            for announcement in item["list"]:
                ann_content = content_map[announcement['ann_id']]
                clean_title = remove_html_tags(announcement["title"])

                if "时限内" in clean_title or (announcement["tag_label"] == "活动" and title_filter("ys", clean_title)):
                    process_ys_event(announcement, ann_content,
                                     version_now, version_begin_time)
                    filtered_list.append(announcement)
                elif announcement["tag_label"] == "扭蛋":
                    process_ys_gacha(announcement, ann_content,
                                     version_now, version_begin_time)
                    filtered_list.append(announcement)

    return filtered_list


def process_ys_event(announcement, ann_content, version_now, version_begin_time):
    clean_title = remove_html_tags(announcement["title"])
    announcement["title"] = clean_title
    announcement["bannerImage"] = announcement.get("banner", "")
    announcement["event_type"] = "event"

    ann_content_start_time = extract_ys_event_start_time(
        ann_content['content'])
    if f"{version_now}版本" in ann_content_start_time:
        announcement["start_time"] = version_begin_time
    else:
        try:
            date_obj = datetime.strptime(extract_clean_time(
                ann_content_start_time), "%Y/%m/%d %H:%M").replace(second=0)
            formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            announcement["start_time"] = formatted_date
        except Exception:
            pass


def process_ys_gacha(announcement, ann_content, version_now, version_begin_time):
    clean_title = ann_content['title']
    if '祈愿' in clean_title:
        if '神铸赋形' in clean_title:
            pattern = r'「[^」]*·([^」]*)」'
            weapon_names = re.findall(pattern, clean_title)
            clean_title = f"【神铸赋形】武器祈愿: {', '.join(weapon_names)}"
        elif '集录' in clean_title:
            match = re.search(r'「([^」]+)」祈愿', clean_title)
            gacha_name = match.group(1)
            clean_title = f"【{gacha_name}】集录祈愿"
        else:
            match = re.search(r'·(.*)\(', clean_title)
            character_name = match.group(1)
            match = re.search(r'「([^」]+)」祈愿', clean_title)
            gacha_name = match.group(1)
            clean_title = f"【{gacha_name}】角色祈愿: {character_name}"

    announcement["title"] = clean_title
    announcement["bannerImage"] = ann_content.get("banner", "")
    announcement["event_type"] = "gacha"

    ann_content_start_time = extract_ys_gacha_start_time(
        ann_content['content'])
    if f"{version_now}版本" in ann_content_start_time:
        announcement["start_time"] = version_begin_time
    else:
        try:
            date_obj = datetime.strptime(extract_clean_time(
                ann_content_start_time), "%Y/%m/%d %H:%M").replace(second=0)
            formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            announcement["start_time"] = formatted_date
        except Exception:
            pass


def process_sr_announcements(data, content_map, pic_content_map, version_now, version_begin_time):
    filtered_list = []

    # Process version announcements
    for item in data["data"]["list"]:
        if item["type_label"] == "公告":
            for announcement in item["list"]:
                clean_title = remove_html_tags(announcement["title"])
                if "版本更新说明" in clean_title:
                    version_now = str(extract_floats(clean_title)[0])
                    announcement["title"] = "崩坏：星穹铁道 " + version_now + " 版本"
                    announcement["bannerImage"] = announcement.get(
                        "banner", "")
                    announcement["event_type"] = "version"
                    version_begin_time = announcement["start_time"]
                    filtered_list.append(announcement)

    # Process event announcements from list
    for item in data["data"]["list"]:
        if item["type_label"] == "公告":
            for announcement in item["list"]:
                ann_content = content_map[announcement['ann_id']]
                clean_title = remove_html_tags(announcement["title"])
                if title_filter("sr", clean_title):
                    process_sr_event(announcement, ann_content,
                                     version_now, version_begin_time)
                    filtered_list.append(announcement)

    # Process event and gacha announcements from pic_list
    for item in data["data"]["pic_list"]:
        for type_item in item["type_list"]:
            for announcement in type_item["list"]:
                ann_content = pic_content_map[announcement['ann_id']]
                clean_title = remove_html_tags(announcement["title"])
                if title_filter("sr", clean_title):
                    process_sr_pic_event(
                        announcement, ann_content, version_now, version_begin_time)
                    filtered_list.append(announcement)
                elif "跃迁" in clean_title:
                    process_sr_gacha(announcement, ann_content,
                                     version_now, version_begin_time)
                    filtered_list.append(announcement)

    return filtered_list


def process_sr_event(announcement, ann_content, version_now, version_begin_time):
    clean_title = remove_html_tags(announcement["title"])
    announcement["title"] = clean_title
    announcement["bannerImage"] = announcement.get("banner", "")
    announcement["event_type"] = "event"

    ann_content_start_time = extract_sr_event_start_time(
        ann_content['content'])
    if f"{version_now}版本" in ann_content_start_time:
        announcement["start_time"] = version_begin_time
    else:
        try:
            date_obj = datetime.strptime(extract_clean_time(
                ann_content_start_time), "%Y/%m/%d %H:%M:%S").replace(second=0)
            formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            announcement["start_time"] = formatted_date
        except Exception:
            pass


def process_sr_pic_event(announcement, ann_content, version_now, version_begin_time):
    clean_title = remove_html_tags(announcement["title"])
    announcement["title"] = clean_title
    announcement["bannerImage"] = announcement.get("img", "")
    announcement["event_type"] = "event"

    ann_content_start_time = extract_sr_event_start_time(
        ann_content['content'])
    if f"{version_now}版本" in ann_content_start_time:
        announcement["start_time"] = version_begin_time
    else:
        try:
            date_obj = datetime.strptime(extract_clean_time(
                ann_content_start_time), "%Y/%m/%d %H:%M:%S").replace(second=0)
            formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            announcement["start_time"] = formatted_date
        except Exception:
            pass


def process_sr_gacha(announcement, ann_content, version_now, version_begin_time):
    clean_title = remove_html_tags(announcement["title"])
    # Extract gacha names
    gacha_names = re.findall(
        r'<h1[^>]*>「([^」]+)」[^<]*活动跃迁</h1>',
        ann_content['content']
    )
    # Filter role gacha names
    role_gacha_names = []
    for name in gacha_names:
        if '•' not in name:  # Exclude light cone gacha names
            role_gacha_names.append(name)
        elif '铭心之萃' in name:  # Special case
            role_gacha_names.append(name.split('•')[0])
    role_gacha_names = list(dict.fromkeys(role_gacha_names))

    # Extract characters and light cones
    five_star_characters = re.findall(
        r'限定5星角色「([^（」]+)',
        ann_content['content']
    )
    five_star_characters = list(dict.fromkeys(five_star_characters))

    five_star_light_cones = re.findall(
        r'限定5星光锥「([^（」]+)',
        ann_content['content']
    )
    five_star_light_cones = list(dict.fromkeys(five_star_light_cones))

    clean_title = (
        f"【{', '.join(role_gacha_names)}】角色、光锥跃迁: "
        f"{', '.join(five_star_characters + five_star_light_cones)}"
    )

    announcement["title"] = clean_title
    announcement["bannerImage"] = announcement.get("img", "")
    announcement["event_type"] = "gacha"

    ann_content_start_time = extract_sr_gacha_start_time(
        ann_content['content'])
    if f"{version_now}版本" in ann_content_start_time:
        announcement["start_time"] = version_begin_time
    else:
        try:
            date_obj = datetime.strptime(extract_clean_time(
                ann_content_start_time), "%Y/%m/%d %H:%M:%S").replace(second=0)
            formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            announcement["start_time"] = formatted_date
        except Exception:
            pass


def process_zzz_announcements(data, content_map, version_now, version_begin_time):
    filtered_list = []

    # Process version announcements
    for item in data["data"]["list"]:
        if item["type_label"] == "游戏公告":
            for announcement in item["list"]:
                clean_title = remove_html_tags(announcement["title"])
                # print(clean_title)
                if "更新说明" in clean_title and "版本" in clean_title:
                    version_now = str(extract_floats(clean_title)[0])
                    announcement["title"] = "绝区零 " + version_now + " 版本"
                    announcement["bannerImage"] = announcement.get(
                        "banner", "")
                    announcement["event_type"] = "version"
                    version_begin_time = announcement["start_time"]
                    filtered_list.append(announcement)

    # Process event and gacha announcements
    for item in data["data"]["list"]:
        if item["type_id"] == 4:
            for announcement in item["list"]:
                ann_content = content_map[announcement['ann_id']]
                clean_title = remove_html_tags(announcement["title"])

                if title_filter("zzz", clean_title) and "累计登录7天" not in ann_content['content']:
                    process_zzz_event(announcement, ann_content,
                                      version_now, version_begin_time)
                    filtered_list.append(announcement)
                elif "限时频段" in clean_title:
                    process_zzz_gacha(announcement, ann_content,
                                      version_now, version_begin_time)
                    filtered_list.append(announcement)

    return filtered_list


def process_zzz_event(announcement, ann_content, version_now, version_begin_time):
    clean_title = remove_html_tags(announcement["title"])
    announcement["title"] = clean_title
    announcement["bannerImage"] = announcement.get("banner", "")
    announcement["event_type"] = "event"

    ann_content_start_time, ann_content_end_time = extract_zzz_event_start_end_time(
        ann_content['content'])
    if f"{version_now}版本" in ann_content_start_time:
        announcement["start_time"] = version_begin_time
        try:
            date_obj = datetime.strptime(extract_clean_time(
                ann_content_end_time), "%Y/%m/%d %H:%M:%S").replace(second=0)
            formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            announcement["end_time"] = formatted_date
        except Exception:
            pass
    else:
        try:
            date_obj = datetime.strptime(extract_clean_time(
                ann_content_start_time), "%Y/%m/%d %H:%M:%S").replace(second=0)
            formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            announcement["start_time"] = formatted_date
            date_obj = datetime.strptime(extract_clean_time(
                ann_content_end_time), "%Y/%m/%d %H:%M:%S").replace(second=0)
            formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            announcement["end_time"] = formatted_date
        except Exception:
            pass


def process_zzz_gacha(announcement, ann_content, version_now, version_begin_time):
    clean_title = remove_html_tags(announcement["title"])

    # 提取所有调频活动名称（如「飞鸟坠入良夜」「『查无此人』」）
    gacha_names = re.findall(r'「([^」]+)」调频活动', ann_content['content'])

    # 提取所有S级代理人和音擎名称
    s_agents = re.findall(
        r"限定S级代理人.*?\[(.*?)\(.*?\)\]", ann_content['content'])
    s_weapons = re.findall(
        r"限定S级音擎.*?\[(.*?)\(.*?\)\]", ann_content['content'])

    # 合并所有名称
    all_names = list(dict.fromkeys(s_agents + s_weapons))
    w_engine_gacha_name = ["喧哗奏鸣", "激荡谐振", "灿烂和声"]
    gacha_names = [x for x in gacha_names if x not in w_engine_gacha_name]

    # 生成新的标题格式
    if gacha_names and all_names:
        clean_title = f"【{', '.join(gacha_names)}】代理人、音擎调频: {', '.join(all_names)}"
    else:
        clean_title = clean_title  # 如果提取失败，保持原样

    announcement["title"] = clean_title
    announcement["event_type"] = "gacha"

    banner_image = announcement.get("banner", "")
    if not banner_image:
        soup = BeautifulSoup(ann_content['content'], 'html.parser')
        img_tag = soup.find('img')
        if img_tag and 'src' in img_tag.attrs:
            banner_image = img_tag['src']
    announcement["bannerImage"] = banner_image

    ann_content_start_time, ann_content_end_time = extract_zzz_gacha_start_end_time(
        ann_content['content'])
    if f"{version_now}版本" in ann_content_start_time:
        announcement["start_time"] = version_begin_time
        try:
            date_obj = datetime.strptime(extract_clean_time(
                ann_content_end_time), "%Y/%m/%d %H:%M:%S").replace(second=0)
            formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            announcement["end_time"] = formatted_date
        except Exception:
            pass
    else:
        try:
            date_obj = datetime.strptime(extract_clean_time(
                ann_content_start_time), "%Y/%m/%d %H:%M:%S").replace(second=0)
            formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            announcement["start_time"] = formatted_date
            date_obj = datetime.strptime(extract_clean_time(
                ann_content_end_time), "%Y/%m/%d %H:%M:%S").replace(second=0)
            formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            announcement["end_time"] = formatted_date
        except Exception:
            pass


def process_ww_announcements(session, data, version_now, version_begin_time):
    filtered_list = []

    # Process version announcements
    for announcement in data["game"]:
        clean_title = remove_html_tags(announcement["tabTitle"]["zh-Hans"])
        if "版本内容说明" in clean_title:
            version_now = str(extract_floats(clean_title)[0])
            announcement["title"] = "鸣潮 " + version_now + " 版本"
            announcement["bannerImage"] = announcement.get(
                "tabBanner", {}).get("zh-Hans", "")[0]
            announcement["start_time"] = datetime.fromtimestamp(
                announcement["startTimeMs"] / 1000).strftime('%Y-%m-%d %H:%M:%S')
            announcement["end_time"] = datetime.fromtimestamp(
                announcement["endTimeMs"] / 1000).strftime('%Y-%m-%d %H:%M:%S')
            announcement["event_type"] = "version"
            version_begin_time = announcement["start_time"]
            filtered_list.append(announcement)

    # Process event and gacha announcements
    for announcement in data["activity"]:
        clean_title = remove_html_tags(announcement["tabTitle"]["zh-Hans"])
        ann_content_response = session.get(
            announcement['contentPrefix'][0] + "zh-Hans.json", timeout=(5, 20))
        ann_content_response.raise_for_status()
        ann_content_data = ann_content_response.json()

        if title_filter("ww", clean_title):
            process_ww_event(announcement, ann_content_data,
                             version_now, version_begin_time)
            filtered_list.append(announcement)
        elif "唤取" in clean_title:
            process_ww_gacha(announcement, ann_content_data,
                             version_now, version_begin_time)
            filtered_list.append(announcement)

    return filtered_list


def process_ww_event(announcement, ann_content_data, version_now, version_begin_time):
    clean_title = remove_html_tags(announcement["tabTitle"]["zh-Hans"])
    announcement["title"] = clean_title
    announcement["bannerImage"] = announcement.get(
        "tabBanner", {}).get("zh-Hans", "")[0]
    announcement["start_time"] = datetime.fromtimestamp(
        announcement["startTimeMs"] / 1000).strftime('%Y-%m-%d %H:%M:%S')
    announcement["end_time"] = datetime.fromtimestamp(
        announcement["endTimeMs"] / 1000).strftime('%Y-%m-%d %H:%M:%S')
    announcement["event_type"] = "event"

    ann_content_start_time, ann_content_end_time = extract_ww_event_start_end_time(
        ann_content_data['textContent'])
    if f"{version_now}版本" in ann_content_start_time:
        announcement["start_time"] = version_begin_time
    else:
        try:
            date_obj = datetime.strptime(extract_clean_time(
                ann_content_start_time), "%Y年%m月%d日%H:%M").replace(second=0)
            formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            announcement["start_time"] = formatted_date
            date_obj = datetime.strptime(extract_clean_time(
                ann_content_end_time), "%Y年%m月%d日%H:%M").replace(second=0)
            formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            announcement["end_time"] = formatted_date
        except Exception:
            pass


def process_ww_gacha(announcement, ann_content_data, version_now, version_begin_time):
    clean_title = remove_html_tags(announcement["tabTitle"]["zh-Hans"])
    gacha_type = "共鸣者"
    if "浮声" in clean_title:
        gacha_type = "武器"

    announcement["title"] = (
        f"【{ann_content_data['textTitle'].split('[')[1].split(']')[0]}】"
        f"{gacha_type}唤取: {ann_content_data['textTitle'].split('「')[1].split('」')[0]}"
    )
    announcement["bannerImage"] = announcement.get(
        "tabBanner", {}).get("zh-Hans", "")[0]
    announcement["start_time"] = datetime.fromtimestamp(
        announcement["startTimeMs"] / 1000).strftime('%Y-%m-%d %H:%M:%S')
    announcement["end_time"] = datetime.fromtimestamp(
        announcement["endTimeMs"] / 1000).strftime('%Y-%m-%d %H:%M:%S')
    announcement["event_type"] = "gacha"

    ann_content_start_time, ann_content_end_time = extract_ww_event_start_end_time(
        ann_content_data['textContent'])
    if f"{version_now}版本" in ann_content_start_time:
        announcement["start_time"] = version_begin_time
    else:
        try:
            date_obj = datetime.strptime(extract_clean_time(
                ann_content_start_time), "%Y年%m月%d日%H:%M").replace(second=0)
            formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            announcement["start_time"] = formatted_date
            date_obj = datetime.strptime(extract_clean_time(
                ann_content_end_time), "%Y年%m月%d日%H:%M").replace(second=0)
            formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
            announcement["end_time"] = formatted_date
        except Exception:
            pass


def process_and_save_announcements(announcements):
    for game, game_announcements in announcements.items():
        for announcement in game_announcements:
            save_or_update_announcement(game, announcement)


def save_or_update_announcement(game, announcement):
    title = announcement["title"]
    existing_event = Event.query.filter_by(title=title).first()

    if existing_event:
        new_event_data = Event(
            title=title,
            game=game,
            data=json.dumps(announcement),
            start_time=datetime.strptime(announcement.get(
                "start_time", ""), '%Y-%m-%d %H:%M:%S'),
            end_time=datetime.strptime(announcement.get(
                "end_time", ""), '%Y-%m-%d %H:%M:%S'),
            banner_image=announcement.get("bannerImage", ""),
            event_type=announcement.get("event_type", ""),
        )
        update_event_fields(existing_event, new_event_data)
    else:
        try:
            new_event = Event(
                title=title,
                game=game,
                data=json.dumps(announcement),
                start_time=datetime.strptime(announcement.get(
                    "start_time", ""), '%Y-%m-%d %H:%M:%S'),
                end_time=datetime.strptime(announcement.get(
                    "end_time", ""), '%Y-%m-%d %H:%M:%S'),
                banner_image=announcement.get("bannerImage", ""),
                event_type=announcement.get("event_type", ""),
            )
            db.session.add(new_event)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error saving event: {e}")


def scheduled_task():
    with app.app_context():
        fetch_and_save_announcements()
        update_request_log()
        log_refresh_time()


def log_refresh_time():
    try:
        new_log = RefreshLog()
        db.session.add(new_log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error logging refresh time: {e}")


cached_events = None


@app.route("/game-events/getnotice", methods=["GET"])
@cache_control('no-cache')
def get_notice():
    global cached_events

    if is_time_to_update():
        fetch_and_save_announcements()
        update_request_log()

    now = datetime.now()

    # 如果缓存为空，或者需要更新缓存
    if cached_events is None:
        active_events = Event.query.filter(Event.end_time > now).order_by(
            Event.start_time.asc(), Event.end_time.asc()).all()
        results = {}
        for event in active_events:
            if event.game not in results:
                results[event.game] = []
            if event.event_type == "gacha" or title_filter(event.game, event.title):
                results[event.game].append({
                    "title": event.title,
                    "start_time": event.start_time.strftime('%Y-%m-%d %H:%M:%S'),
                    "end_time": event.end_time.strftime('%Y-%m-%d %H:%M:%S'),
                    "bannerImage": event.banner_image,
                    "uuid": event.uuid,
                    "event_type": event.event_type,
                })

        for game, events in results.items():
            version_events = [
                event for event in events if "版本" in event["title"]]
            other_events = [
                event for event in events if "版本" not in event["title"]]
            results[game] = version_events + other_events

        for game, events in results.items():
            other_events = [
                event for event in events if event["event_type"] != "gacha"]
            gacha_events = [
                event for event in events if event["event_type"] == "gacha"]
            results[game] = other_events + gacha_events

        if "ww" in results:
            ww_events = results["ww"]
            # 将包含“武器”的事件单独提取出来
            weapon_events = [
                event for event in ww_events if "武器" in event["title"]]
            non_weapon_events = [
                event for event in ww_events if "武器" not in event["title"]]
            # 将非武器事件排在前面，武器事件排在最后
            results["ww"] = non_weapon_events + weapon_events

        cached_events = results
    # else:
        # logging.info("命中缓存")

    response = make_response(json.dumps(cached_events, ensure_ascii=False))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response


def limit_user_tokens(userid):
    tokens = UserLoginToken.query.filter_by(
        userid=userid).order_by(UserLoginToken.time.asc()).all()
    if len(tokens) > 10:
        db.session.delete(tokens[0])
        db.session.commit()


def decrypt_password(encrypted_password, private_key_pem):
    private_key = serialization.load_pem_private_key(
        private_key_pem,
        password=None,
    )
    # print(encrypted_password)
    encrypted_password_bytes = base64.b64decode(encrypted_password)
    decrypted_password = private_key.decrypt(
        encrypted_password_bytes,
        padding.PKCS1v15()
    )
    return decrypted_password.decode('utf-8')


def update_existing_passwords():
    users = User.query.all()
    for user in users:
        if not user.password.startswith('scrypt:32768:8:1'):
            user.set_password(user.password)
            db.session.commit()


def validate_geetest(validate):
    global geetest_config
    if not geetest_config:  # 如果配置不存在或无效，直接返回 True（跳过验证）
        return True

    captcha_id = geetest_config.get('captchaId')
    captcha_key = geetest_config.get('captchaKey')
    if not captcha_id or not captcha_key:  # 双重检查
        return True

    lot_number = validate.get('lot_number', '')
    captcha_output = validate.get('captcha_output', '')
    pass_token = validate.get('pass_token', '')
    gen_time = validate.get('gen_time', '')

    lotnumber_bytes = lot_number.encode()
    prikey_bytes = captcha_key.encode()
    sign_token = hmac.new(prikey_bytes, lotnumber_bytes,
                          digestmod=hashlib.sha256).hexdigest()

    query = {
        "lot_number": lot_number,
        "captcha_output": captcha_output,
        "pass_token": pass_token,
        "gen_time": gen_time,
        "sign_token": sign_token,
    }
    url = f"http://gcaptcha4.geetest.com/validate?captcha_id={captcha_id}"

    try:
        res = requests.post(url, data=query)
        assert res.status_code == 200
        gt_msg = res.json()
    except Exception as e:
        gt_msg = {'result': 'fail', 'reason': 'request geetest api fail'}

    return gt_msg['result'] == 'success'


@app.route('/get-public-key', methods=['GET'])
@cache_control('no-cache')
def get_public_key():
    return public_key_pem, 200


@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    encrypted_password = data.get('password').encode('utf-8')

    # 如果 Geetest 配置无效，跳过验证
    if geetest_config is None:
        print("Warning: Geetest is disabled. Skipping captcha validation.")
    else:
        validate = data.get('validate')
        if not validate_geetest(validate):
            return "Invalid captcha", 401

    password = decrypt_password(encrypted_password, private_key_pem)

    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        token = generate_token()
        login_token = UserLoginToken(userid=user.userid, token=token)
        db.session.add(login_token)
        limit_user_tokens(user.userid)
        db.session.commit()

        response = make_response(jsonify(
            {"code": 0, "message": "Logged in successfully", "token": login_token.token}))
        response.set_cookie('token', token, expires=None)
        return response
    else:
        return "Invalid credentials", 401


@app.route('/logout', methods=['POST'])
def logout():
    token = request.headers.get('Authorization').split(' ')[1]
    if not token:
        return jsonify({'message': 'Unauthorized'}), 401

    login_token = UserLoginToken.query.filter_by(token=token).first()
    if not login_token:
        return jsonify({'message': 'Unauthorized'}), 401

    db.session.delete(login_token)
    db.session.commit()

    response = make_response(
        jsonify({"code": 0, 'message': 'Logged out successfully'}))
    response.set_cookie('token', '', expires=0)
    return response


@app.route('/game-events/save-settings', methods=['POST'])
def save_user_settings():
    token = request.cookies.get('token')
    if not token:
        return "Unauthorized", 401

    login_token = UserLoginToken.query.filter_by(token=token).first()
    if not login_token:
        return "Unauthorized", 401

    userid = login_token.userid
    settings = request.json

    user_settings = UserSettings.query.filter_by(userid=userid).first()
    if user_settings:
        user_settings.settings = json.dumps(settings)
    else:
        user_settings = UserSettings(
            userid=userid, settings=json.dumps(settings))
        db.session.add(user_settings)

    db.session.commit()
    return jsonify({"code": 0, "message": "ok"})


@app.route('/game-events/load-settings', methods=['GET'])
@cache_control('no-cache')
def load_user_settings():
    token = request.cookies.get('token')
    if not token:
        return "Unauthorized", 401

    login_token = UserLoginToken.query.filter_by(token=token).first()
    if not login_token:
        return "Unauthorized", 401

    userid = login_token.userid
    user_settings = UserSettings.query.filter_by(userid=userid).first()

    if user_settings:
        return jsonify(json.loads(user_settings.settings))
    else:
        return jsonify({})


def generate_random_password(length=8):
    characters = string.ascii_letters + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))


def initialize_user():
    user = User.query.filter_by(username='user').first()
    if not user:
        random_password = generate_random_password()
        user = User(userid=10, username='user')
        user.set_password(random_password)
        db.session.add(user)
        db.session.commit()
        print(
            f"Initialized user 'user' with random password: {random_password}")


@app.route("/")
@cache_control('max-age=86400')
def home():
    return render_template("home.html", nowYear=datetime.now().year)


@app.route("/game-events/")
@cache_control('max-age=86400')
def redirect_to_events():
    return redirect('/game-events', code=301, Response=None)


@app.route("/game-events")
@cache_control('max-age=86400')
def game_events():
    global geetest_config
    # geetest_config = app.config['GEETEST_CONFIG']
    captcha_id = geetest_config.get('captchaId')
    return render_template("game-events.html", nowYear=datetime.now().year, captchaId=captcha_id)


@app.route('/favicon')
@cache_control('no-cache')
def dynamic_favicon():
    size = (32, 32)
    radius = 8
    image = Image.new('RGBA', size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    rect_color = (50, 150, 255, 255)
    draw.rounded_rectangle([0, 0, size[0], size[1]],
                           radius=radius, fill=rect_color)
    today = datetime.now().day
    day_str = str(today)

    try:
        font = ImageFont.truetype("凤凰点阵体 12px.ttf", 20)
    except IOError:
        font = ImageFont.load_default()

    text_bbox = draw.textbbox((0, 0), day_str, font=font)
    text_size = (text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1])
    text_position = ((size[0] - text_size[0]) // 2,
                     (size[1] - text_size[1]) // 2 - 2)
    text_color = (255, 255, 255, 255)
    draw.text(text_position, day_str, font=font, fill=text_color)

    img_io = io.BytesIO()
    image.save(img_io, 'PNG')
    img_io.seek(0)

    response = make_response(send_file(img_io, mimetype='image/png'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@app.errorhandler(404)
@cache_control('max-age=86400')
def show_404_page(e):
    return render_template('404.html', nowYear=datetime.now().year), 404


def load_geetest_config():
    geetest_config_path = os.path.join(base_dir, 'geetest.json')
    if not os.path.exists(geetest_config_path):
        return None

    try:
        with open(geetest_config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # 检查必要字段是否存在且非空
            if not config.get('captchaId') or not config.get('captchaKey'):
                print(
                    "Warning: geetest.json is missing required fields (captchaId or captchaKey). Captcha will be disabled.")
                return None
            return config
    except json.JSONDecodeError:
        print("Warning: geetest.json is invalid. Captcha will be disabled.")
        return None


geetest_config = load_geetest_config()
app.config['GEETEST_CONFIG'] = geetest_config

scheduler = BackgroundScheduler()
scheduler.add_job(scheduled_task, 'cron', hour=9, minute=0)
scheduler.add_job(scheduled_task, 'cron', hour=12, minute=30)
scheduler.add_job(scheduled_task, 'cron', hour=18, minute=0)
scheduler.add_job(scheduled_task, 'cron', hour=22, minute=0)
scheduler.start()


if __name__ == "__main__":
    geetest_config = load_geetest_config()
    with app.app_context():
        db.create_all()
        initialize_user()
        update_existing_passwords()
    socketio.run(app, host="0.0.0.0", port=8180, allow_unsafe_werkzeug=True)
