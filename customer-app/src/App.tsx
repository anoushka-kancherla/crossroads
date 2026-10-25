import { NavLink, Route, Routes } from "react-router-dom";
import { LogoSlot } from "./brand/LogoSlot";
import { CustomerPicker } from "./components/CustomerPicker";
import { CustomerProvider } from "./CustomerContext";
import Overview from "./routes/Overview";
import Paths from "./routes/Paths";

// The customer app: the Overview and Your paths screens, with the Demo customer picker above both.
export default function App() {
  return (
    <CustomerProvider>
      <header className="topbar">
        <LogoSlot />
        <strong className="brand">Crossroads</strong>
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
          <Route path="/paths" element={<Paths />} />
        </Routes>
      </main>
    </CustomerProvider>
  );
}
