import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./styles.css";
import { Layout } from "./components/Layout";
import { getToken } from "./lib/api/client";
import Login from "./app/Login";
import Inbox from "./app/Inbox";
import JobPage from "./app/JobPage";
import Studio from "./app/Studio";
import Pipeline from "./app/Pipeline";
import Messages from "./app/Messages";
import RunViewer from "./app/RunViewer";
import Analytics from "./app/Analytics";
import SettingsPage from "./app/SettingsPage";

function Private({ children }: { children: JSX.Element }) {
  return getToken() ? children : <Navigate to="/login" replace />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, "")}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Private><Layout /></Private>}>
          <Route path="/" element={<Navigate to="/inbox" replace />} />
          <Route path="/inbox" element={<Inbox />} />
          <Route path="/jobs/:id" element={<JobPage />} />
          <Route path="/studio/:thread" element={<Studio />} />
          <Route path="/pipeline" element={<Pipeline />} />
          <Route path="/messages" element={<Messages />} />
          <Route path="/runs/:thread" element={<RunViewer />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/inbox" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
