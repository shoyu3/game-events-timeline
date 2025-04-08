"use strict";

window.remainingTimeInterval = null;
window.totalDays = 0;
window.pxPerDay = 36;
window.initialEvents = [];
window.walkthroughBlackWords = [
    "版本",
    "移涌",//ys
    "位面分裂",//sr
    "异器盈界",
    "花藏繁生",
    "数据悬赏",//zzz
    "先遣赏金",
    "回音盈域",//ww
    "声弦涤荡",
    "区域系列活动",
];

document.addEventListener('DOMContentLoaded', () => {
    const token = localStorage.getItem('token');
    if (token) {
        window.socket = connectWebSocket(token);
        loadEvents(socket);
        addLogoutButton();
    } else {
        loadEvents();
        addLoginButton();
    }
    const sortSelect = document.querySelector("#sort-select");
    sortSelect.addEventListener('change', function () {
        eventsSettings.sortOrder = sortSelect.value;
        saveEventsSettings();
        sortEvents();
    });
    const toggleBtn = document.querySelector('.toggle-btn');
    const loginContainer = document.querySelector('.login-container');
    const legendContainer = document.querySelector('.legend-inner');
    toggleBtn.addEventListener('click', () => {
        loginContainer.classList.toggle('collapsed');
        legendContainer.classList.toggle('collapsed');
        toggleBtn.textContent = legendContainer.classList.contains('collapsed') ? '▲' : '▼';
        toggleBtn.style.position = legendContainer.classList.contains('collapsed') ? "static" : "absolute";
    });
    const usernameinput = document.querySelector("input[name=username]");
    const passwordinput = document.querySelector("input[name=password]");
    usernameinput.addEventListener('input', function () {
        this.classList.toggle('red', this.value.trim() === '' || this.value.length > 16);
    });
    passwordinput.addEventListener('input', function () {
        this.classList.toggle('red', this.value.trim() === '' || this.value.length > 32);
    });
    const logbtn = document.querySelector(".login-btn");
    logbtn.addEventListener("click", function () {
        let err = false;
        const username = usernameinput.value;
        const password = passwordinput.value;
        if (username.trim() === '' || username.length > 16) {
            usernameinput.classList.add('red');
            err = true;
        }
        if (password.trim() === '' || password.length > 32) {
            passwordinput.classList.add('red');
            err = true;
        }
        if (!err) {
            usernameinput.classList.remove('red');
            passwordinput.classList.remove('red');
            login(username, password);
        }
    });

    const timelineContainer = document.querySelector('.timeline-container');
    let isDragging = false;
    let startX, startY, scrollLeft, scrollTop;

    // 鼠标按下时记录初始位置
    timelineContainer.addEventListener('mousedown', (e) => {
        isDragging = true;
        startX = e.pageX - timelineContainer.offsetLeft;
        startY = e.pageY - timelineContainer.offsetTop;
        scrollLeft = timelineContainer.scrollLeft;
        scrollTop = timelineContainer.scrollTop;
        timelineContainer.style.cursor = 'grabbing'; // 拖动时显示抓取光标
        e.preventDefault(); // 防止默认行为（如文本选中）
    });

    // 鼠标移动时计算偏移量并滚动
    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        const x = e.pageX - timelineContainer.offsetLeft;
        const y = e.pageY - timelineContainer.offsetTop;
        const walkX = (x - startX) * 2; // 横向拖动速度
        const walkY = (y - startY) * 2; // 纵向拖动速度
        timelineContainer.scrollLeft = scrollLeft - walkX;
        timelineContainer.scrollTop = scrollTop - walkY;
    });

    // 鼠标释放时停止拖动
    document.addEventListener('mouseup', () => {
        isDragging = false;
        timelineContainer.style.cursor = 'grab';
    });

    // 鼠标移出容器时停止拖动
    timelineContainer.addEventListener('mouseleave', () => {
        isDragging = false;
        timelineContainer.style.cursor = 'grab';
    });
});

let eventsSettings = {
    hide_setting: {
        ys: false,
        sr: false,
        zzz: false,
        ww: false,
    },
    events: {},
    sortOrder: 'default'
};

function loadEvents(socket) {
    fetch('game-events/getnotice')
        .then(response => response.json())
        .then(data => {
            const events = [];
            ['ys', 'sr', 'zzz', 'ww'].forEach(type => {
                if (Array.isArray(data[type])) {
                    data[type].forEach(event => {
                        let name = '';
                        // console.log(type, event.event_type);
                        if (type === 'ww' && (event.title.includes("区域系列"))) {
                            name = event.title;
                        } else if (type === 'zzz' && event.event_type === 'gacha') {
                            name = event.title;
                        } else {
                            name = extractTitle(event.title);
                        }
                        // console.log(name);
                        const newEvent = {
                            start: new Date(event.start_time),
                            end: new Date(event.end_time),
                            name: name,
                            title: event.title,
                            color: getColor(type),
                            bannerImage: event.bannerImage,
                            uuid: event.uuid,
                            game: type,
                            type: event.event_type,
                        };
                        if (newEvent.bannerImage === "") {
                            if (newEvent.game === "sr") {
                                newEvent.bannerImage = "/static/images/sr.png";
                            }
                        }
                        events.push(newEvent);
                    });
                }
            });
            if (events.length > 0) {
                updateCurrentTimeMarker();
                createTimeline(events);
                setInterval(updateCurrentTimeMarker, 100);
                createLegend();
                // 确保 eventsSettings 正确初始化
                const savedSettings = localStorage.getItem('events_setting');
                if (savedSettings) {
                    eventsSettings = JSON.parse(savedSettings);
                } else {
                    // 如果 localStorage 中没有数据，初始化 eventsSettings
                    eventsSettings = {
                        hide_setting: {
                            ys: false,
                            sr: false,
                            zzz: false,
                            ww: false,
                        },
                        events: {},
                        sortOrder: 'default'
                    };
                }
                loadHiddenStatus();
                loadCompletionStatus();
                const sortSelect = document.querySelector("#sort-select");
                sortSelect.value = eventsSettings.sortOrder;
                sortEvents();
            } else {
                const legendContainer = document.querySelector('.legend-list');
                legendContainer.innerHTML = "当前无事件";
            }
        })
        .catch(error => console.error('Error loading events:', error));
}

