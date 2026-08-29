# Dev Charter (開発憲章)

> **このファイルは正本（日本語版）です。**
> 英語版（参照）は [README.md](README.md) を参照してください。

[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](LICENSE)
[![check-charter CI](https://github.com/y-marui/dev-charter/actions/workflows/check-charter.yml/badge.svg)](https://github.com/y-marui/dev-charter/actions/workflows/check-charter.yml)

AI支援ソフトウェアプロジェクトのための共有開発憲章。

このリポジトリは、プロジェクト横断的に使用される共通の哲学、アーキテクチャ原則、
および開発ルールを定義します。

## Documents

憲章ドキュメントの一覧とトピック別の参照先は、正本である [CHARTER_INDEX.md](CHARTER_INDEX.md) を参照してください。

## How to Use

1. `git subtree` で `docs/dev-charter/` に取り込む
2. AI に dev-charter を読ませ、プロジェクトルートに `AI_CONTEXT.md` と AI ツール設定ファイルを生成させる
3. 憲章が更新されたら `git subtree pull` 後、AI にコンテキストファイルを追従させる

構成仕様は [AI_TOOL_SETUP.md](AI_TOOL_SETUP.md) を参照。

## Quick Install

プロジェクトのルートで実行してください：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/y-marui/dev-charter/main/scripts/install.sh)
```

Windows PowerShell の場合：

```powershell
irm https://raw.githubusercontent.com/y-marui/dev-charter/main/scripts/install.ps1 | iex
```

スクリプトが git subtree のセットアップを自動化し、Claude Code が利用可能であれば
初回セットアップ（INSTALL_CHECKLIST）の起動まで案内します。

> **Note:** インストール先やブランチを変更する場合は環境変数で指定できます：
> `CHARTER_PREFIX=path/to/charter bash <(curl -fsSL .../install.sh)`

## Install (git subtree)

```
git remote add dev-charter https://github.com/y-marui/dev-charter
git fetch dev-charter
git subtree add --prefix=docs/dev-charter dev-charter main --squash
```

インストール後、以下のプロンプトを AI ツールに貼り付けてください：

```
docs/dev-charter/INSTALL_CHECKLIST.md を実行して
```

## Update

`dev-charter` リモートが未設定の場合（プロジェクトを clone した直後など）は先に追加する：

```
git remote add dev-charter https://github.com/y-marui/dev-charter
git subtree pull --prefix=docs/dev-charter dev-charter main --squash
```

> **Note（[lite](#lite-version) を導入している場合）:** 上記の `main` を `lite` に
> 置き換えること。取り違えると full/lite が入れ替わってしまう（[Makefile
> Helper](#makefile-helper) は導入済みのブランチを自動判定するため、この
> 取り違えが起きない）。

> **Note（テンプレートリポジトリから作成したプロジェクト）:**
> GitHub テンプレートはファイルのみコピーし git 履歴を引き継がないため、`git subtree pull` は失敗します。
> `check-charter.yml` ワークフローがこのケースを自動検出して対処します。
> 手動で更新する場合は `git subtree pull` の代わりに以下を実行してください：
> ```bash
> git remote add dev-charter https://github.com/y-marui/dev-charter || true
> git fetch dev-charter
> SPLIT=$(git rev-parse dev-charter/main)
> rm -rf docs/dev-charter/
> mkdir -p docs/dev-charter/
> git archive dev-charter/main | tar -x -C docs/dev-charter/
> git add docs/dev-charter/
> git commit -m "Squashed 'docs/dev-charter/' content from commit ${SPLIT}
>
> git-subtree-dir: docs/dev-charter
> git-subtree-split: ${SPLIT}"
> ```

更新後、以下のプロンプトを AI ツールに貼り付けてください：

```
docs/dev-charter/UPDATE_CHECKLIST.md を実行して
```

## Lite Version

`main`（このリポジトリ全体）は、Python 開発環境・UI デザイン・収益化方針など
ソフトウェアプロジェクト固有の内容を多く含む。ドキュメントのみのリポジトリ
（設定ファイル集、ノートアーカイブ等）ではそのまま導入すると過剰になる場合、
`lite` ブランチを使うと、プロジェクト種別を問わず普遍的に価値がある部分
（AI コンテキストの整備、GitHub Issues/Projects でのタスク管理、シークレット
管理等）だけを取り込める。収録ファイルの分類は
[scripts/lite-manifest.txt](scripts/lite-manifest.txt) を参照。

Quick Install（`CHARTER_BRANCH=lite` を指定）：

```bash
CHARTER_BRANCH=lite bash <(curl -fsSL https://raw.githubusercontent.com/y-marui/dev-charter/main/scripts/install.sh)
```

git subtree で直接導入する場合：

```
git remote add dev-charter https://github.com/y-marui/dev-charter
git fetch dev-charter
git subtree add --prefix=docs/dev-charter dev-charter lite --squash
```

Version Check (CI) を使う場合は `branch: lite` を指定する：

```yaml
    uses: y-marui/dev-charter/.github/workflows/check-charter.yml@main
    with:
      branch: lite
```

lite の `VERSION` は full とは独立して管理され、収録ファイルの内容が実際に
変わったときだけ更新される（無関係な full 側の変更で更新PRが飛ばないようにするため）。

lite のみを導入した場合、この README・`INSTALL_CHECKLIST.md`・
`UPDATE_CHECKLIST.md` は含まれない。そのため `scripts/publish-lite-branch.sh`
が生成する lite 版 `CHARTER_INDEX.md` には、`git subtree pull` コマンドと
下記 Makefile Helper への案内を含む独自の "Updating" セクションを収録し、
full を導入していない採用先でも自己完結した更新手順を参照できるようにしている。

## Makefile Helper

`git subtree pull` は作業ツリーに未コミットの変更があると失敗するため、
実行前に自動で `git stash` し、完了後に `git stash pop` で戻す。

導入時に `main`（full）と `lite` のどちらを選んだかをこのターゲットが覚えている
必要はない。既存の `docs/dev-charter/CHARTER_INDEX.md` の内容（lite 版は
`scripts/publish-lite-branch.sh` が生成するため必ず `(lite)` を含む）から
毎回導入済みブランチを自動判定するため、`main`/`lite` を取り違えて更新して
しまう事故（full 導入なのに lite で上書き、またはその逆）を防げる。

```
.PHONY: update-charter
update-charter:
	git remote | grep -q '^dev-charter$$' || \
	  git remote add dev-charter https://github.com/y-marui/dev-charter
	git fetch dev-charter
	@BRANCH=main; \
	if [ -f docs/dev-charter/CHARTER_INDEX.md ] && grep -q '(lite)' docs/dev-charter/CHARTER_INDEX.md; then \
		BRANCH=lite; \
	fi; \
	echo "dev-charter branch: $$BRANCH"; \
	STASHED=0; \
	if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$$(git ls-files --others --exclude-standard)" ]; then \
		git stash push -u -m "update-charter"; \
		STASHED=1; \
	fi; \
	git subtree pull --prefix=docs/dev-charter dev-charter $$BRANCH --squash; \
	if [ "$$STASHED" = "1" ]; then git stash pop; fi
```

## Version Check (CI)

`.github/workflows/dev-charter-check.yml` をプロジェクトに追加すると、
PR作成や main への push をきっかけに最新バージョンを確認し、古い場合は update PR を作成します
（直近7日以内に成功したチェックがあればスキップするため、活発な repo でも毎回チェックが走ることはありません）。

```yaml
name: Dev Charter

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  check:
    name: Check
    if: github.actor != 'dependabot[bot]' && (github.event_name != 'pull_request' || github.event.pull_request.draft == false)
    uses: y-marui/dev-charter/.github/workflows/check-charter.yml@main
    permissions:
      contents: write
      pull-requests: write
      actions: read

  gate:
    name: Dev Charter
    needs: [check]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Verify dev-charter check did not fail
        run: |
          result="${{ needs.check.result }}"
          if [ "$result" = "failure" ] || [ "$result" = "cancelled" ]; then
            echo "::error::dev-charter check did not succeed (got: $result)"
            exit 1
          fi
          echo "check result: $result (skipped is fine — draft or dependabot)"
```

> **Note:** dependabot が作成した PR や draft PR では `check` 自体がスキップされます
> （後述）。`gate` はその場合も `skipped` を正常として扱い、必ず `Dev Charter`（ワークフロー
> 自身の `name:` と同じ値）を報告します。Branch Protection（Ruleset）に必須ステータス
> チェックとして登録するのは `Check / check` ではなく `Dev Charter` です（[CI_POLICY.md
> の Ruleset 節](topics/CI_POLICY.md#branch-protection-ruleset)参照）。
> `check` job だけを直接必須チェックに登録すると、skip 時に `Check / check` という
> コンテキスト自体が一切報告されず、PR が `Expected — Waiting for status to be reported`
> のまま永久にブロックされます。

> **Note:** dependabot が作成した PR ではスキップされます（依存関係更新だけが動いている間はチェック不要という判断）。
> repo が完全に静止している間はチェックが走らないため、活動に関わらず定期的に確認したい場合は
> 上記に加えて低頻度の `schedule`（例：月1回）を併用してください。

> **Note:** Draft PR ではスキップされます（draft はそもそもマージできないため、チェックが
> 未報告のままでもリスクがない）。`on.pull_request.types` の `ready_for_review` により、
> draft を解除した際は改めて実行されます。

> **Note:** Branch Protection で direct push が禁止されている場合は、
> GitHub Actions bot の bypass rule を追加してください
> （Settings > Rules > Rulesets > Bypass list > GitHub Actions）。

## Badge for Adopting Projects

プロジェクトの README にこのバッジを追加すると、dev-charter の更新状態を可視化できます。

### Workflow Status Badge

dev-charter が最新かどうかを表示します。

```markdown
[![Charter Check](https://github.com/{owner}/{repo}/actions/workflows/dev-charter-check.yml/badge.svg)](https://github.com/{owner}/{repo}/actions/workflows/dev-charter-check.yml)
```

`{owner}` と `{repo}` を自分のリポジトリのオーナー名・リポジトリ名に置き換えてください。

| 状態 | Status Badge |
|---|---|
| 未導入 / CI 未設定 | 赤（VERSION not found） |
| 導入済み・最新 | 緑 |
| 導入済み・更新必要 | 赤 |

---

*この文書には英語版 [README.md](README.md) があります。編集時は同一コミットで更新してください。*
