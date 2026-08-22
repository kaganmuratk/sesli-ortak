#!/bin/bash
# Sesli Ortak — Claude Code Stop hook
#
# Bu dosyayi kendi projenin .claude/hooks/ klasorune kopyala, sonra
# .claude/settings.json'a soyle bagla:
#
#   "Stop": [{ "hooks": [{ "type": "command",
#     "command": "\"$CLAUDE_PROJECT_DIR/.claude/hooks/speak-if-voice.sh\"", "timeout": 5 }] }]
#
# Asagidaki SESLI_DIR, bu reponun (sesli-ortak) projenin kokunde dogrudan
# bir alt klasor oldugunu varsayar (orn. <proje>/sesli-ortak). Farkli bir
# yerdeyse yolu elle duzelt.
SESLI_DIR="$CLAUDE_PROJECT_DIR/sesli-ortak"

cat | nohup "$SESLI_DIR/.venv/bin/python3" "$SESLI_DIR/hook_konustur.py" \
  > "$SESLI_DIR/hook_konustur.log" 2>&1 &
disown

exit 0
