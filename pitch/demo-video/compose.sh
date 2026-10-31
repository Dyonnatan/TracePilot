#!/usr/bin/env bash
# Junta as cenas gravadas num vídeo só. A cena 8 (OpenObserve × TracePilot)
# vira tela dividida lado a lado antes de entrar na sequência.
set -euo pipefail
cd "$(dirname "$0")"
RAW=out/raw
OUT=out/tracepilot-demo.mp4
W=1600; H=900; FPS=30

[ -d "$RAW" ] || { echo "Não há gravações em $RAW. Rode: node record.js" >&2; exit 1; }

# --- tela dividida da comparação -------------------------------------------
L="$RAW/08a-openobserve.webm"; R="$RAW/08b-tracepilot.webm"
if [ -f "$L" ] && [ -f "$R" ]; then
  echo "· montando a tela dividida"
  ffmpeg -v error -y -i "$L" -i "$R" -filter_complex \
    "[0:v]scale=800:900,setsar=1[l];[1:v]scale=800:900,setsar=1[r];\
     [l][r]hstack=inputs=2,drawbox=x=798:y=0:w=4:h=900:color=0x0b0e14@0.9:t=fill[v]" \
    -map "[v]" -r $FPS -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
    "$RAW/08-comparacao.mp4"
fi

# --- normaliza cada cena ----------------------------------------------------
rm -rf out/norm && mkdir -p out/norm
i=0
for f in $(ls "$RAW" | grep -E '\.(webm|mp4)$' | grep -vE '^08[ab]-' | LC_ALL=C sort); do
  i=$((i+1))
  n=$(printf 'out/norm/%03d.mp4' "$i")
  echo "· $f"
  ffmpeg -v error -y -i "$RAW/$f" \
    -vf "scale=$W:$H:force_original_aspect_ratio=decrease,pad=$W:$H:(ow-iw)/2:(oh-ih)/2:color=0x0b0e14,fps=$FPS,setsar=1" \
    -an -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p "$n"
done
[ "$i" -gt 0 ] || { echo "Nenhuma cena para juntar." >&2; exit 1; }

# --- junta ------------------------------------------------------------------
: > out/lista.txt
for n in out/norm/*.mp4; do echo "file '$(basename "$n")'" >> out/lista.txt; done
( cd out/norm && cp ../lista.txt . )
ffmpeg -v error -y -f concat -safe 0 -i out/norm/lista.txt -c copy "$OUT"
echo
echo "Pronto: $OUT"
ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "$OUT" | awk '{printf "Duração: %d min %02d s\n", $1/60, $1%60}'
