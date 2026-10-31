#!/usr/bin/env bash
# Cortes curtos a partir das mesmas gravações de out/raw.
#
#   ./compose-curto.sh            # 5 min  → out/tracepilot-demo-5min.mp4
#   ./compose-curto.sh relampago  # 2m30   → out/tracepilot-demo-2min30.mp4
#
# Cada linha é: cena|onde começa|segundos aproveitados|aceleração.
# O que é rolagem acelera mais; o que é leitura (causa, prompt, erro na tela)
# acelera menos.
set -euo pipefail
cd "$(dirname "$0")"
RAW=out/raw
W=1600; H=900; FPS=30
PERFIL="${1:-curto}"

if [ "$PERFIL" = "relampago" ]; then
  OUT=out/tracepilot-demo-2min30.mp4
  # Versão de 2m30: o enredo é a solução funcionando. A apresentação da loja e
  # a configuração entram só como contexto; o peso fica na falha, na
  # investigação e na resposta.
  CORTES="
01-landing|2|12|2.0
02-loja|8|16|2.0
03-configuracao|6|22|2.2
04-painel|6|24|2.0
05-falha|10|20|2.0
05b-loja-erro|4|21|1.8
06-investigar|6|21|1.8
07-resultado|0|36|1.5
08-comparacao|6|28|1.8
09-cenarios|30|17|2.2
09b-loja-cupom|9|7|1.3
10-reacao|8|20|2.0
11-fechamento|10|27|1.7
"
else
  OUT=out/tracepilot-demo-5min.mp4
  CORTES="
01-landing|0|40|1.6
02-loja|0|46|1.7
03-configuracao|0|60|1.9
04-painel|0|48|1.8
05-falha|0|38|1.8
05b-loja-erro|0|24|1.6
06-investigar|0|28|1.8
07-resultado|0|38|1.5
08-comparacao|0|38|1.7
09-cenarios|0|50|1.9
09b-loja-cupom|0|15|1.5
10-reacao|0|34|1.8
11-fechamento|10|44|1.7
"
fi

# Tela dividida da comparação (mesma montagem da versão longa).
L="$RAW/08a-openobserve.webm"; R="$RAW/08b-tracepilot.webm"
if [ -f "$L" ] && [ -f "$R" ] && [ ! -f "$RAW/08-comparacao.mp4" ]; then
  ffmpeg -nostdin -v error -y -i "$L" -i "$R" -filter_complex \
    "[0:v]scale=800:900,setsar=1[l];[1:v]scale=800:900,setsar=1[r];\
     [l][r]hstack=inputs=2,drawbox=x=798:y=0:w=4:h=900:color=0x0b0e14@0.9:t=fill[v]" \
    -map "[v]" -r $FPS -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p "$RAW/08-comparacao.mp4"
fi

TMP="out/$PERFIL"
rm -rf "$TMP" && mkdir -p "$TMP"
i=0
while IFS='|' read -r nome inicio take fator; do
  [ -n "${nome:-}" ] || continue
  src=""
  for ext in webm mp4; do [ -f "$RAW/$nome.$ext" ] && src="$RAW/$nome.$ext"; done
  [ -n "$src" ] || { echo "· (falta $nome)"; continue; }
  i=$((i+1))
  dst=$(printf '%s/%03d.mp4' "$TMP" "$i")
  printf '· %-18s %ss a partir de %ss ÷ %s\n' "$nome" "$take" "$inicio" "$fator"
  ffmpeg -nostdin -v error -y -ss "$inicio" -t "$take" -i "$src" \
    -vf "scale=$W:$H:force_original_aspect_ratio=decrease,pad=$W:$H:(ow-iw)/2:(oh-ih)/2:color=0x0b0e14,setpts=PTS/$fator,fps=$FPS,setsar=1" \
    -an -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p "$dst"
done <<< "$CORTES"

: > "$TMP/lista.txt"
for n in "$TMP"/*.mp4; do echo "file '$(basename "$n")'" >> "$TMP/lista.txt"; done
ffmpeg -nostdin -v error -y -f concat -safe 0 -i "$TMP/lista.txt" -c copy "$OUT"
rm -rf "$TMP"
echo
echo "Pronto: $OUT"
ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "$OUT" | awk '{printf "Duração: %d min %02d s\n", $1/60, $1%60}'
