# Raccourcisseur d'URL — pipeline cloud complet

Projet personnel construit pour démontrer une chaîne de mise en production
complète, pas seulement une application. L'application elle-même (un
raccourcisseur d'URL, 3 routes) est volontairement simple : tout l'intérêt
du projet est dans ce qui l'entoure.

## Ce que ça couvre

- **Conteneurisation** — `Dockerfile` multi-stage, utilisateur non-root, image allégée
- **Orchestration** — manifestes Kubernetes (Deployment 2 réplicas + Service, health checks)
- **CI/CD** — GitHub Actions : tests automatiques → build de l'image → publication sur GitHub Container Registry à chaque push
- **Supervision** — Prometheus (scraping des métriques) + Grafana (visualisation), via Docker Compose

## Architecture

```
                 ┌─────────────┐
   push  ──────▶ │ GitHub       │
                 │ Actions      │──▶ test ──▶ build image ──▶ push (ghcr.io)
                 └─────────────┘
                                                     │
                                                     ▼
                 ┌──────────────────────────────────────────┐
                 │  Cluster Kubernetes (local — kind/minikube)│
                 │  ┌────────────┐  ┌────────────┐            │
                 │  │ Pod app #1 │  │ Pod app #2 │  Service    │
                 │  └────────────┘  └────────────┘  (NodePort) │
                 └──────────────────────────────────────────┘

                 ┌──────────────────────────────────────────┐
                 │  Docker Compose (supervision locale)       │
                 │  app ──▶ Prometheus (scrape /metrics) ──▶ Grafana │
                 └──────────────────────────────────────────┘
```

## Tester l'application seule (sans Docker)

```bash
cd app
pip install -r requirements.txt
uvicorn main:app --reload
```
- `POST /shorten` avec `{"url": "https://example.com"}` → renvoie un code
- `GET /{code}` → redirige vers l'URL d'origine
- `GET /stats/{code}` → nombre de clics
- `GET /metrics` → métriques au format Prometheus
- `GET /health` → utilisé par Kubernetes

## Construire et lancer l'image Docker

```bash
docker build -t url-shortener:local .
docker run -p 8000:8000 url-shortener:local
```

## Déployer sur un cluster Kubernetes local

Nécessite [kind](https://kind.sigs.k8s.io/) ou [minikube](https://minikube.sigs.k8s.io/) (gratuits) :

```bash
kind create cluster
kind load docker-image url-shortener:local
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl get pods    # vérifier que les 2 réplicas sont "Running"
```

Accès à l'app (avec kind, redirection de port nécessaire) :
```bash
kubectl port-forward service/url-shortener 8000:8000
```

## Lancer la supervision (Prometheus + Grafana)

```bash
docker compose up
```
- Prometheus : http://localhost:9090
- Grafana : http://localhost:3000 (identifiants : `admin` / `admin`)

Dans Grafana, ajouter Prometheus (`http://prometheus:9090`) comme source de
données, puis créer un dashboard sur `http_requests_total` ou
`http_request_duration_seconds`.

## Le pipeline CI/CD

À chaque `push` sur `main`, `.github/workflows/ci-cd.yaml` :
1. Installe les dépendances et lance l'app
2. Teste le parcours complet (raccourcir → rediriger → vérifier le code 307)
3. Si les tests passent : construit l'image Docker et la publie sur
   `ghcr.io/<ton-compte>/cloud-devops-project`

## Testé de bout en bout

Chaque brique de ce projet a été réellement exécutée, pas seulement écrite :

- **Docker** : image construite et lancée en conteneur, les 4 routes de l'app vérifiées (`/health`, `/shorten`, redirection, `/stats`), ainsi que l'exposition des métriques Prometheus.
- **Docker Compose** : stack complète (app + Prometheus + Grafana) démarrée ensemble ; cible Prometheus confirmée `UP` ; dashboard Grafana créé avec un graphique sur des métriques réelles (`rate(http_requests_total[1m])`).
- **Kubernetes** (cluster local via `kind`) : déploiement à 2 réplicas, les deux passés à `1/1 Running`, accès à l'app confirmé à travers le `Service` Kubernetes (`kubectl port-forward`).

Deux bugs réels ont été trouvés et corrigés au cours de ces tests (pas seulement de la théorie) :

1. **Permissions du conteneur** — l'utilisateur non-root (`appuser`) n'avait pas les droits d'écriture sur `/app`, donc SQLite ne pouvait pas créer son fichier de base au démarrage (`unable to open database file`). Corrigé en ajoutant `RUN chown -R appuser:appuser /app` dans le `Dockerfile`, avant de basculer sur l'utilisateur non-root.
2. **Image inexistante en local** — `k8s/deployment.yaml` référençait `ghcr.io/.../cloud-devops-project:latest`, une image qui n'existe que sur le registre distant (une fois la CI/CD exécutée). En local, Kubernetes essayait de la télécharger et échouait (`ErrImagePull`, 403 Forbidden). Corrigé en pointant vers l'image chargée localement (`image: url-shortener:local`) avec `imagePullPolicy: Never`, pour forcer Kubernetes à utiliser uniquement l'image présente sur le nœud.

## Limites assumées

- Le fichier `k8s/deployment.yaml` pointe actuellement vers l'image locale
  (`url-shortener:local`) pour permettre les tests avec `kind`. Pour un
  déploiement sur un vrai cluster cloud, il faudrait remettre l'image du
  registre (`ghcr.io/...`) une fois celle-ci publiée par la CI/CD.



- Le déploiement sur le cluster Kubernetes n'est **pas automatisé** depuis
  GitHub Actions : le cluster est local (kind/minikube), donc un runner
  GitHub hébergé ne peut pas s'y connecter. En entreprise, cette dernière
  étape se ferait vers un vrai cluster cloud (EKS/GKE/AKS) avec des
  identifiants stockés en secret. Ici, le déploiement se fait manuellement
  via `kubectl apply` après avoir récupéré la nouvelle image.
- SQLite comme stockage : suffisant pour la démonstration, mais ne
  supporterait pas plusieurs réplicas en écriture concurrente en production
  (il faudrait une vraie base, Postgres par exemple).
- Pas de HTTPS/domaine réel : usage local uniquement.

## Structure du repo

```
├── app/
│   ├── main.py
│   └── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── k8s/
│   ├── deployment.yaml
│   └── service.yaml
├── monitoring/
│   └── prometheus.yml
├── .github/workflows/ci-cd.yaml
└── .gitignore
```
