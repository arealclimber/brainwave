# 本地執行 Notion 字數統計（Word Count）

## 平常就用這一行（全庫每頁重算 + 寫回）

```bash
cd ~/arealclimber/brainwave
PYTHONPATH=. venv/bin/python scripts/update_word_counts.py
```

每次都從頭重算，不依賴 `last_edited_time` 變更偵測；只有算出來跟現存 `Words` 不同的頁才會寫入，所以重跑安全（idempotent）。1705 頁約需 12~15 分鐘（讀取為主，寫入限速 ~3 req/s）。

其他用法：

```bash
# 只看會改什麼，不寫入
PYTHONPATH=. venv/bin/python scripts/update_word_counts.py --dry-run

# 單頁
PYTHONPATH=. venv/bin/python scripts/update_word_counts.py --page <PAGE_ID>

# 留下逐頁報表（page_id / url / title / stored / recomputed / error）
PYTHONPATH=. venv/bin/python scripts/update_word_counts.py --csv /tmp/word_counts.csv

# 先審再寫：先產報表，看過 DIFF 再跑一次寫入
PYTHONPATH=. venv/bin/python scripts/update_word_counts.py --dry-run --csv /tmp/word_counts.csv
```

前置條件：`brainwave/.env` 需有 `NOTION_TOKEN` 與 `NOTION_DATABASE_ID`（已存在）。`PYTHONPATH=.` 是必要的，因為腳本在 `scripts/` 底下但要 import repo root 的 `notion_service`。

## 字數功能在 repo 裡的位置

| 元件 | 位置 | 作用 |
| --- | --- | --- |
| 計數演算法 | `notion_service.py` `count_words()` | 中文字元逐字計 1，其餘用 `\b\w+\b` 抓英數 token，兩者相加 |
| 取內文 | `notion_service.py` `get_page_content()` | 讀 page 的 top-level blocks，遇到 `Readability` / `Correctness` / `Ask AI` 這幾個 H1 就停（AI 產生的段落不算進字數，見 `AI_SECTION_HEADINGS`） |
| 寫回 Notion | `notion_service.py` `update_word_count()` | 更新 page 的 `Words` number property |
| 單頁 read→count→write | `notion_service.py` `calculate_and_update_word_count()` | 上面三者串起來 |
| 列出全庫頁面 | `notion_service.py` `get_database_pages()` | cursor 分頁，回傳全部 pages |
| 排程 / 批次 | `monitor.py` `manual_update_all()` | 走訪整個 database（正式環境每天 UTC+8 03:00 由 APScheduler 觸發，只更新有變動的頁） |
| HTTP 入口 | `main.py` | `POST /notion/word-count/update` (單頁)、`POST /notion/word-count/update-all` |

不寫腳本、直接用現成程式碼跑單頁：

```bash
cd ~/arealclimber/brainwave
PYTHONPATH=. venv/bin/python -c "
import asyncio, os
from dotenv import load_dotenv; load_dotenv(os.path.join(os.getcwd(), '.env'))
from notion_service import notion_service
print(asyncio.run(notion_service.calculate_and_update_word_count('<PAGE_ID>')))
"
```

或啟本地 server 打 API：

```bash
cd ~/arealclimber/brainwave
venv/bin/python -m uvicorn realtime_server:app --port 8000
curl -X POST localhost:8000/notion/word-count/update -H 'Content-Type: application/json' -d '{"page_id":"<PAGE_ID>"}'
curl -X POST localhost:8000/notion/word-count/update-all
```

## 已知限制

- `get_page_content()` 不遞迴 child blocks（toggle、巢狀 list、column）→ 收在 toggle 裡的文字不計入字數。目前刻意保留此行為。
- 分頁問題（`get_database_pages()` 只拿前 100 頁、`get_page_content()` 只讀前 100 個 block）已於 2026-07-29 修掉；修之前每天的排程實際上只覆蓋最近編輯的 100 頁，長頁也會被截斷。

## 2026-07-29 全量重算結果

- 全庫 1705 頁，268 頁字數與現行定義不一致 → 已全部更新，0 失敗；事後查 database property 驗證 1705/1705 相符。
- 268 頁的組成：99 頁 `Words` 原本是空的；其餘為既有數值偏移。
- 其中 67 頁字數大幅下降（例：3349 → 31）。逐頁比對後，這 67 頁的舊值都等於「含 AI 段落」的字數（誤差 ≤2%），且都存在 `Readability` / `Correctness` / `Ask AI` 的 H1 → 下降來自現行「只算 transcript」的定義，不是資料遺失。
- 剩餘 ±1~3 的小幅差異，推測是後續編輯造成的漂移（未逐頁查證）。
