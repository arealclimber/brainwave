# Railway 本地直推 cheatsheet（不接 GitHub）

> 用 `railway up` 把當前 working directory 打包上傳，bypass GitHub。
> 對 feature branch 快速 iterate / hot-fix / 沒 push 到 remote 也想驗證很實用。

## 一次性設定（已做過可跳過）

```bash
railway login                       # 開瀏覽器登入
cd /Users/shirley/arealclimber/brainwave
railway link                        # 互動選 project + environment + service
railway status                      # 確認 link 對：Project / Environment / Service
```

`railway link` 之後會在 `.railway/` 寫設定，**不要 commit `.railway/`**（已在 .gitignore 就忽略這行）。

## 部署

```bash
# 一次性部署（推薦：阻塞直到 build 完）
railway up

# 部署但不 follow logs（背景，回 prompt）
railway up --detach

# 指定 service（多 service project）
railway up --service brainwave
```

`railway up` 會：
1. 把當前目錄 tar 起來上傳（受 `.railwayignore` / `.gitignore` 過濾，**包含未 commit 的 dirty changes**）
2. 在 Railway 端跑 `Dockerfile` build
3. 取代正在跑的 deployment

## 查 deploy 狀態

```bash
railway logs                        # 看當前 deployment 的執行 log
railway logs --deployment           # 看 build log
railway status                      # 看當前 deployment id / state
railway domain                      # 拿 public URL
```

## 環境變數

```bash
railway variables                   # 列出全部
railway variables --set "KEY=value" # 設一個
railway variables --set "OPENAI_API_KEY=sk-..." \
                  --set "GOOGLE_API_KEY=..."
```

⚠️ `--set` 會觸發 redeploy。

## Rollback

```bash
railway deployments                 # 列歷史 deployments
railway redeploy <deployment-id>    # 回滾到指定版本
```

## 常見坑

| 症狀 | 原因 | 解 |
|---|---|---|
| `railway up` 卡在 "Uploading..." | 上傳目錄太大（venv、__pycache__ 沒排除） | 加 `.railwayignore`：`venv/`、`__pycache__/`、`*.log`、`.git/` |
| Build 失敗 `pip` 找不到 package | `requirements.txt` 沒更新 | `pip freeze > requirements.txt` |
| `railway ssh` 拿到本機 shell（非 container） | 沒指定 service / link 沒對好 | `railway ssh --service <name> bash` |
| Deploy 後舊 JS 還在 | 瀏覽器 cache | 看 `realtime.html` script `?v=N`，bump 一下 |

## 我的 workflow（建議）

```bash
# 1. 改 code、本機快測
python realtime_server.py

# 2. 一鍵推 Railway
railway up --detach && railway logs
```
