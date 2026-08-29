#!/usr/bin/env bash
# CHARTER_INDEX.md に列挙された全ファイルが scripts/lite-manifest.txt の
# include/exclude いずれかに分類済みかを機械的に検証する。
#
# 新規ドキュメントを CHARTER_INDEX.md に追記した際、lite 版（git branch: lite）
# に含めるかどうかの判断が漏れたまま気づかれずに残ることを防ぐ。
set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel)
INDEX="${REPO_ROOT}/CHARTER_INDEX.md"
MANIFEST="${REPO_ROOT}/scripts/lite-manifest.txt"

trim() {
  sed -e 's/#.*//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | grep -v '^$'
}

index_files=$(grep -oE '`[A-Za-z0-9_./-]+\.md`' "$INDEX" | tr -d '`' | sort -u)

include_files=$(awk '/^\[include\]/{f=1;next} /^\[exclude\]/{f=0} f' "$MANIFEST" | trim | sort -u)
exclude_files=$(awk '/^\[exclude\]/{f=1;next} /^\[include\]/{f=0} f' "$MANIFEST" | trim | sort -u)

status=0

duplicates=$(comm -12 <(echo "$include_files") <(echo "$exclude_files"))
if [ -n "$duplicates" ]; then
  echo "error: 以下のファイルが lite-manifest.txt の [include]/[exclude] 両方に登録されています:"
  echo "$duplicates" | sed 's/^/  - /'
  status=1
fi

manifest_files=$(printf '%s\n%s\n' "$include_files" "$exclude_files" | grep -v '^$' | sort -u)

unclassified=$(comm -23 <(echo "$index_files") <(echo "$manifest_files"))
if [ -n "$unclassified" ]; then
  echo "error: CHARTER_INDEX.md にあるが scripts/lite-manifest.txt で未分類のファイルがあります:"
  echo "$unclassified" | sed 's/^/  - /'
  echo "  scripts/lite-manifest.txt の [include] か [exclude] に追記してください。"
  status=1
fi

stale=$(comm -13 <(echo "$index_files") <(echo "$manifest_files"))
if [ -n "$stale" ]; then
  echo "error: scripts/lite-manifest.txt にあるが CHARTER_INDEX.md に存在しないファイルがあります:"
  echo "$stale" | sed 's/^/  - /'
  echo "  scripts/lite-manifest.txt から削除するか、CHARTER_INDEX.md を確認してください。"
  status=1
fi

exit "$status"
