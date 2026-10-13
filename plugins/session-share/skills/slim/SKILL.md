---
description: 共有先に送る会話のコピーから、フックの出力や画像を削って容量を減らす設定を確認・変更する
argument-hint: "[hooks|images] [on|off]"
allowed-tools: Bash(bash:*)
disable-model-invocation: true
---
!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" slim $ARGUMENTS 2>&1 || true`

結果をユーザーの言語で伝える。
- hooks (既定オン): フックが標準出力に返した内容を 500 文字に切り詰める。`claude --resume` には使われない。
- images (既定オフ): 会話に貼った画像やスクリーンショットを「画像を省略」という文字に置き換える。再開した会話では Claude がその画像を見られなくなる。
削るのは共有先のコピーだけで、このデバイスの会話は書き換えない。ただし、別のデバイスから取り込んだ会話は削った版になる。
設定は共有先に保存され、全デバイスに効く。変更した場合は、次の `/session-share:push` で既存の会話も送り直されることを添える。
