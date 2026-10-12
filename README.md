# 网页版卡密商城原型

一个简单可用的 Python Flask + SQLite + Bootstrap 卡密销售网站。

## 本地运行

```bash
pip install -r requirements.txt
python app.py
```

访问 http://127.0.0.1:5000  
后台：http://127.0.0.1:5000/admin （admin / admin123）

## 免费部署到 Render.com（推荐）

1. 把整个项目上传到你的 GitHub 仓库（新建一个 public 或 private repo）。
2. 登录 [Render.com](https://render.com)（用 GitHub 账号登录最方便）。
3. 点击 **New +** → **Web Service**。
4. 连接你的 GitHub 仓库。
5. 设置：
   - **Name**：任意（如 card-key-shop）
   - **Runtime**：Python 3
   - **Build Command**：`pip install -r requirements.txt`
   - **Start Command**：`gunicorn app:app --bind 0.0.0.0:$PORT`
6. 选择 **Free** 计划，点击 **Create Web Service**。
7. 等待部署完成（约 2-5 分钟），Render 会给你一个 `https://xxx.onrender.com` 的免费链接。

### 注意事项（免费版）
- 闲置约 15 分钟后会休眠，首次访问会慢几秒（冷启动）。
- SQLite 数据在服务重启后会重置（免费实例无持久磁盘）。适合演示，正式用建议升级或换数据库。
- 默认管理员：admin / admin123

部署完成后即可公网访问。
