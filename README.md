# Music_Recommender_v2
Based on the Music Recommender a better version with a new back- and frontend.

## Setup

### Prerequisites
- Python 3.10+
- Node.js 18+ (includes `npm`)
- PostgreSQL

### Backend
```bash
cd backend
pip install -r requirements.txt
```

### Frontend
```bash
cd frontend
npm install   # downloads node_modules — required before the project works in VSCode or browser
npm run dev   # starts dev server at http://localhost:5173
```

> `node_modules/` is gitignored. Run `npm install` once after cloning.


### Datenbank
wenn man noch gar keine hat, den befehl ausführen:
```bash
docker exec -it music_recommender_v2-backend-1 alembic upgrade head
```

#### pg admin

username:
admin@admin.com 
pw:
admin
