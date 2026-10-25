import { NavLink, Route, Routes } from "react-router-dom";
import { LogoSlot } from "./brand/LogoSlot";
import { CustomerPicker } from "./components/CustomerPicker";
import { CustomerProvider } from "./CustomerContext";
import Landing from "./routes/Landing";
import Overview from "./routes/Overview";
import Paths from "./routes/Paths";

// The customer app: a role landing page at "/", then the Overview and Your paths screens with the Demo
// customer picker above both. The landing page is a bare split screen: no header, no data requests.
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/*" element={<CustomerApp />} />
    </Routes>
  );
}

function CustomerApp() {
  return (
    <CustomerProvider>
      <header className="topbar">
        <LogoSlot />
        <strong className="brand">Crossroads</strong>
        <nav>
          <NavLink to="/overview" end>
            Customer
          </NavLink>
          <NavLink to="/paths">Your paths</NavLink>
        </nav>
        <CustomerPicker />
      </header>
      <main>
        <Routes>
          <Route path="/overview" element={<Overview />} />
          <Route path="/paths" element={<Paths />} />
        </Routes>
      </main>
    </CustomerProvider>
  );
}
