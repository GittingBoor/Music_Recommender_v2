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
| Backend  | http://localhost:8000 |
| Database | localhost:5432        |
