import { NavLink, Route, Routes } from "react-router-dom";

// Scaffold only: the Customer overview and Your paths screens arrive with the customer stories.
export default function App() {
  return (
    <>
      <header>
        <strong>Crossroads</strong>
        <nav>
          <NavLink to="/" end>
            Customer
          </NavLink>{" "}
          <NavLink to="/paths">Your paths</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<p>The customer overview is built in the next phase.</p>} />
          <Route path="/paths" element={<p>Your paths is built in the next phase.</p>} />
        </Routes>
      </main>
    </>
  );
}
