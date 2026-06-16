import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider, Navigate } from "react-router-dom";
import App from "./App.jsx";
import Logbook from "./pages/Logbook.jsx";
import Vehicles from "./pages/Vehicles.jsx";
import Pilots from "./pages/Pilots.jsx";
import "leaflet/dist/leaflet.css";
import "./styles.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Logbook /> },
      { path: "flights/:id", element: <Logbook /> },
      { path: "vehicles", element: <Vehicles /> },
      { path: "pilots", element: <Pilots /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
