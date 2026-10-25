import { Link } from "react-router-dom";
import { LogoSlot } from "../brand/LogoSlot";
import { staffUrl } from "../staffUrl";

// The front door: two halves, one for customers and one for staff. It shows no data, makes no request and
// remembers nothing. Staff leave this app for the dashboard's own address, where sign-in still applies.
export default function Landing() {
  const staff = staffUrl(window.location, import.meta.env.VITE_STAFF_URL);
  return (
    <main className="landing">
      <div className="landing-brand">
        <LogoSlot />
        <strong className="brand">Crossroads</strong>
      </div>
      <Link className="landing-half landing-customer" to="/overview">
        <h1>Are you a customer?</h1>
        <p>See your options and what each would cost you.</p>
      </Link>
      {staff ? (
        <a className="landing-half landing-staff" href={staff}>
          <h1>Are you a staff member?</h1>
          <p>Sign in to the Toyota Financial Services dashboard.</p>
        </a>
      ) : (
        <div className="landing-half landing-staff is-disabled" aria-disabled="true">
          <h1>Are you a staff member?</h1>
          <p>The staff address is not configured.</p>
        </div>
      )}
    </main>
  );
}