async function login(username, password) {
    window.userinfo = { username, password };
    if (window.captchaObj && typeof captchaObj.showCaptcha === 'function') {
        captchaObj.showCaptcha();
    } else {
        console.warn("Geetest not available, proceeding without captcha.");
        login2({});
    }
}

async function fetchPublicKey() {
    try {
        const response = await fetch('/get-public-key');
        if (!response.ok) {
            throw new Error('获取公钥失败');
        }
        return await response.text();
    } catch (error) {
        console.error('获取公钥错误:', error);
        throw error; // 重新抛出以便外部捕获
    }
}

async function login2(validate) {
    const logbtn = document.querySelector(".login-btn");
    const usernameInput = document.querySelector("input[name=username]");
    const passwordInput = document.querySelector("input[name=password]");
    try {
        logbtn.disabled = true;
        logbtn.innerHTML = "登录中...";
        const loginData = {
            username: usernameInput.value.trim(),
            password: await encryptPassword(passwordInput.value, await fetchPublicKey())
        };
        if (window.captchaObj && typeof captchaObj.getValidate === 'function') {
            loginData.validate = validate;
        }
        const response = await fetch('/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(loginData)
        });
        if (response.ok) {
            const data = await response.json();
            localStorage.setItem('token', data.token);
            const loginForm = document.querySelector(".login-form");
            loginForm.classList.add("hide");
            addLogoutButton();
            window.socket = connectWebSocket(data.token);
        } else {
            const error = await response.text();
            throw new Error(error || '登录失败');
        }
    } catch (error) {
        console.error("Login error:", error);
        logbtn.classList.add("red");
        logbtn.innerHTML = "登录失败";
        setTimeout(() => {
            logbtn.classList.remove("red");
            logbtn.innerHTML = "确认登录";
            logbtn.disabled = false;
        }, 2000);
    } finally {
        if (window.captchaObj && typeof captchaObj.reset === 'function') {
            captchaObj.reset();
        }
    }
}

