#!/usr/bin/env bash
# このリポジトリに導入済みの dev-charter VERSION を、隣接する ../dev-charter
# チェックアウトの main または lite ブランチ（導入した方）と比較する。
#
# 想定するディレクトリ構成:
#   <parent>/dev-charter/     dev-charter のローカルクローン
#   <parent>/<this-repo>/     このリポジトリ
#
# - 隣接リポジトリの対象ブランチが導入済みより新しい -> block
#   （実行可能な差分が確定しているため: git subtree pull を実行する）
# - 隣接リポジトリの対象ブランチが導入済みより古い -> warning のみ
#   （隣接リポジトリ自体が fetch/pull されていないだけの可能性があるため）
# - 一致、またはどちらかの VERSION が取得できない -> 何も出力しない
#
# 隣接リポジトリの working tree ではなくローカル ref から VERSION を読むため、
# そちらで何のブランチがチェックアウトされているかに結果が左右されない。
# デフォルトの ref は、導入済み CHARTER_INDEX.md の `(lite)` マーカーから
# 自動判定する（README の Makefile helper・check-charter.yml と同じ方式）。
# これにより main 導入・lite 導入のそれぞれで正しいブランチと比較される。
# 必要であれば CHARTER_PREFIX / CHARTER_LOCAL_PATH / CHARTER_LOCAL_REF の
# 環境変数で上書きできる。
set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel)
PREFIX="${CHARTER_PREFIX:-docs/dev-charter}"
LOCAL_CHARTER="${CHARTER_LOCAL_PATH:-$(dirname "$REPO_ROOT")/dev-charter}"

DEFAULT_REF="main"
if [ -f "${REPO_ROOT}/${PREFIX}/CHARTER_INDEX.md" ] && grep -q '(lite)' "${REPO_ROOT}/${PREFIX}/CHARTER_INDEX.md"; then
  DEFAULT_REF="lite"
fi
LOCAL_REF="${CHARTER_LOCAL_REF:-$DEFAULT_REF}"

INSTALLED_VERSION_FILE="${REPO_ROOT}/${PREFIX}/VERSION"

[ -f "$INSTALLED_VERSION_FILE" ] || exit 0
[ -d "$LOCAL_CHARTER" ] || exit 0

INSTALLED=$(head -1 "$INSTALLED_VERSION_FILE")
LOCAL=$(git -C "$LOCAL_CHARTER" show "${LOCAL_REF}:VERSION" 2>/dev/null | head -1) || exit 0
[ -n "$LOCAL" ] || exit 0

if [ "$LOCAL" = "$INSTALLED" ]; then
  exit 0
fi

if [[ "$LOCAL" > "$INSTALLED" ]]; then
  echo "error: ${LOCAL_CHARTER} の ${LOCAL_REF} ブランチの VERSION (${LOCAL}) が ${PREFIX}/VERSION (${INSTALLED}) より新しいです。"
  echo "  1. git subtree pull で dev-charter を更新する"
  echo "  2. ${PREFIX}/UPDATE_CHECKLIST.md の手順を実行し、変更されたファイルの影響を確認・反映する（このコミットの前に行うこと。無視・後回しにしない）"
  echo "  3. 上記が完了してから、元のコミットをやり直す"
  exit 1
fi

echo "warning: ${LOCAL_CHARTER} の ${LOCAL_REF} ブランチの VERSION (${LOCAL}) は ${PREFIX}/VERSION (${INSTALLED}) より古いです。"
echo "  (${LOCAL_CHARTER} の ${LOCAL_REF} 自体が fetch/pull 済みでない可能性があるため、警告にとどめています)"
exit 0
