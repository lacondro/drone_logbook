import { NavLink, Outlet } from "react-router-dom";

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">✈</span>
          <div>
            <div className="brand-title">Drone Flight Logbook</div>
            <div className="brand-sub">PX4 · ArduPilot log archive</div>
          </div>
        </div>
        <nav className="topnav">
          <NavLink to="/" end>
            Flights
          </NavLink>
          <NavLink to="/vehicles">Aircrafts</NavLink>
          <NavLink to="/pilots">Pilots</NavLink>
        </nav>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
