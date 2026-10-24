import { Route, Routes } from "react-router-dom";

// Scaffold only: sign-in and the portfolio arrive with the business-view story. This app has no
// link to the customer app (FR-023).
export default function App() {
  return (
    <>
      <header>
        <strong>Crossroads Internal</strong>
        <div>Toyota Financial Services · staff only</div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<p>The portfolio view is built in a later phase.</p>} />
          <Route path="/login" element={<p>Staff sign-in is built in a later phase.</p>} />
        </Routes>
      </main>
    </>
  );
}
