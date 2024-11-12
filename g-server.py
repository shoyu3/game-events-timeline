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
from flask import Flask, render_template, jsonify, make_response, send_file, send_from_directory, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
from apscheduler.schedulers.background import BackgroundScheduler
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from flask_socketio import SocketIO, emit
from flask_socketio import join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash

user_connections = {}
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, 'events.sqlite3')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins='*')


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')


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
    print(f"User {userid} connected with session ID {request.sid}")

    emit('user_connected', {'username': username})


@socketio.on('disconnect')
def handle_disconnect():
    for userid, connections in user_connections.items():
        if request.sid in connections:
            connections.remove(request.sid)
            leave_room(str(userid))
            print(f"User {userid} disconnected with session ID {request.sid}")
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
        user_settings = UserSettings(userid=userid, settings=json.dumps(settings))
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
    userid = db.Column(db.Integer, db.ForeignKey('user.userid'), nullable=False)
    token = db.Column(db.String(256), nullable=False)
    time = db.Column(db.DateTime, nullable=False, default=datetime.now)


class UserSettings(db.Model):
    userid = db.Column(db.Integer, db.ForeignKey('user.userid'), primary_key=True)
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
    log = RequestLog.query.first()
    if not log:
        return True
    now = datetime.now()
    return (now - log.last_request_time) > timedelta(hours=24)


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
        return "时限内" in title or (all(keyword not in title for keyword in ["魔神任务", "礼包", "纪行", "铸境研炼", "七圣召唤"]))
    elif game == "sr":
        return "等奖励" in title and "模拟宇宙" not in title
    elif game == "zzz":
        return "活动说明" in title
    elif game == "ww":
        return title.endswith("活动") and "感恩答谢" not in title
    return False


