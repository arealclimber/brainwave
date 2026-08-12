# 徹底從 git history 移除 `.claude/settings.local.json`

> **Why amend, not filter-repo?**
> 這個檔案只在 HEAD commit `8165b18` 出現過一次（已用 `git log --all --full-history -- .claude/settings.local.json` 確認）。
> 對「只污染最新 commit」的情境，amend 是最小侵入手術。`filter-repo` 是給污染散落在多個歷史 commit 的情境用。
>
> **Warning**：第 4 步的 `push --force-with-lease` 會改寫 remote 歷史。如果其他人 / 機器在這個 branch 上 work，他們的本地 history 會跟 remote 衝突。
> 你目前只有自己一台機器在用 → 安全。

## Step 1: 先把 `.claude/` 加到 `.gitignore`（避免之後再 commit 進來）

```bash
cd /Users/shirley/arealclimber/brainwave

# 確認 .gitignore 還沒有
grep -n "^\.claude" .gitignore 2>/dev/null

# 沒有就追加
echo "" >> .gitignore
echo "# Claude Code local settings — never commit" >> .gitignore
echo ".claude/" >> .gitignore
```

## Step 2: 從 git index 移除（檔案保留在磁碟上，Claude Code 繼續能用）

```bash
git rm --cached .claude/settings.local.json
# 如果整個 .claude/ 都不該被追蹤，用：
# git rm -r --cached .claude/
```

## Step 3: Amend 進 HEAD commit（保留原 commit message）

```bash
git add .gitignore
git commit --amend --no-edit
```

驗證 commit 內容已乾淨：

```bash
git show --stat HEAD
# 應該看到 .gitignore 取代了 .claude/settings.local.json

git log --all --full-history -- .claude/settings.local.json
# 應該完全沒輸出 → history 已清乾淨
```

## Step 4: Force push 到 origin（已被污染的 remote）

```bash
git push --force-with-lease origin feature/shirley-customize
```

`--force-with-lease` 比 `--force` 安全：如果 remote 有你不知道的新 commit（別人剛 push），會擋下來。

## Step 5: 正常 push 到 deploy（這個 remote 從沒收到污染 commit）

```bash
git push deploy feature/shirley-customize
```

不用 force，因為 `8165b18` 從未到過 deploy。

## Step 6: 驗收

```bash
# 兩個 remote 的歷史都應該完全找不到這檔
git fetch --all
for remote in origin deploy; do
  echo "=== $remote ==="
  git log $remote/feature/shirley-customize --all --full-history -- .claude/settings.local.json
done
# 兩個都應該無輸出
```

---

## 如果以後又有 commit 不小心碰到 `.claude/`（多 commit 情境）

那時 amend 不適用，改用 `git filter-repo`：

```bash
brew install git-filter-repo

# 備份！filter-repo 會直接改寫本地歷史
git clone --mirror . ../brainwave.git.backup

git filter-repo --path .claude/settings.local.json --invert-paths
# 或整個資料夾：
# git filter-repo --path .claude/ --invert-paths

# filter-repo 為安全會把 remote 拿掉，要重設
git remote add origin github-personal:arealclimber/brainwave.git
git remote add deploy github-personal:iunhsa/brainwave-private.git

git push --force-with-lease origin feature/shirley-customize
git push --force-with-lease deploy feature/shirley-customize
```

---

## 一鍵 copy（合併步驟 1–5）

```bash
cd /Users/shirley/arealclimber/brainwave && \
grep -q "^\.claude" .gitignore || printf "\n# Claude Code local settings\n.claude/\n" >> .gitignore && \
git rm --cached .claude/settings.local.json && \
git add .gitignore && \
git commit --amend --no-edit && \
git show --stat HEAD && \
echo "==> ready to force-push; review above first, then run:" && \
echo "git push --force-with-lease origin feature/shirley-customize" && \
echo "git push deploy feature/shirley-customize"
```

我故意把 force-push 留在最後一手動，讓你看完 amend 結果再按 Enter。
