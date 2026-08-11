import { NavLink } from "react-router-dom";

function AxisMark() {
  return (
    <svg className="axis" viewBox="0 0 32 32" aria-hidden="true">
      <line className="z" x1="16" y1="16" x2="6" y2="24" />
      <line className="y" x1="16" y1="16" x2="16" y2="4" />
      <line className="x" x1="16" y1="16" x2="28" y2="20" />
    </svg>
  );
}

export default function Header() {
  return (
    <header className="bar">
      <NavLink to="/" className="ident">
        <AxisMark />
        <div>
          <div className="part">LSM6DSOX</div>
          <div className="sub">6-axis IMU · datasheet support agent</div>
        </div>
      </NavLink>
      <nav className="nav">
        <NavLink to="/" end className="navlink">
          Chat
        </NavLink>
        <NavLink to="/about" className="navlink">
          How it works
        </NavLink>
      </nav>
    </header>
  );
}