def fetch_and_save_announcements():
    session = requests.Session()
    urls = {
        "ys": "https://hk4e-ann-api.mihoyo.com/common/hk4e_cn/announcement/api/getAnnList?game=hk4e&game_biz=hk4e_cn&lang=zh-cn&bundle_id=hk4e_cn&level=1&platform=pc&region=cn_gf01&uid=1",
        "sr": "https://hkrpg-ann-api.mihoyo.com/common/hkrpg_cn/announcement/api/getAnnList?game=hkrpg&game_biz=hkrpg_cn&lang=zh-cn&bundle_id=hkrpg_cn&level=1&platform=pc&region=prod_gf_cn&uid=1",
        "zzz": "https://announcement-api.mihoyo.com/common/nap_cn/announcement/api/getAnnList?game=nap&game_biz=nap_cn&lang=zh-cn&bundle_id=nap_cn&level=1&platform=pc&region=prod_gf_cn&uid=1",
        "ww": "https://aki-gm-resources-back.aki-game.com/gamenotice/G152/76402e5b20be2c39f095a152090afddc/notice.json",
    }

    for key, url in urls.items():
        try:
            response = session.get(url, timeout=(5, 10))
            response.raise_for_status()
            filtered_list = []
            data = response.json()

            if key == "ys":
                for item in data["data"]["list"]:
                    if item["type_label"] == "活动公告":
                        for announcement in item["list"]:
                            clean_title = remove_html_tags(announcement["title"])
                            if "时限内" in clean_title or (announcement["tag_label"] == "活动" and title_filter(key, clean_title)):
                                announcement["title"] = clean_title
                                announcement["bannerImage"] = announcement.get("banner", "")
                                filtered_list.append(announcement)
                    elif item["type_label"] == "游戏公告":
                        for announcement in item["list"]:
                            clean_title = remove_html_tags(announcement["title"])
                            if "版本更新说明" in clean_title:
                                announcement["title"] = "原神 " + str(extract_floats(clean_title)[0]) + " 版本"
                                announcement["bannerImage"] = announcement.get("banner", "")
                                filtered_list.append(announcement)

            elif key == "sr":
                for item in data["data"]["list"]:
                    if item["type_label"] == "公告":
                        for announcement in item["list"]:
                            clean_title = remove_html_tags(announcement["title"])
                            if title_filter(key, clean_title):
                                announcement["title"] = clean_title
                                announcement["bannerImage"] = announcement.get("banner", "")
                                filtered_list.append(announcement)
                            elif "版本更新说明" in clean_title:
                                announcement["title"] = "崩坏：星穹铁道 " + str(extract_floats(clean_title)[0]) + " 版本"
                                announcement["bannerImage"] = announcement.get("banner", "")
                                filtered_list.append(announcement)

                for item in data["data"]["pic_list"]:
                    for type_item in item["type_list"]:
                        for announcement in type_item["list"]:
                            clean_title = remove_html_tags(announcement["title"])
                            if title_filter(key, clean_title):
                                announcement["title"] = clean_title
                                announcement["bannerImage"] = announcement.get("img", "")
                                filtered_list.append(announcement)

            elif key == "zzz":
                for item in data["data"]["list"]:
                    if item["type_id"] == 4:
                        for announcement in item["list"]:
                            clean_title = remove_html_tags(announcement["title"])
                            if title_filter(key, clean_title):
                                announcement["title"] = clean_title
                                announcement["bannerImage"] = announcement.get("banner", "")
                                filtered_list.append(announcement)
                    elif item["type_label"] == "游戏公告":
                        for announcement in item["list"]:
                            clean_title = remove_html_tags(announcement["title"])
                            if "更新说明" in clean_title:
                                announcement["title"] = "绝区零 " + str(extract_floats(clean_title)[0]) + " 版本"
                                announcement["bannerImage"] = announcement.get("banner", "")
                                filtered_list.append(announcement)

            elif key == "ww":
                for announcement in data["game"]:
                    clean_title = remove_html_tags(announcement["tabTitle"]["zh-Hans"])
                    if "版本内容说明" in clean_title:
                        announcement["title"] = "鸣潮 " + str(extract_floats(clean_title)[0]) + " 版本"
                        announcement["bannerImage"] = announcement.get("tabBanner", {}).get("zh-Hans", "")[0]
                        announcement["start_time"] = datetime.fromtimestamp(announcement["startTimeMs"] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                        announcement["end_time"] = datetime.fromtimestamp(announcement["endTimeMs"] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                        filtered_list.append(announcement)
                for announcement in data["activity"]:
                    clean_title = remove_html_tags(announcement["tabTitle"]["zh-Hans"])
                    if title_filter(key, clean_title):
                        announcement["title"] = clean_title
                        announcement["bannerImage"] = announcement.get("tabBanner", {}).get("zh-Hans", "")[0]
                        announcement["start_time"] = datetime.fromtimestamp(announcement["startTimeMs"] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                        announcement["end_time"] = datetime.fromtimestamp(announcement["endTimeMs"] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                        filtered_list.append(announcement)

        except requests.exceptions.RequestException as e:
            print(f"Error fetching {key} announcements: {repr(e)}")

        try:
            for announcement in filtered_list:
                title = announcement["title"]
                if title:
                    existing_event = Event.query.filter_by(title=title).first()
                    if not existing_event:
                        try:
                            new_event = Event(
                                title=title,
                                game=key,
                                data=json.dumps(announcement),
                                start_time=datetime.strptime(announcement.get("start_time", ""), '%Y-%m-%d %H:%M:%S'),
                                end_time=datetime.strptime(announcement.get("end_time", ""), '%Y-%m-%d %H:%M:%S'),
                                banner_image=announcement.get("bannerImage", "")
                            )
                            db.session.add(new_event)
                            db.session.commit()
                        except Exception as e:
                            db.session.rollback()
                            print(f"Error saving event: {e}")
        except Exception as e:
            print(f"Error saving to db: {repr(e)}")


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


@app.route("/game-events/getnotice", methods=["GET"])
def get_notice():
    if is_time_to_update():
        fetch_and_save_announcements()
        update_request_log()

    now = datetime.now()
    active_events = Event.query.filter(Event.end_time > now).order_by(Event.start_time.asc(), Event.end_time.asc()).all()
    results = {}
    for event in active_events:
        if event.game not in results:
            results[event.game] = []
        if title_filter(event.game, event.title):
            results[event.game].append({
                "title": event.title,
                "start_time": event.start_time.strftime('%Y-%m-%d %H:%M:%S'),
                "end_time": event.end_time.strftime('%Y-%m-%d %H:%M:%S'),
                "bannerImage": event.banner_image,
                "uuid": event.uuid
            })

    for game, events in results.items():
        version_events = [event for event in events if "版本" in event["title"]]
        other_events = [event for event in events if "版本" not in event["title"]]
        results[game] = version_events + other_events

    response = make_response(json.dumps(results, ensure_ascii=False))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response


def limit_user_tokens(userid):
    tokens = UserLoginToken.query.filter_by(userid=userid).order_by(UserLoginToken.time.asc()).all()
    if len(tokens) > 10:
        db.session.delete(tokens[0])
        db.session.commit()


def decrypt_password(encrypted_password, private_key_pem):
    private_key = serialization.load_pem_private_key(
        private_key_pem,
        password=None,
    )
    print(encrypted_password)
    encrypted_password_bytes = base64.b64decode(encrypted_password)
    decrypted_password = private_key.decrypt(
        encrypted_password_bytes,
        padding.PKCS1v15()
    )
    return decrypted_password.decode('utf-8')


def update_existing_passwords():
    users = User.query.all()
    for user in users:
        if not user.password.startswith('scrypt:32768:8:1'):  # 检查密码是否已经加密
            user.set_password(user.password)
            db.session.commit()


def validate_geetest(validate):
    geetest_config = app.config['GEETEST_CONFIG']
    captcha_id = geetest_config.get('captchaId')
    captcha_key = geetest_config.get('captchaKey')
    lot_number = validate.get('lot_number', '')
    captcha_output = validate.get('captcha_output', '')
    pass_token = validate.get('pass_token', '')
    gen_time = validate.get('gen_time', '')

    lotnumber_bytes = lot_number.encode()
    prikey_bytes = captcha_key.encode()
    sign_token = hmac.new(prikey_bytes, lotnumber_bytes, digestmod=hashlib.sha256).hexdigest()

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
def get_public_key():
    return public_key_pem, 200


@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    encrypted_password = data.get('password').encode('utf-8')
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

        response = make_response(jsonify({"code": 0, "message": "Logged in successfully", "token": login_token.token}))
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

    response = make_response(jsonify({"code": 0, 'message': 'Logged out successfully'}))
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
        user_settings = UserSettings(userid=userid, settings=json.dumps(settings))
        db.session.add(user_settings)

    db.session.commit()
    return jsonify({"code": 0, "message": "ok"})


@app.route('/game-events/load-settings', methods=['GET'])
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
        print(f"Initialized user 'user' with random password: {random_password}")


@app.route("/")
def home():
    return render_template("home.html", nowYear=datetime.now().year)


@app.route("/game-events")
def game_events():
    geetest_config = app.config['GEETEST_CONFIG']
    captcha_id = geetest_config.get('captchaId')
    return render_template("game-events.html", nowYear=datetime.now().year, captchaId=captcha_id)


@app.route('/favicon')
def dynamic_favicon():
    size = (32, 32)
    radius = 8
    image = Image.new('RGBA', size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    rect_color = (50, 150, 255, 255)
    draw.rounded_rectangle([0, 0, size[0], size[1]], radius=radius, fill=rect_color)
    today = datetime.now().day
    day_str = str(today)

    try:
        font = ImageFont.truetype("凤凰点阵体 12px.ttf", 20)
    except IOError:
        font = ImageFont.load_default()

    text_bbox = draw.textbbox((0, 0), day_str, font=font)
    text_size = (text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1])
    text_position = ((size[0] - text_size[0]) // 2, (size[1] - text_size[1]) // 2 - 2)
    text_color = (255, 255, 255, 255)
    draw.text(text_position, day_str, font=font, fill=text_color)

    img_io = io.BytesIO()
    image.save(img_io, 'PNG')
    img_io.seek(0)

    response = make_response(send_file(img_io, mimetype='image/png'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


def load_geetest_config():
    geetest_config_path = os.path.join(base_dir, 'geetest.json')
    with open(geetest_config_path, 'r', encoding='utf-8') as f:
        geetest_config = json.load(f)
    return geetest_config


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        initialize_user()
        update_existing_passwords()
        scheduler = BackgroundScheduler()
        geetest_config = load_geetest_config()
        app.config['GEETEST_CONFIG'] = geetest_config
        scheduler.add_job(scheduled_task, 'cron', hour=9, minute=0)
        scheduler.add_job(scheduled_task, 'cron', hour=11, minute=0)
        scheduler.add_job(scheduled_task, 'cron', hour=18, minute=0)
        scheduler.start()
    socketio.run(app, host="0.0.0.0", port=8180, allow_unsafe_werkzeug=True)
