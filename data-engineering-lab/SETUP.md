Server Setup (Hetzner)

Goal: get JupyterLab running quickly on a fresh Ubuntu server, with HTTPS.

Assumptions
- Ubuntu 22.04+ with SSH access
- You will clone this repo to the server
- DNS/firewall allows inbound TCP on JUPYTER_PORT (default 8888)
- DNS/firewall allows inbound TCP on 80/443 for HTTPS

1) Install Docker and Compose
   - sudo apt-get update
   - sudo apt-get install -y ca-certificates curl gnupg
   - sudo install -m 0755 -d /etc/apt/keyrings
   - curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
   - sudo chmod a+r /etc/apt/keyrings/docker.gpg
   - echo \
     "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
     $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
     sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   - sudo apt-get update
   - sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

2) Clone the repo
   - git clone <your-repo-url>
   - cd GeoDataAnalytics

3) Configure Jupyter
   - cp delab/jupyter/.env.example delab/jupyter/.env
   - Edit .env to set:
     - JUPYTER_TOKEN (strong token)
     - JUPYTER_PORT if you want something other than 8888
     - OMP_NUM_THREADS/OPENBLAS_NUM_THREADS/MKL_NUM_THREADS for your CPU

4) Start JupyterLab
   - cd delab/jupyter
   - docker compose up -d

5) Access JupyterLab
   - Open: http://<server-ip>:<JUPYTER_PORT>/

Notes
- If you need HTTPS, put Caddy/Nginx in front of Jupyter and set JUPYTER_BASE_URL.
- Keep .env files private; only commit .env.example templates.

Fast path (recommended)
1) On the server, run:
   - REPO_URL=<your-repo-url> DOMAIN=<your-domain> EMAIL=<your-email> bash delab/bootstrap.sh
2) Open: https://<your-domain>/

Using host Nginx
- If Nginx is already installed on the host, run:
  - REPO_URL=<your-repo-url> DOMAIN=<your-domain> EMAIL=<your-email> USE_HOST_NGINX=true bash delab/bootstrap.sh
