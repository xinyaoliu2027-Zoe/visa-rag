# SETUP — 从这里开始（先读这一个文件就好）

## 别慌，先看这段

这个项目有快 20 个文件，但**今天你只跟这一个文件打交道**。其他文件是你未来 10 周慢慢改、慢慢往上盖的东西，今天一个都不用打开。

今天的唯一目标：**让这个空骨架在你的电脑上跑起来。** 大概 1 小时，其中大部分时间是在等下载，不需要写任何代码。

把整个项目想成三个阶段：

| 阶段 | 时间 | 你做什么 | 跟哪个文件 |
|---|---|---|---|
| **Phase 0** | 今天，约 1 小时 | 把空骨架跑起来（装软件、敲几条命令） | **本文件 SETUP.md** |
| Phase 1 | 第 1 周 | 喂数据进去 | WEEK1_CHECKLIST.md |
| Phase 2 | 第 2–10 周 | 一点点把功能做好 | 后续我再给你 |

下面开始 Phase 0。**每一步都有「✓ 成功的样子」，对上了再做下一步。**

---

## Step 1 — 把项目搬到一个属于你的文件夹

现在 `visa_rag` 文件夹在 Claude 的工作目录里，不稳妥。先把它搬回家。

1. 在上面的文件卡片里，随便点开一个文件，在「访达 / Finder」里找到它
2. 往上一层，找到整个 `visa_rag` 文件夹
3. 把整个 `visa_rag` 文件夹**复制**到 `~/Documents/` 下

✓ 成功的样子：你在「文稿」里能看到 `Documents/visa_rag/`，里面有 `SETUP.md`、`docker-compose.yml` 等文件。

---

## Step 2 — 安装 Docker Desktop

Docker 是个能"一键把数据库和应用都开起来"的工具，你不用懂它的原理。

1. 打开 https://www.docker.com/products/docker-desktop/
2. 下载 Mac 版（注意选对芯片：Apple Silicon / M 系列，还是 Intel）
3. 安装，然后**打开** Docker Desktop 这个 App
4. 等它左下角的小图标变成稳定的绿色 / 显示 "Engine running"

✓ 成功的样子：打开「终端 / Terminal」，输入 `docker --version`，能看到一行版本号。

---

## Step 3 — 拿一个 Anthropic API key

这个 key 是让你的应用能调用 AI 模型用的。

1. 打开 https://console.anthropic.com/
2. 注册 / 登录（新账号通常有少量免费额度）
3. 左侧菜单找到 "API Keys" → "Create Key"
4. **复制这串 key 存好**（它只显示一次，形如 `sk-ant-...`）

Cohere 的 key 这周用不到，可以跳过。

---

## Step 4 — 创建你的 .env 文件

`.env` 是放密钥的文件，不会被上传到任何地方。

1. 打开「终端」
2. 一行行输入下面的命令（每行按回车）：

```bash
cd ~/Documents/visa_rag
cp .env.example .env
open -e .env
```

3. 最后一条命令会用「文本编辑」打开 `.env`。找到这一行：

```
ANTHROPIC_API_KEY=sk-ant-...
```

把 `sk-ant-...` 换成你 Step 3 复制的真实 key。保存，关闭。

✓ 成功的样子：`.env` 文件里 `ANTHROPIC_API_KEY=` 后面是你自己的 key。

---

## Step 5 — 构建项目（第一次会慢）

回到「终端」，确认你还在项目目录里，然后输入：

```bash
cd ~/Documents/visa_rag
docker compose build
```

**这一步要 5–10 分钟**，它在下载和安装所有依赖、还会预下载一个 AI 嵌入模型。屏幕会滚很多字，是正常的。去倒杯水。

✓ 成功的样子：最后出现 `=> => naming to ...visa_rag_app:dev` 之类的字样，命令结束，光标回到你能输入的状态。

---

## Step 6 — 启动！

```bash
docker compose up -d
```

这条命令会同时开两个东西：一个数据库、一个你的应用。`-d` 表示在后台跑。

✓ 成功的样子：看到两行带 `Started` 或 `Healthy` 的提示，分别是 `visa_rag_postgres` 和 `visa_rag_app`。

再确认一下：

```bash
docker compose ps
```

✓ 成功的样子：两个服务的状态都是 `running`（app 可能要再等 20 秒才变 `healthy`）。

---

## Step 7 — 验证应用活着

```bash
curl http://localhost:8000/health
```

✓ 成功的样子：屏幕回 `{"status":"ok"}`。

你也可以直接在浏览器打开 http://localhost:8000/docs ——会看到一个自动生成的 API 测试页面。**这就是你的应用，已经在跑了。**

---

## Step 8 — 验证数据库建好了

```bash
docker compose exec postgres psql -U postgres -d postgres -c "\dt visa.*"
```

✓ 成功的样子：列出三张表 `documents`、`chunks`、`ingestion_runs`。

输入 `exit` 或直接进行下一步。

---

## Step 9（今天可选）— 放上 GitHub

不是必须，但强烈建议——之后每周的进度会有提交记录，面试时这本身就是故事。

1. 在 https://github.com/new 建一个空 repo，名字叫 `visa-rag`，**不要**勾选任何初始化选项
2. 回到终端：

```bash
cd ~/Documents/visa_rag
git init
git add .
git commit -m "Initial skeleton"
git branch -M main
git remote add origin https://github.com/你的用户名/visa-rag.git
git push -u origin main
```

✓ 成功的样子：刷新 GitHub 页面，能看到所有文件。

---

## Phase 0 完成的标准

下面三条都对上，今天就成功了：

1. `curl http://localhost:8000/health` 返回 `{"status":"ok"}`
2. `docker compose ps` 显示两个服务都在 running
3. `\dt visa.*` 能看到三张表

---

## 现在「还不能用」的部分（这是正常的）

如果你现在去试 `/ask` 问问题，它只会回复"找不到权威来源，请咨询 DSO"。

**这是对的，不是 bug。** 因为数据库里还没有任何文档——你还没喂数据。喂数据是 Phase 1 的事，在 `WEEK1_CHECKLIST.md` 的 Day 3 开始。

今天你证明了"骨架能跑"，就够了。

---

## 卡住了怎么办

| 现象 | 怎么办 |
|---|---|
| `docker: command not found` | Docker Desktop 没装好或没打开，回 Step 2 |
| `docker compose build` 报网络错误 | 检查网络，重新跑一遍命令（它会接着上次的进度） |
| Step 6 后 app 一直不 healthy | 跑 `docker compose logs app` 看报错；最常见是 `.env` 里 key 没填对 |
| 端口 5432 或 8000 被占用 | 你电脑上已经有别的程序在用这个端口，关掉它，或问 Claude 怎么改端口 |
| 全乱了想重来 | `docker compose down -v` 清空一切，再从 Step 6 开始 |

任何一步卡住超过 20 分钟，把报错信息原文复制下来问我，别硬磕。

---

## 下一步

Phase 0 完成后，打开 `WEEK1_CHECKLIST.md`，从 **Day 3（抓取官方文档）** 开始——Day 1、Day 2 的内容你今天已经在本文件里做完了。
