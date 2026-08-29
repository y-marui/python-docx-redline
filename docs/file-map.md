# File Map

ファイルレベルの依存関係を記録するドキュメント。初回コード探索後に追記していく。

## 記載方法

各ファイルについて、主要な import 元・呼び出し元・呼び出し先を記録する。

```
src/project_name/
  __init__.py
    - exports: (公開シンボル)

  module_a.py
    - imports: module_b, module_c
    - used by: module_x
```

## ファイル依存マップ

<!-- 初回探索後にここへ追記する -->

```
src/project_name/
  __init__.py
    - (未記入)
```
