# 游梦纪事 - 游戏活动时间线管理

<!--![项目封面](https://img.shields.io/badge/版本-1.0.0-blue)-->
![License](https://img.shields.io/badge/License-MIT-green)
![Python](https://img.shields.io/badge/Python-3.12+-blue)
![Flask](https://img.shields.io/badge/Flask-3.1+-blue)

## 🌟 项目简介

游梦纪事是一个专注于二次元游戏活动时间线管理的Web应用，目前支持以下游戏：

- 🏰 原神
- 🚄 崩坏：星穹铁道
- 🎸 绝区零
- 🌪️ 鸣潮

项目通过抓取各游戏官方公告，自动整理活动时间信息，并以直观的时间轴形式展示，帮助玩家高效规划游戏时间。

## ✨ 主要功能特性

### 核心功能
- 📅 **多游戏活动时间线**：一站式查看所有支持游戏的限时活动
- ⏳ **实时倒计时**：精确显示活动剩余/已过时间
- 🎯 **活动分类**：区分常规活动、卡池活动等不同类型

### 账号功能（需登录）
- ✅ **活动状态标记**：标记活动为"未开始/进行中/已完成"
- 🔄 **多端同步**：登录后活动状态实时同步
- 🎨 **个性化设置**：自定义游戏显示/隐藏

### 用户体验
- 📱 **响应式设计**：适配各种设备屏幕
- 🖼️ **活动海报展示**：点击查看活动详情海报
- 🔍 **快速攻略搜索**：一键跳转B站搜索活动攻略

## 🛠️ 技术栈

### 后端
- **Python 3.8+**
- **Flask** - Web框架
- **SQLAlchemy** - ORM数据库管理
- **APScheduler** - 定时任务调度

### 前端
- **纯原生实现** - 无前端框架依赖
- **HTML5/CSS3** - 页面结构与样式
- **JavaScript** - 交互逻辑
- **WebSocket** - 实时数据同步

### 数据存储
- **SQLite** - 轻量级数据库

## 🚀 快速开始

### 环境要求
- Python 3.10+
- pip

### 安装步骤
```bash
# 克隆仓库
git clone https://github.com/shoyu3/game-events-timeline.git
cd game-events-timeline

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate    # Windows

# 安装依赖
pip install -r requirements.txt

# 运行应用
python app.py
```

<!-- # 初始化数据库
python init_db.py -->

### 默认账号
首次运行时，控制台会输出默认用户名和随机生成的密码：
```
[INFO] 初始用户已创建:
用户名: user
密码: xxxxxxxx
```

## 📊 数据更新机制

项目采用智能更新策略，确保数据新鲜度：
- 每天自动更新4次（9:00, 12:30, 18:00, 22:00）
<!-- - 手动触发更新API可用
- 数据变更时自动刷新前端展示 -->

<!-- ## 🌈 界面预览

![时间线界面](docs/screenshots/timeline.png)
*活动时间线主界面 - 直观展示各游戏活动时间轴*

![活动详情](docs/screenshots/event-detail.png)
*活动详情弹窗 - 显示活动海报和精确时间信息* -->

## 📚 使用指南

1. **浏览活动**：
   - 水平滚动查看完整时间线
   - 点击活动条查看详情

2. **标记活动状态**（需登录）：
   - 点击活动条左侧方框循环切换状态：
     - ⬜ 未开始
     - ✅ 已完成
     - ⏩ 进行中

3. **筛选游戏**：
   - 点击左侧栏游戏图标切换显示/隐藏

4. **搜索攻略**：
   - 点击详情弹窗中的【快速搜索攻略】链接

## 🤝 贡献指南

欢迎贡献代码！请遵循以下流程：

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 发起 Pull Request

## 📜 许可证

本项目采用 MIT 许可证 - 详情请见 [LICENSE](LICENSE) 文件

## 🔑 关键功能列表

### 前端功能
1. **时间轴可视化**
   - 水平滚动时间轴展示
   - 日期刻度与周几显示
   - 当前时间指示线

2. **活动交互**
   - 活动卡片点击展开详情
   - 活动状态标记(未开始/进行中/已完成)
   - 活动剩余时间实时计算

3. **游戏筛选**
   - 按游戏类型筛选显示
   - 游戏图例点击切换可见性

4. **用户系统**
   - 登录/注销功能
   - 活动状态多端同步
   - 用户设置存储

5. **详情展示**
   - 活动海报展示
   - 精确时间显示
   - 快速攻略搜索链接

6. **响应式设计**
   - 适配不同屏幕尺寸
   - 滚动优化

### 后端功能
1. **数据采集**
   - 多游戏公告定时抓取
   - 公告内容解析
   - 活动时间提取

2. **数据处理**
   - 活动时间标准化
   - 活动类型分类
   - 数据去重处理

3. **API服务**
   - 活动数据接口
   - 用户认证接口
   - 设置同步接口

4. **用户系统**
   - 密码加密存储
   - Token认证
   - 多设备状态同步

5. **定时任务**
   - 每日自动更新
   - 数据缓存管理
   - 更新日志记录

## TODO: 模块化改造计划

### 1. 游戏逻辑分离

**目标**：将各游戏的处理逻辑拆分为独立模块

**实施方案**：
```python
# 新结构
game_modules/
├── base_parser.py      # 基础解析类
├── genshin/            # 原神模块
│   ├── __init__.py
│   ├── constants.py    # 游戏特定常量
│   ├── parser.py       # 公告解析器
│   └── scraper.py      # 数据抓取器
├── starrail/           # 星穹铁道模块
│   ├── __init__.py
│   ├── constants.py
│   ├── parser.py
│   └── scraper.py
└── ...                 # 其他游戏同理
```

**接口规范**：
```python
class BaseGameScraper:
    GAME_ID = None
    GAME_NAME = None
    
    @classmethod
    def fetch_announcements(cls):
        """获取公告原始数据"""
        raise NotImplementedError
        
    @classmethod
    def parse_announcement(cls, raw_announcement):
        """解析单个公告"""
        raise NotImplementedError
```

### 2. 前端动态加载

**目标**：根据后端配置动态生成游戏列表

**改造点**：
1. 后端增加游戏配置接口 `/api/games`
2. 前端改为动态加载游戏列表
3. 游戏颜色、图标等配置化

```javascript
// 动态加载示例
async function loadGameList() {
    const response = await fetch('/api/games');
    const games = await response.json();
    
    games.forEach(game => {
        const gameTab = createGameTabElement(game);
        gameListContainer.appendChild(gameTab);
    });
}
```

### 3. 公共组件提取

**目标**：提取公共逻辑到基础模块

**提取内容**：
1. 时间处理工具
2. 网络请求工具
3. 缓存管理
4. 错误处理机制

### 4. 配置中心

**目标**：集中管理所有配置

**配置项**：
```python
# config.py
GAME_CONFIGS = {
    'genshin': {
        'name': '原神',
        'color': '#A068F8',
        'announce_url': 'https://hk4e-api.mihoyo.com/...',
        'enabled': True
    },
    # 其他游戏配置...
}
```

### 5. 新游戏接入流程

1. 创建游戏模块目录
2. 实现基础接口类
3. 注册到配置中心
4. 添加前端资源(图标等)

### 6. 待优化项

1. 错误处理与重试机制
2. 数据验证流程
3. 测试覆盖率提升
4. 文档完善

通过这种模块化改造，新游戏的接入将变得非常简单，只需实现特定游戏的解析逻辑即可，其他通用功能由基础模块提供支持。同时系统的可维护性和扩展性将大幅提升。

## 📞 联系

如有任何问题或建议，请通过以下方式联系：
- GitHub Issues

---

✨ **游梦纪事** - 让游戏时间管理更轻松 ✨