async function logout() {
    const token = localStorage.getItem('token');
    if (!token) {
        alert('Not logged in');
        return;
    }
    const response = await fetch('/logout', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`,
        },
    });
    if (response.ok) {
        localStorage.removeItem('token');
        socket.disconnect();
        addLoginButton();
    } else {
        localStorage.removeItem('token');
        socket.disconnect();
        const logoutButton = document.querySelector(".logout-btn");
        logoutButton.classList.add("red");
        logoutButton.innerHTML = "登出失败，请等待...";
        setTimeout(() => {
            addLoginButton();
        }, 1500);
    }
}

async function encryptPassword(password, publicKey) {
    const encryptor = new JSEncrypt();
    encryptor.setPublicKey(publicKey);
    return encryptor.encrypt(password);
}

function connectWebSocket(token) {
    window.socket = io('/', {
        query: { token }
    });
    socket.on('connect', () => {
        console.log('Connected to server');
        fetchLatestSettings(socket);
    });
    socket.on('user_connected', (data) => {
        const username = data.username;
        const userContainer = document.querySelector(".user-container");
        userContainer.innerHTML = `已登录: ${username}`;
    });
    socket.on('settings_updated', (data) => {
        eventsSettings = data;
        localStorage.setItem('events_setting', JSON.stringify(data));
        loadHiddenStatus();
        loadCompletionStatus();
        const sortSelect = document.querySelector("#sort-select");
        sortSelect.value = eventsSettings.sortOrder;
        sortEvents();
    });
    socket.on('disconnect', () => {
        console.log('Disconnected from server');
    });
    return socket;
}

function fetchLatestSettings(socket) {
    fetch('/game-events/load-settings', {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
    })
        .then(response => response.json())
        .then(data => {
            if (data && typeof data === 'object') {
                // 确保 data 包含 hide_setting 和 events
                if (!data.hide_setting) {
                    data.hide_setting = {
                        ys: false,
                        sr: false,
                        zzz: false,
                        ww: false,
                    };
                }
                if (!data.events) {
                    data.events = {};
                }
                if (!data.sortOrder) {
                    data.sortOrder = 'default';
                }
                eventsSettings = data;
                localStorage.setItem('events_setting', JSON.stringify(data));
                loadCompletionStatus();
            } else {
                // 如果数据为空，初始化 eventsSettings
                eventsSettings = {
                    hide_setting: {
                        ys: false,
                        sr: false,
                        zzz: false,
                        ww: false,
                    },
                    events: {},
                    sortOrder: 'default'
                };
                localStorage.setItem('events_setting', JSON.stringify(eventsSettings));
            }
        })
        .catch(error => console.error('Error fetching latest settings:', error));
}

function updateSettings(settings, socket) {
    socket.emit('settings_updated', { settings });
}

function createTimeline(events) {
    const timeline = document.querySelector('.timeline');
    const timeline_container = document.querySelector('.timeline-container');
    const dateAxis = document.querySelector('.date-axis');
    const earliestStart = new Date(Math.min(...events.map(event => event.start.getTime())));
    const latestEnd = new Date(Math.max(...events.map(event => event.end.getTime())));
    const timelineStart = new Date(earliestStart);
    timelineStart.setDate(timelineStart.getDate() - 5);
    timelineStart.setHours(0, 0, 0, 0);
    const timelineEnd = new Date(latestEnd);
    timelineEnd.setDate(timelineEnd.getDate() + 5);
    timelineEnd.setHours(0, 0, 0, 0);
    const totalTimeInMs = timelineEnd - timelineStart;
    window.totalDays = Math.ceil((timelineEnd - timelineStart) / (1000 * 60 * 60 * 24));
    for (let i = 0; i <= totalDays; i++) {
        const currentDate = new Date(timelineStart);
        currentDate.setDate(currentDate.getDate() + i);
        const label = document.createElement('div');
        label.classList.add('date-label');
        label.style.left = i * pxPerDay + "px";
        if (isToday(currentDate)) {
            label.classList.add('today');
        }
        label.dataset.date = formatLocalDate(currentDate);
        const line = document.createElement('div');
        line.style.marginLeft = i * pxPerDay - 10 + "px";
        line.classList.add('date-label-line');
        if (currentDate.Format("d") === "1" || isSameDate(currentDate, timelineStart)) {
            label.innerHTML = `<div class="month-day first-day">${currentDate.Format("M月")}</div><div class="week-day" style="width:35px">${formatWeekDay(currentDate)}</idv>`;
            if (isSameDate(currentDate, timelineStart)) {
                label.style.width = (getDaysInMonth2(currentDate) - timelineStart.Format("d") + 1) * pxPerDay - pxPerDay / 1.2 + "px";
                label.style.paddingRight = pxPerDay / 1.2 + "px";
            } else if (currentDate.Format("M") === timelineEnd.Format("M")) {
                label.style.width = (timelineEnd.Format("d")) * pxPerDay + pxPerDay / 2 - pxPerDay / 1.2 + "px";
                label.style.paddingRight = pxPerDay / 1.2 + "px";
            } else {
                label.style.width = getDaysInMonth2(currentDate) * pxPerDay - pxPerDay / 1.2 + "px";
                label.style.paddingRight = pxPerDay / 1.2 + "px";
            }
            label.style.marginLeft = "-8px";
            line.style.marginLeft = i * pxPerDay - 11 + "px";
            if (currentDate.Format("d") === "1") {
                line.style.width = "3px";
                line.style.backgroundColor = "#ccc";
            }
        } else {
            line.style.marginLeft = i * pxPerDay - 10 + "px";
            label.innerHTML = `<div class="month-day today-date">${currentDate.Format("d")}</div><div class="week-day">${formatWeekDay(currentDate)}</idv>`;
        }
        dateAxis.appendChild(label);
        dateAxis.appendChild(line);
    }
    const line = document.createElement('div');
    line.style.marginLeft = (totalDays + 1) * pxPerDay - 10 + "px";
    line.classList.add('date-label-line');
    dateAxis.appendChild(line);

    events.forEach((event, index) => {
        const eventElement = document.createElement('div');
        eventElement.classList.add('event');
        eventElement.dataset.start = event.start.getTime();
        eventElement.dataset.end = event.end.getTime();
        eventElement.dataset.bannerImage = event.bannerImage;
        eventElement.dataset.uuid = event.uuid;
        eventElement.dataset.game = event.game;
        eventElement.dataset.eventType = event.type;
        eventElement.dataset.title = event.title;
        eventElement.style.backgroundColor = event.color;
        if (['ys', 'sr', 'zzz'].includes(event.game) && event.type === "gacha") {
            const startDate = event.start;
            const dayOfWeek = startDate.getDay();
            if ([1].includes(dayOfWeek)) {
                const adjustedDate = new Date(startDate);
                const daysToWednesday = (3 - dayOfWeek + 7) % 7;
                adjustedDate.setDate(startDate.getDate() + daysToWednesday);
                adjustedDate.setHours(7, 0, 0, 0);
                event.start = adjustedDate;
            }
        } else if (event.game === 'ww' && event.type === 'gacha') {
            const startDate = event.start;
            const dayOfWeek = startDate.getDay();
            if (dayOfWeek !== 4) {
                const adjustedDate = new Date(startDate);
                const daysToThursday = (4 - dayOfWeek + 7) % 7;
                adjustedDate.setDate(startDate.getDate() + daysToThursday);
                adjustedDate.setHours(8, 0, 0, 0);
                event.start = adjustedDate;
            }
        }
        const eventStartOffset = (event.start.getTime() - timelineStart.getTime()) / totalTimeInMs;
        const eventDuration = (event.end.getTime() - event.start.getTime()) / totalTimeInMs;
        eventElement.style.left = `${eventStartOffset * 100}%`;
        eventElement.style.width = (event.end.getTime() - event.start.getTime()) / (86400 / pxPerDay * 1000) - 10 + "px";
        eventElement.style.top = `${index * 30 + index * 8}px`;
        const eventTitleDiv = document.createElement('div');
        eventTitleDiv.classList.add('event-title');
        const timeRemainingSpan = document.createElement('div');
        timeRemainingSpan.classList.add('time-remaining');
        eventElement.appendChild(timeRemainingSpan);
        const completionBox = document.createElement('div');
        completionBox.classList.add('completion-box');
        completionBox.style.border = '2px dashed lightgrey';
        completionBox.style.backgroundColor = 'rgba(225, 225, 225, 0.5)';
        completionBox.dataset.status = '0';
        completionBox.addEventListener('click', toggleCompletionStatus);
        eventTitleDiv.appendChild(completionBox);
        const eventTitle = document.createElement('span');
        const isBlacklisted = window.walkthroughBlackWords.some(keyword =>
            event.name.includes(keyword)
        );
        const isYsQuest = event.title.includes("时限内完成") && event.title.includes("任务");
        if (event.type === "event" && !isBlacklisted && !isYsQuest) {
            eventTitle.innerHTML = `${event.name} 🎦`;
        } else {
            eventTitle.textContent = event.name;
        }
        eventTitleDiv.appendChild(eventTitle);
        updateEventCountdown();
        // 添加倒计时逻辑
        function updateEventCountdown() {
            const now = new Date();
            const startTime = new Date(event.start);
            const endTime = new Date(event.end);
            if (now < startTime) {
                // 活动未开始，显示开始倒计时
                const timeRemaining = startTime.getTime() - now.getTime();
                const days = Math.floor(timeRemaining / (1000 * 60 * 60 * 24));
                const hours = Math.floor((timeRemaining % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                const minutes = Math.floor((timeRemaining % (1000 * 60 * 60)) / (1000 * 60));
                const seconds = Math.floor((timeRemaining % (1000 * 60)) / 1000);
                timeRemainingSpan.textContent = `即将开始 ${days}天 ${hours}小时`;
                // timeRemainingSpan.style.color = 'orange';
                const timeRemainingWidth = timeRemainingSpan.offsetWidth;
                timeRemainingSpan.style.right = 'auto';
                timeRemainingSpan.style.left = `-${(timeRemainingWidth === 0 ? 90 : timeRemainingWidth) + 10}px`;
            } else if (now >= startTime && now <= endTime) {
                // 活动进行中，显示剩余时间
                const timeRemaining = endTime.getTime() - now.getTime();
                const days = Math.floor(timeRemaining / (1000 * 60 * 60 * 24));
                const hours = Math.floor((timeRemaining % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                timeRemainingSpan.textContent = `${days}天 ${hours}小时`;
                // timeRemainingSpan.style.color = 'green';
                const timeRemainingWidth = timeRemainingSpan.offsetWidth;
                timeRemainingSpan.style.left = 'auto';
                timeRemainingSpan.style.right = `-${(timeRemainingWidth === 0 ? 90 : timeRemainingWidth) + 10}px`;
            } else {
                // 活动已结束，显示结束时间
                const timePassed = now.getTime() - endTime.getTime();
                const days = Math.floor(timePassed / (1000 * 60 * 60 * 24));
                const hours = Math.floor((timePassed % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                timeRemainingSpan.textContent = `已结束 ${days}天 ${hours}小时`;
                // timeRemainingSpan.style.color = 'red';
                const timeRemainingWidth = timeRemainingSpan.offsetWidth;
                timeRemainingSpan.style.left = 'auto';
                timeRemainingSpan.style.right = `-${(timeRemainingWidth === 0 ? 90 : timeRemainingWidth) + 10}px`;
            }

        }
        // 初始化倒计时
        updateEventCountdown();
        setInterval(updateEventCountdown, 1000);
        eventElement.addEventListener('click', function () {
            document.querySelectorAll('.event').forEach(e => {
                if (e.style.borderTopWidth === "3px") {
                    e.style.border = 'none';
                    e.style.top = parseInt(e.style.top) + 3 + "px";
                }
            });
            eventElement.style.border = '3px solid white';
            eventElement.style.top = parseInt(eventElement.style.top) - 3 + "px";
            if (event.bannerImage) {
                showBannerWithInfo(event);
            }
        });
        const now = new Date();
        const timeRemainingInMs = event.end.getTime() - now.getTime();
        const oneDayInMs = 1000 * 60 * 60 * 24;
        if (timeRemainingInMs <= oneDayInMs + oneDayInMs / 2) {
            eventElement.style.backgroundImage = `linear-gradient(to right, ${event.color} calc(100% - 252px), red 100%)`;
        } else if (timeRemainingInMs <= 3 * oneDayInMs + oneDayInMs / 2) {
            eventElement.style.backgroundImage = `linear-gradient(to right, ${event.color} calc(100% - 252px), #FF5000 100%)`;
        }
        eventElement.appendChild(eventTitleDiv);
        // 创建并添加带有 bannerImage 的 div
        const bannerDiv = document.createElement('div');
        bannerDiv.classList.add('event-banner');
        bannerDiv.style.backgroundImage = `url(${event.bannerImage})`;
        if (event.type === "gacha") {
            if (event.game === "ys") {
                bannerDiv.style.backgroundPosition = 'center 45px';
            } else if (event.game === "sr") {
                bannerDiv.style.backgroundPosition = 'center 25px';
            } else if (event.game === "zzz") {
                bannerDiv.style.backgroundPosition = 'center 34px';
            } else {
                if (!event.name.includes("武器")) {
                    bannerDiv.style.backgroundPosition = 'center 25%';
                }
                else {
                    bannerDiv.style.backgroundPosition = 'center center';
                }
            }
        } else {
            bannerDiv.style.backgroundPosition = 'center';
        }
        bannerDiv.style.position = 'absolute';
        bannerDiv.style.right = '0';
        bannerDiv.style.top = '0';
        bannerDiv.style.bottom = '0';
        bannerDiv.style.width = '100px'; // 你可以根据需要调整宽度
        // console.log(event)
        eventElement.appendChild(bannerDiv);
        timeline.appendChild(eventElement);
        updateCurrentTimeMarker();
        timeline.style.marginLeft = "20px";
        timeline.style.width = totalDays * pxPerDay + "px";
        const currentOffset = (now.getTime() - timelineStart.getTime()) / totalTimeInMs;
        timeline_container.scrollLeft = currentOffset * totalDays * pxPerDay - timeline_container.offsetWidth / 2 + 20;
    });

    const linestylediv = document.createElement("style");
    linestylediv.innerHTML = `.date-label-line {height:${(timeline.children.length) * 40 - 15}px!important;}`;
    document.body.appendChild(linestylediv);
    setInterval(updateTodayHighlight, 500);
    initialEvents = [...document.querySelectorAll('.event')];
    sortEvents();
    updateCurrentTimeMarker();
    loadCompletionStatus();
}

