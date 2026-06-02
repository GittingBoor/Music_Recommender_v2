import { useEffect, useState } from 'react';
import { fetchSongs } from './services/api';
import type { Song } from './types/song';
import { SongCard } from './components/SongCard';

export default function App() {
  const [songs, setSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSongs()
      .then(setSongs)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 px-6 py-4">
        <h1 className="text-xl font-bold tracking-tight">Music Recommender</h1>
        {!loading && !error && (
          <p className="text-sm text-gray-500 mt-0.5">{songs.length} songs</p>
        )}
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6">
        {loading && (
          <div className="text-gray-500 text-center py-16">Loading songs…</div>
        )}
        {error && (
          <div className="text-red-400 text-center py-16">Error: {error}</div>
        )}
        {!loading && !error && songs.length === 0 && (
          <div className="text-gray-500 text-center py-16">No songs in the database yet.</div>
        )}
        {!loading && !error && songs.length > 0 && (
          <div className="space-y-2">
            {songs.map(song => (
              <SongCard key={song.id} song={song} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
