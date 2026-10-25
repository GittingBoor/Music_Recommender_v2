# Music_Recommender_v2
The Music Recommender v2 is a university project based on an earlier version of a music recommender from our tutor.
Using different APIs and machine learning models, we extract metadata and other features of songs.
Through the frontend, you can then search for songs with certain characteristics such as danceability, mood, and many more.

## Setup

### Prerequisites
- [Python 3.10+](https://www.python.org/downloads/)
- [Node.js 18+](https://nodejs.org/)
- [PostgreSQL](https://www.postgresql.org/download/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)

### Docker 
Start your Docker software before running the following command:
```bash
docker-compose up --build -d
```

### Database
If you don't have a database yet, run the following command:
```bash
docker exec -it music_recommender_v2-backend-1 alembic upgrade head
```

#### pgAdmin

Username: admin@admin.com

Password: admin

## How to use

### Frontend
```
npm run dev
```

### Backend

#### How to get inside the Docker
Execute the following command in your terminal to enter the Docker container:
```bash
docker exec -it music_recommender_v2-backend-1 bash
```

#### How to get Songs through the Pipeline
If you want to see a .json file for testing:
```
python -m src.analysis.pipeline "test_audio/filename.mp3" --save
```

If you want all songs from a specific folder to be added to your database, or just one song:
```
python -m src.analysis.pipeline /app/test_audio/ --db

python -m src.analysis.pipeline /app/test_audio/"filename.mp3" --db
```

## Local Addresses

| Service  | Address               |
|----------|-----------------------|
| Frontend | http://localhost:5173 |
| Backend  | http://localhost:8000/docs#/ |
| Database | localhost:5432        |
| pgAdmin  | http://localhost:5050 |

## Accounts and Spotify import

Personal accounts are optional (login top right); the shared site password still guards
the production site. A connected Spotify account can import its own and collaborative
playlists with one click: every track is searched on YouTube, downloaded and only saved
when AcoustID does not identify the audio as a different song.

Backend settings (`backend/.env` locally, `.env.prod` on the mini-PC):

| Variable | Purpose |
|---|---|
| `SESSION_SECRET` | Signs login cookies (already required for the site password). Local dev sets one in `docker-compose.yml`. |
| `PUBLIC_BASE_URL` | Base of password reset links, e.g. `https://music.gittingboor.de` |
| `BREVO_API_KEY`, `MAIL_FROM`, `MAIL_FROM_NAME` | Brevo transactional mail; without them reset links are only logged |
| `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` | The Spotify app (also used for metadata) |
| `SPOTIFY_REDIRECT_URI` | `https://music.gittingboor.de/api/spotify/callback` in prod; default is the local `http://127.0.0.1:5173/api/spotify/callback` |

Deploying this feature: run `alembic upgrade head` before (re)starting the backend; the
import's restart recovery needs the new tables (without them it only logs an error).

Spotify dashboard: both redirect URIs above must be registered, and every user's Spotify
e-mail must be added under *User Management* (development mode allows 5 users). Open the
local frontend via `http://127.0.0.1:5173` (not `localhost`) so the OAuth redirect matches.
