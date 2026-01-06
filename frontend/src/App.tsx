import { Routes, Route, Navigate } from "react-router-dom";
import { NotebookApp } from "./components/NotebookApp";

export default function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<Navigate to="/notebook" replace />} />
        <Route path="/notebook/:notebookId?" element={<NotebookApp />} />
        <Route path="*" element={<Navigate to="/notebook" replace />} />
      </Routes>
    </>
  );
}
