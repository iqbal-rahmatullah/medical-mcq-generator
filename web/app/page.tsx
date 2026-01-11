import Navbar from "../components/Navbar";

export default function HomePage() {
  return (
    <div className="app-shell">
      <Navbar />
      <main className="page-body">
        <div className="container">
          <section className="page-placeholder">
            <p>Konten utama akan ditambahkan setelah navbar.</p>
          </section>
        </div>
      </main>
    </div>
  );
}