function updateCurrentTimeMarker() {
    const timeline = document.querySelector('.timeline');
    const currentTimeMarker = document.querySelector('.current-time-marker') || document.createElement('div');
    const currentTimeLabel = document.querySelector('.current-time-label') || document.createElement('div');
    const now = new Date();
    const events = Array.from(document.querySelectorAll('.event'));
    const eventStartTimes = events.map(event => new Date(Number(event.dataset.start)));
    const eventEndTimes = events.map(event => new Date(Number(event.dataset.end)));
    const timelineStart = new Date(Math.min(...eventStartTimes));
    const timelineEnd = new Date(Math.max(...eventEndTimes));
    timelineStart.setDate(timelineStart.getDate() - 5);
    timelineStart.setHours(0, 0, 0, 0);
    timelineEnd.setDate(timelineEnd.getDate() + 5);
    timelineEnd.setHours(0, 0, 0, 0);
    const totalTimeInMs = timelineEnd - timelineStart;
    const currentOffset = (now.getTime() - timelineStart.getTime()) / totalTimeInMs;
    const offsetLeft = (now.getTime() - timelineStart.getTime()) / (86400 / pxPerDay * 1000) + "px";
    currentTimeMarker.classList.add('current-time-marker');
    currentTimeMarker.style.height = (document.querySelector(".timeline").children.length - 2) * 40 + "px";
    currentTimeMarker.style.left = offsetLeft;
    currentTimeMarker.style.display = 'block';
    currentTimeLabel.classList.add('current-time-label');
    currentTimeLabel.textContent = `${formatTime(now)}`;
    currentTimeLabel.style.left = offsetLeft;
    if (!document.querySelector('.current-time-marker')) {
        timeline.appendChild(currentTimeMarker);
    }
    if (!document.querySelector('.current-time-label')) {
        timeline.appendChild(currentTimeLabel);
    }
}

