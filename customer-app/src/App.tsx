import { NavLink, Route, Routes } from "react-router-dom";
import { CustomerPicker } from "./components/CustomerPicker";
import { CustomerProvider } from "./CustomerContext";
import Overview from "./routes/Overview";

// The Customer overview is built; Your paths arrives with the paths story.
export default function App() {
  return (
    <CustomerProvider>
      <header className="topbar">
        <strong>Crossroads</strong>
        <nav>
          <NavLink to="/" end>
            Customer
          </NavLink>
          <NavLink to="/paths">Your paths</NavLink>
        </nav>
        <CustomerPicker />
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/paths" element={<p>Your paths is built in the next phase.</p>} />
        </Routes>
      </main>
    </CustomerProvider>
  );
}
