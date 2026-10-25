## Deploying
- Deploy only by running ./deploy.sh.
- Check logs with: ssh crossroads 'cd /opt/crossroads && docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=50 customer-api internal-api caddy'
- Never read, print, copy or edit /opt/crossroads/.env; ask me if a secret is missing.
- On the server, only run docker compose commands in /opt/crossroads. No apt, no rm outside /opt/crossroads, no firewall or user changes.
