import "./styles/index.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import { applyThemePreference, readThemePreference } from "./lib/theme";

// Apply a saved Light/Dark override before the first render (System needs no script).
applyThemePreference(readThemePreference());

const container = document.getElementById("root");
if (!container) throw new Error("Missing #root element");

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