function updateTodayHighlight() {
    const today = formatLocalDate(new Date());
    document.querySelectorAll('.date-label').forEach(label => {
        const labelDate = label.dataset.date;
        if (labelDate === today) {
            label.classList.add('today');
            if (!label.children[0].classList.contains("first-day")) {
                label.children[0].classList.add('today-date');
            }
        } else {
            label.classList.remove('today');
            label.children[0].classList.remove('today-date');
        }
    });
}

function showBannerWithInfo(event) {
    const bannerContainer = document.querySelector('.banner-img-container');
    const bannerImage = bannerContainer.querySelector('.banner-img');
    const eventNameElem = bannerContainer.querySelector('.event-name');
    const eventStartDateElem = bannerContainer.querySelector('.event-start-date');
    const eventEndDateElem = bannerContainer.querySelector('.event-end-date');
    const eventRemainingTimeElem = bannerContainer.querySelector('.event-remaining-time');
    if (window.remainingTimeInterval) {
        clearInterval(window.remainingTimeInterval);
        window.remainingTimeInterval = null;
    }
    bannerImage.src = event.bannerImage;
    let displayName = event.name;
    const isBlacklisted = window.walkthroughBlackWords.some(keyword =>
        displayName.includes(keyword)
    );
    console.log(event.type, isBlacklisted);
    const isYsQuest = event.title.includes("时限内完成") && event.title.includes("任务");
    if (event.type === "event" && !isBlacklisted && !isYsQuest) {
        // displayName = displayName.replace('🎦', '').trim();
        eventNameElem.innerHTML = `${displayName}<br><a href="https://search.bilibili.com/all?keyword=${encodeURIComponent(displayName)}" 
        target="_blank" style="color: #00a3ff;text-decoration: none;" rel="noreferrer">
        【点击快速搜索攻略】
        </a>`;
        console.log(eventNameElem.innerHTML)
    }
    else if (event.type === "gacha" && event.name.includes('】')) {
        let name = event.name.split("】");
        let weapons = name[1].split(", ");
        let title = weapons[0].split(": ")[0];
        let formattedHTML = `${name[0]}】<br>${title}`;
        if (event.name.includes(':')) {
            weapons.forEach((weapon, index) => {
                if (index === 0) {
                    weapon = weapon.split(": ")[1];
                }
                formattedHTML += `<br>${index + 1}. ${weapon}`;
            });
        }
        eventNameElem.innerHTML = formattedHTML;
    } else {
        eventNameElem.textContent = `${event.name}`;
    }
    eventStartDateElem.textContent = `📣 ${formatDateTime(event.start)}`;
    eventEndDateElem.textContent = `🛑 ${formatDateTime(event.end)}`;

    // 更新右下角倒计时
    const updateRemainingTime = () => {
        const now = new Date();
        if (now < event.start) {
            // 活动未开始
            const timeUntilStart = event.start.getTime() - now.getTime();
            const days = Math.floor(timeUntilStart / (1000 * 60 * 60 * 24));
            const hours = Math.floor((timeUntilStart % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
            const minutes = Math.floor((timeUntilStart % (1000 * 60 * 60)) / (1000 * 60));
            const seconds = Math.floor((timeUntilStart % (1000 * 60)) / 1000);
            const formattedTime = `${days}天 ${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
            eventRemainingTimeElem.textContent = `⏳ 距开始 ${formattedTime}`;
        } else if (now > event.end) {
            // 活动已结束
            const timeSinceEnd = now.getTime() - event.end.getTime();
            const days = Math.floor(timeSinceEnd / (1000 * 60 * 60 * 24));
            const hours = Math.floor((timeSinceEnd % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
            const minutes = Math.floor((timeSinceEnd % (1000 * 60 * 60)) / (1000 * 60));
            const seconds = Math.floor((timeSinceEnd % (1000 * 60)) / 1000);
            const formattedTime = `${days}天 ${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
            eventRemainingTimeElem.textContent = `⏳ 已结束 ${formattedTime}`;
        } else {
            // 活动进行中
            const timeRemaining = event.end.getTime() - now.getTime();
            const days = Math.floor(timeRemaining / (1000 * 60 * 60 * 24));
            const hours = Math.floor((timeRemaining % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
            const minutes = Math.floor((timeRemaining % (1000 * 60 * 60)) / (1000 * 60));
            const seconds = Math.floor((timeRemaining % (1000 * 60)) / 1000);
            const formattedTime = `${days}天 ${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
            eventRemainingTimeElem.textContent = `⏳ 剩余 ${formattedTime}`;
        }
    };

    // 初始化倒计时
    updateRemainingTime();
    // 每秒更新一次倒计时
    window.remainingTimeInterval = setInterval(updateRemainingTime, 1000);
    // 显示 banner 容器
    bannerContainer.style.display = 'block';
    // 关闭按钮逻辑
    const closeBtn = bannerContainer.querySelector('.close-btn');
    closeBtn.addEventListener('click', () => {
        bannerContainer.style.display = 'none';
        clearInterval(window.remainingTimeInterval);
        window.remainingTimeInterval = null;
        document.querySelectorAll('.event').forEach(e => {
            if (e.style.borderTopWidth === "3px") {
                e.style.border = 'none';
                e.style.top = parseInt(e.style.top) + 3 + "px";
            }
        });
    }, { once: true });
}

function createLegend() {
    const legendContainer = document.querySelector('.legend-list');
    legendContainer.innerHTML = "";
    const activityTypes = [
        { type: 'ys', name: '原神' },
        { type: 'sr', name: '崩坏：星穹铁道' },
        { type: 'zzz', name: '绝区零' },
        { type: 'ww', name: '鸣潮' }
    ];
    activityTypes.forEach(activity => {
        const legendItem = document.createElement('div');
        legendItem.classList.add('legend-item');
        const colorBox = document.createElement('span');
        colorBox.dataset.game = activity.type;
        colorBox.classList.add('color-box');
        colorBox.style.backgroundColor = getColor(activity.type);
        // 添加点击事件监听器
        colorBox.addEventListener('click', () => toggleGameEventsVisibility(activity.type));
        const label = document.createElement('span');
        label.classList.add('label');
        label.textContent = activity.name;
        legendItem.appendChild(colorBox);
        legendItem.appendChild(label);
        legendContainer.appendChild(legendItem);
    });
    const legendNote = document.createElement('div');
    legendNote.innerHTML = '<span style="width: 24px;display: inline-block;text-align: center;margin-right: 8px;">🎦</span>可快速搜索攻略';
    document.querySelector('.legend-list').appendChild(legendNote);
}

function toggleGameEventsVisibility(gameType) {
    const events = document.querySelectorAll('.event');
    // 切换隐藏状态
    eventsSettings.hide_setting[gameType] = !eventsSettings.hide_setting[gameType];
    events.forEach(event => {
        if (event.dataset.game === gameType) {
            event.style.display = eventsSettings.hide_setting[gameType] ? 'none' : 'flex';
        }
    });
    recalculateEventPositions();
    updateColorBoxStyle(gameType);
    saveEventsSettings();
}

function saveEventsSettings() {
    localStorage.setItem('events_setting', JSON.stringify(eventsSettings));
    updateSettings(eventsSettings, socket);
}

function recalculateEventPositions() {
    const events = document.querySelectorAll('.event');
    let currentTop = 0; // 当前事件的顶部位置
    events.forEach(event => {
        if (event.style.display !== 'none') {
            // 如果事件未隐藏，调整其位置
            event.style.top = `${currentTop}px`;
            currentTop += event.offsetHeight + 8; // 增加事件高度和间距
        }
    });
}

function loadHiddenStatus() {
    const events = document.querySelectorAll('.event');
    // 确保 eventsSettings.hide_setting 存在
    if (!eventsSettings.hide_setting) {
        eventsSettings.hide_setting = {
            ys: false,
            sr: false,
            zzz: false,
            ww: false,
        };
    }
    events.forEach(event => {
        const gameType = event.dataset.game;
        const isHidden = eventsSettings.hide_setting[gameType] || false;
        if (isHidden) {
            event.style.display = 'none';
        } else {
            event.style.display = 'flex';
        }
    });

    initializeColorBoxStyles();
    recalculateEventPositions();
}

function updateColorBoxStyle(gameType) {
    const colorBox = document.querySelector(`.color-box[data-game="${gameType}"]`);
    if (!colorBox) return;
    // 检查当前游戏类型的事件是否全部隐藏
    const isAllHidden = eventsSettings.hide_setting[gameType] || false;
    if (isAllHidden) {
        // 如果全部隐藏，设置为虚线边框空心
        colorBox.style.border = '2px dashed ' + getColor(gameType);
        colorBox.style.backgroundColor = 'transparent';
    } else {
        // 如果显示，设置为实心
        colorBox.style.border = '2px solid ' + getColor(gameType);
        colorBox.style.backgroundColor = getColor(gameType);
    }
}

function initializeColorBoxStyles() {
    const activityTypes = ['ys', 'sr', 'zzz', 'ww']; // 游戏类型
    activityTypes.forEach(gameType => {
        updateColorBoxStyle(gameType);
    });
}

function isToday(date) {
    const today = new Date();
    return date.getDate() === today.getDate() &&
        date.getMonth() === today.getMonth() &&
        date.getFullYear() === today.getFullYear();
}

function getColor(type) {
    const colors = {
        sr: '#E0A064',
        ww: '#18A0E8',
        ys: '#A068F8',
        zzz: '#4CAF50',
    };
    return colors[type] || '#FFFFFF';
}

function extractTitle(title) {
    const regex = /[「\[]([^「\]」]+)[」\]]/;
    const match = regex.exec(title);
    return match ? match[1] : title;
}

function formatLocalDate(date) {
    return date.Format("yyyy-MM-dd");
}

function formatDate(date) {
    return date.Format("MM-dd");
}

function formatTime(date) {
    return date.Format("HH:mm:ss");
}

function formatDateTime(date) {
    return date.Format("yyyy-MM-dd HH:mm:ss");
}

function formatDateTime2(date) {
    return date.Format("yyyy-MM-dd HH:mm");
}

function formatWeekDay(date) {
    const weekDays = ['日', '一', '二', '三', '四', '五', '六'];
    return `${weekDays[date.getDay()]}`;
}

function getDaysInMonth(year, month) {
    return new Date(year, month + 1, 0).getDate();
}

function getDaysInMonth2(date) {
    const year = date.getFullYear();
    const month = date.getMonth();
    return new Date(year, month + 1, 0).getDate();
}

function isSameDate(date1, date2) {
    return date1.getFullYear() === date2.getFullYear() &&
        date1.getMonth() === date2.getMonth() &&
        date1.getDate() === date2.getDate();
}

document.querySelector('.timeline-container').addEventListener('wheel', (event) => {
    event.preventDefault();
    const scrollAmount = event.deltaY;
    event.currentTarget.scrollLeft += scrollAmount;
});

document.querySelector('.close-btn').addEventListener('click', function () {
    document.querySelector('.banner-img-container').style.display = 'none';
});

function toggleCompletionStatus(event) {
    event.stopPropagation();
    const box = event.target;
    const eventElement = box.closest('.event');
    const uuid = eventElement.dataset.uuid;
    const currentStatus = box.dataset.status;
    let newStatus;
    switch (currentStatus) {
        case '0':
            newStatus = '1';
            box.style.border = '2px solid lightgreen';
            box.style.backgroundColor = '#6f67';
            box.innerHTML = "✅"
            break;
        case '1':
            newStatus = '2';
            box.style.border = '2px solid yellow';
            box.style.backgroundColor = 'rgba(255, 255, 0, 0.5)';
            box.innerHTML = "⏩"
            break;
        case '2':
            newStatus = '0';
            box.style.border = '2px dashed lightgrey';
            box.style.backgroundColor = 'rgba(225, 225, 225, 0.5)';
            box.innerHTML = ""
            break;
    }

    box.dataset.status = newStatus;
    if (!eventsSettings.events[uuid]) {
        eventsSettings.events[uuid] = {};
    }
    eventsSettings.events[uuid].isCompleted = newStatus;
    saveEventsSettings();
}

function loadCompletionStatus() {
    const events = document.querySelectorAll('.event');
    // 确保 eventsSettings.events 存在
    if (!eventsSettings.events) {
        eventsSettings.events = {};
    }
    events.forEach(event => {
        const uuid = event.dataset.uuid;
        const completionBox = event.querySelector('.completion-box');
        const status = eventsSettings.events[uuid]?.isCompleted || '0';
        completionBox.dataset.status = status;
        switch (status) {
            case '1':
                completionBox.style.border = '2px solid lightgreen';
                completionBox.style.backgroundColor = '#6f67';
                completionBox.innerHTML = "✅";
                break;
            case '2':
                completionBox.style.border = '2px solid yellow';
                completionBox.style.backgroundColor = 'rgba(255, 255, 0, 0.5)';
                completionBox.innerHTML = "⏩";
                break;
            default:
                completionBox.style.border = '2px dashed lightgrey';
                completionBox.style.backgroundColor = 'rgba(225, 225, 225, 0.5)';
                completionBox.innerHTML = "";
                break;
        }
    });
}

Date.prototype.Format = function (fmt) {
    var o = {
        "M+": this.getMonth() + 1,
        "d+": this.getDate(),
        "H+": this.getHours(),
        "m+": this.getMinutes(),
        "s+": this.getSeconds(),
        "q+": Math.floor((this.getMonth() + 3) / 3),
        "S": this.getMilliseconds()
    };
    fmt = fmt.replace(/(y+)/, (match, p1) => {
        return (this.getFullYear() + "").slice(-p1.length);
    });
    for (var k in o) {
        fmt = fmt.replace(new RegExp("(" + k + ")"), (match, p1) => {
            return p1.length == 1 ? o[k] : ("00" + o[k]).slice(-p1.length);
        });
    }
    return fmt;
}

function changeTime(t) {
    const OriginalDate = Date;
    const customTime = new OriginalDate(t);
    const offset = customTime.getTime() - OriginalDate.now();
    window.Date = function (...args) {
        if (args.length === 0) {
            return new OriginalDate(OriginalDate.now() + offset);
        } else {
            return new OriginalDate(...args);
        }
    };
    Date.now = function () {
        return OriginalDate.now() + offset;
    };
    Date.UTC = OriginalDate.UTC;
    Date.parse = OriginalDate.parse;
    Date.prototype = OriginalDate.prototype;
}

function addLoginButton() {
    const loginButton = document.createElement("button");
    const logoutButton = document.querySelector(".logout-btn");
    logoutButton && logoutButton.remove();
    const userContainer = document.querySelector(".user-container");
    userContainer && userContainer.remove();
    const loginContainer = document.querySelector(".login-container");
    loginButton.innerHTML = "点击登录";
    loginButton.classList.add("login-button");
    loginButton.addEventListener("click", function () {
        loginButton.remove()
        const loginForm = document.querySelector(".login-form");
        loginForm.classList.remove("hide");
    });
    loginContainer.appendChild(loginButton);
}

function addLogoutButton() {
    let logoutButton = document.querySelector(".logout-btn");
    logoutButton && logoutButton.remove();
    logoutButton = document.createElement("button");
    const loginContainer = document.querySelector(".login-container");
    logoutButton.innerHTML = "点击退出登录";
    const usernameinput = document.querySelector("input[name=username]");
    const passwordinput = document.querySelector("input[name=password]");
    logoutButton.classList.add("logout-btn");
    logoutButton.addEventListener("click", function () {
        logoutButton.innerHTML = "...";
        logoutButton.disabled = true;
        logout();
        const logbtn = document.querySelector(".login-btn");
        logbtn.innerHTML = "确认登录";
        logbtn.disabled = false;
    });
    const userContainer = document.createElement("div");
    userContainer.innerHTML = `已登录: ${usernameinput.value || "-"}`;
    userContainer.classList.add("user-container");
    usernameinput.value = "";
    passwordinput.value = "";
    loginContainer.appendChild(userContainer);
    loginContainer.appendChild(logoutButton);
}


// 排序事件函数
function sortEvents() {
    const timeline = document.querySelector('.timeline');
    let events = [];
    if (eventsSettings.sortOrder === 'default') {
        // 使用初次获取的数据
        events = [...initialEvents];
    } else if (eventsSettings.sortOrder === 'end-time') {
        // 按活动结束时间升序排序
        events = Array.from(document.querySelectorAll('.event')).sort((a, b) => {
            const endTimeA = a.dataset.end;
            const endTimeB = b.dataset.end;
            return endTimeA - endTimeB;
        });
    }
    // 清空时间轴并重新添加排序后的事件
    timeline.innerHTML = '';
    events.forEach(event => timeline.appendChild(event));
    // 重新计算事件位置
    recalculateEventPositions();
}

// 获取游戏顺序
function getGameOrder(gameType) {
    const gameOrder = {
        'ys': 1,
        'sr': 2,
        'zzz': 3,
        'ww': 4
    };
    return gameOrder[gameType] || 0;
}